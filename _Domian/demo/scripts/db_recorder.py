#!/usr/bin/env python3
"""
DOMIAN — Database Recorder
Graba en SQLite todos los datos del servidor RuView en tiempo real.

Tablas:
  presencia  → estado general por tick (motion, confidence, personas)
  vitales    → signos vitales por tick (BR, HR, signal_quality)
  nodos      → estado de cada ESP32-S3 por tick
  personas   → tracks individuales por tick
  eventos    → eventos discretos (caídas, alertas, conexiones)

Uso:
  source ~/domian_env/bin/activate
  python3 db_recorder.py

  # Con IP personalizada:
  WS_URL=ws://192.168.0.19:8765/ws/sensing python3 db_recorder.py
"""

import asyncio
import websockets
import json
import sqlite3
import os
import sys
import signal
from datetime import datetime
from collections import deque

# ── Configuración ────────────────────────────────────────────────
WS_URL  = os.environ.get("WS_URL", "ws://192.168.0.19:8765/ws/sensing")
DB_PATH = os.environ.get("DB_PATH", os.path.expanduser(
    "~/Documents/RuView/_Domian/demo/data/ruview.db"
))

# Parámetros de detección de caídas
VENTANA_CAIDA   = 30   # frames (~3 segundos)
MOTION_SPIKE    = 60   # umbral de spike para caída
MOTION_POST     = 15   # umbral post-caída (quieto)

# ── Inicializar base de datos ────────────────────────────────────
def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    cur = con.cursor()
    cur.executescript("""
    -- ─────────────────────────────────────────────────────────
    -- Estado general del sistema por tick
    -- ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS presencia (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        tick        INTEGER NOT NULL,
        motion      TEXT,               -- absent | present_still | present_moving
        confidence  REAL DEFAULT 0,     -- confianza clasificador (0.0-1.0)
        presence    INTEGER DEFAULT 0,  -- 1=hay alguien, 0=vacío
        personas    INTEGER DEFAULT 0   -- estimated_persons (dedup aplicado)
    );
    CREATE INDEX IF NOT EXISTS idx_presencia_ts ON presencia(timestamp);
    CREATE INDEX IF NOT EXISTS idx_presencia_motion ON presencia(motion);

    -- ─────────────────────────────────────────────────────────
    -- Signos vitales por tick
    -- ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS vitales (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        tick            INTEGER NOT NULL,
        breathing_bpm   REAL DEFAULT 0, -- respiración en RPM
        heart_bpm       REAL DEFAULT 0, -- pulso en BPM
        breathing_conf  REAL DEFAULT 0, -- confianza respiración (0.0-1.0)
        heart_conf      REAL DEFAULT 0, -- confianza pulso (0.0-1.0)
        signal_quality  REAL DEFAULT 0  -- calidad general señal CSI
    );
    CREATE INDEX IF NOT EXISTS idx_vitales_ts ON vitales(timestamp);

    -- ─────────────────────────────────────────────────────────
    -- Estado de cada nodo ESP32-S3 por tick (4 registros/tick)
    -- ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS nodos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        tick        INTEGER NOT NULL,
        node_id     INTEGER NOT NULL,   -- 1, 2, 3 o 4
        variance    REAL DEFAULT 0,     -- varianza CSI (actividad)
        motion_band REAL DEFAULT 0,     -- potencia banda movimiento
        confidence  REAL DEFAULT 0,     -- confianza nodo individual
        stale       INTEGER DEFAULT 0,  -- 1=desconectado, 0=activo
        last_seen   INTEGER DEFAULT 0   -- ms desde último paquete
    );
    CREATE INDEX IF NOT EXISTS idx_nodos_ts      ON nodos(timestamp);
    CREATE INDEX IF NOT EXISTS idx_nodos_node_id ON nodos(node_id);
    CREATE INDEX IF NOT EXISTS idx_nodos_stale   ON nodos(stale);

    -- ─────────────────────────────────────────────────────────
    -- Tracks individuales de personas por tick
    -- ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS personas (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        tick        INTEGER NOT NULL,
        person_id   INTEGER NOT NULL,   -- ID del track del servidor
        pos_x       REAL DEFAULT 0,     -- posición X estimada
        pos_y       REAL DEFAULT 0,     -- posición Y estimada
        pos_z       REAL DEFAULT 0,     -- posición Z estimada
        confidence  REAL DEFAULT 0      -- confianza del track
    );
    CREATE INDEX IF NOT EXISTS idx_personas_ts        ON personas(timestamp);
    CREATE INDEX IF NOT EXISTS idx_personas_person_id ON personas(person_id);

    -- ─────────────────────────────────────────────────────────
    -- Eventos discretos del sistema
    -- Tipos: caida_detectada | presencia_detectada | ausencia_detectada
    --        nodo_desconectado | nodo_reconectado | servidor_iniciado
    --        alerta_vitales | alerta_inactividad | automatizacion_ha
    -- ─────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS eventos (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        tipo        TEXT    NOT NULL,   -- tipo de evento (ver arriba)
        subtipo     TEXT,               -- detalle adicional
        score       REAL DEFAULT 0,     -- score de confianza del evento (0-1)
        descripcion TEXT,               -- texto descriptivo del evento
        datos_json  TEXT,               -- datos adicionales en JSON
        origen      TEXT DEFAULT 'sistema',  -- sistema | ha | usuario | nodo
        tick        INTEGER             -- tick del servidor cuando ocurrió
    );
    CREATE INDEX IF NOT EXISTS idx_eventos_ts   ON eventos(timestamp);
    CREATE INDEX IF NOT EXISTS idx_eventos_tipo ON eventos(tipo);
    """)
    con.commit()
    return con


def registrar_evento(cur, tipo, subtipo=None, score=0.0,
                     descripcion=None, datos=None, origen='sistema', tick=0):
    """Inserta un evento discreto en la tabla eventos."""
    cur.execute("""
        INSERT INTO eventos (timestamp, tipo, subtipo, score, descripcion, datos_json, origen, tick)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        tipo, subtipo,
        round(score, 4),
        descripcion,
        json.dumps(datos) if datos else None,
        origen,
        tick
    ))


# ── Detector de caídas por patrón CSI ───────────────────────────
class FallDetector:
    def __init__(self):
        self.ventana = deque(maxlen=VENTANA_CAIDA)
        self.ultimo_evento = None
        self.cooldown = 30  # frames entre detecciones

    def update(self, estado, motion, conf):
        self.ventana.append({'estado': estado, 'motion': motion, 'conf': conf})
        if self.ultimo_evento is not None:
            self.ultimo_evento -= 1

    def detectar(self):
        if len(self.ventana) < 15:
            return False, 0.0
        if self.ultimo_evento is not None and self.ultimo_evento > 0:
            return False, 0.0

        motions  = [f['motion'] for f in self.ventana]
        estados  = [f['estado'] for f in self.ventana]
        confs    = [f['conf'] for f in self.ventana]

        motion_max = max(motions[:-10]) if motions[:-10] else 0
        motion_rec = sum(motions[-5:]) / 5

        habia_movimiento = any(e in ['active', 'present_moving'] for e in estados[:-8])
        ahora_quieto     = all(e in ['absent', 'present_still'] for e in estados[-5:])
        spike            = motion_max > MOTION_SPIKE and motion_rec < MOTION_POST
        conf_ok          = sum(confs[-5:]) / 5 > 0.3

        if habia_movimiento and ahora_quieto and spike and conf_ok:
            score = min(1.0, (motion_max / 100) * 0.7 + (1 - motion_rec / 60) * 0.3)
            self.ultimo_evento = self.cooldown
            return True, round(score, 3)
        return False, 0.0


# ── Detector de transiciones de presencia ───────────────────────
class PresenceTracker:
    def __init__(self):
        self.ultimo_estado = None

    def update(self, presence, tick, cur):
        estado_actual = 'presente' if presence else 'ausente'
        if self.ultimo_estado is not None and estado_actual != self.ultimo_estado:
            if estado_actual == 'presente':
                registrar_evento(cur, 'presencia_detectada',
                    descripcion='Persona detectada en el depto',
                    score=1.0, tick=tick)
            else:
                registrar_evento(cur, 'ausencia_detectada',
                    descripcion='Depto vacío detectado',
                    score=1.0, tick=tick)
        self.ultimo_estado = estado_actual


# ── Loop principal ───────────────────────────────────────────────
async def grabar():
    con = init_db(DB_PATH)
    cur = con.cursor()

    fall_detector     = FallDetector()
    presence_tracker  = PresenceTracker()
    frames            = 0
    errores           = 0
    inicio            = datetime.now()

    # Registrar inicio del servidor
    registrar_evento(cur, 'servidor_iniciado',
        descripcion=f'db_recorder iniciado — conectando a {WS_URL}',
        origen='sistema')
    con.commit()

    print("━" * 55)
    print("💾 DOMIAN DB Recorder")
    print(f"   DB:  {DB_PATH}")
    print(f"   WS:  {WS_URL}")
    print("━" * 55)
    print(f"{'Hora':8} {'Motion':16} {'Conf':6} {'BR':6} {'HR':6} {'Pers':5} {'Frames':>8}")
    print("─" * 55)

    retry_delay = 3

    while True:
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            ) as ws:
                retry_delay = 3
                registrar_evento(cur, 'servidor_iniciado',
                    descripcion='WebSocket conectado', origen='sistema')
                con.commit()

                async for msg in ws:
                    try:
                        data   = json.loads(msg)
                        ts     = datetime.now().isoformat()
                        tick   = data.get('tick', 0)
                        clf    = data.get('classification', {})
                        vit    = data.get('vital_signs', {})
                        nfeats = data.get('node_features', [])
                        pers   = data.get('persons', [])
                        est    = data.get('estimated_persons', len(pers))

                        motion   = clf.get('motion_level', 'unknown')
                        conf     = clf.get('confidence', 0)
                        presence = clf.get('presence', False)
                        br       = vit.get('breathing_rate_bpm') or 0
                        hr       = vit.get('heart_rate_bpm') or 0
                        motion_b = data.get('features', {}).get('motion_band_power', 0)

                        # ── Presencia ──────────────────────────
                        cur.execute("""
                            INSERT INTO presencia
                            (timestamp,tick,motion,confidence,presence,personas)
                            VALUES (?,?,?,?,?,?)
                        """, (ts, tick, motion, conf,
                              1 if presence else 0, est))

                        # ── Vitales ────────────────────────────
                        cur.execute("""
                            INSERT INTO vitales
                            (timestamp,tick,breathing_bpm,heart_bpm,
                             breathing_conf,heart_conf,signal_quality)
                            VALUES (?,?,?,?,?,?,?)
                        """, (ts, tick, br, hr,
                              vit.get('breathing_confidence', 0),
                              vit.get('heartbeat_confidence', 0),
                              vit.get('signal_quality', 0)))

                        # ── Nodos ──────────────────────────────
                        for nf in nfeats:
                            f = nf.get('features', {})
                            cur.execute("""
                                INSERT INTO nodos
                                (timestamp,tick,node_id,variance,motion_band,
                                 confidence,stale,last_seen)
                                VALUES (?,?,?,?,?,?,?,?)
                            """, (ts, tick,
                                  nf.get('node_id', 0),
                                  f.get('variance', 0),
                                  f.get('motion_band_power', 0),
                                  nf.get('classification', {}).get('confidence', 0),
                                  1 if nf.get('stale') else 0,
                                  nf.get('last_seen_ms', 0)))

                        # ── Personas ───────────────────────────
                        for p in pers:
                            pos = p.get('position') or {}
                            cur.execute("""
                                INSERT INTO personas
                                (timestamp,tick,person_id,pos_x,pos_y,pos_z,confidence)
                                VALUES (?,?,?,?,?,?,?)
                            """, (ts, tick,
                                  p.get('id', 0),
                                  pos.get('x', 0) if isinstance(pos, dict) else 0,
                                  pos.get('y', 0) if isinstance(pos, dict) else 0,
                                  pos.get('z', 0) if isinstance(pos, dict) else 0,
                                  p.get('confidence', 0)))

                        # ── Detector caídas ────────────────────
                        fall_detector.update(motion, motion_b, conf)
                        caida, score = fall_detector.detectar()
                        if caida:
                            registrar_evento(cur, 'caida_detectada',
                                score=score,
                                descripcion=f'Posible caída detectada (score={score:.2f})',
                                datos={'motion_spike': motion_b, 'confidence': conf},
                                origen='sistema', tick=tick)
                            print(f"\n🚨 [{ts[11:19]}] CAÍDA DETECTADA — score={score:.2f}")

                        # ── Tracker presencia ──────────────────
                        presence_tracker.update(presence, tick, cur)

                        # ── Alerta vitales anómalos ────────────
                        if br > 0 and (br < 8 or br > 35):
                            registrar_evento(cur, 'alerta_vitales',
                                subtipo='respiracion_anomala',
                                score=0.7,
                                descripcion=f'Respiración fuera de rango: {br:.1f} RPM',
                                datos={'br': br, 'hr': hr},
                                tick=tick)
                        if hr > 0 and (hr < 45 or hr > 120):
                            registrar_evento(cur, 'alerta_vitales',
                                subtipo='pulso_anomalo',
                                score=0.7,
                                descripcion=f'Pulso fuera de rango: {hr:.1f} BPM',
                                datos={'br': br, 'hr': hr},
                                tick=tick)

                        con.commit()
                        frames += 1

                        # ── Display ────────────────────────────
                        if frames % 10 == 0:
                            elapsed = (datetime.now() - inicio).seconds
                            print(
                                f"{ts[11:19]:8} {motion:16} "
                                f"{conf:.2f}   {br:5.1f}  {hr:5.1f}  "
                                f"{est:3}  {frames:>8,}",
                                end='\r'
                            )

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        errores += 1
                        print(f"\n⚠️  Error frame: {e}")

        except (websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError, OSError) as e:
            print(f"\n⚠️  Desconectado: {e} — reconectando en {retry_delay}s...")
            registrar_evento(cur, 'nodo_desconectado',
                descripcion=str(e), origen='sistema')
            con.commit()
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)

        except asyncio.CancelledError:
            break

    # Cierre limpio
    registrar_evento(cur, 'servidor_iniciado',
        descripcion=f'db_recorder detenido — {frames:,} frames grabados',
        origen='sistema')
    con.commit()
    con.close()
    print(f"\n✅ Detenido — {frames:,} frames grabados en {DB_PATH}")


# ── Señales de sistema ───────────────────────────────────────────
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    task = loop.create_task(grabar())

    def shutdown(sig, frame):
        print("\n🛑 Deteniendo...")
        task.cancel()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()

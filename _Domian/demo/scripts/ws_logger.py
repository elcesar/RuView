import asyncio
import websockets
import json
from datetime import datetime
import os

BASE = os.path.expanduser("~/Documents/RuView/_Domian/demo/data")
WS_URL = "ws://192.168.0.8:8765/ws/sensing"

os.makedirs(BASE, exist_ok=True)

FILE_PRESENCIA = f"{BASE}/historial_presencia.json"
FILE_VITALES   = f"{BASE}/historial_vitales.json"
FILE_NODOS     = f"{BASE}/historial_nodos.json"

presencia_log = []
vitales_log   = []
nodos_log     = []

def guardar(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def confianza_asignacion(person_count, confidence, signal_quality):
    if person_count == 0:
        return "sin_persona"
    if person_count == 1 and confidence > 0.5 and signal_quality > 0.3:
        return "directa"
    if person_count > 1:
        return "ambigua"
    return "baja_confianza"

async def escuchar():
    print(f"Conectando a {WS_URL}...")
    async with websockets.connect(WS_URL) as ws:
        print("Conectado. Grabando 3 archivos:")
        print(f"  {FILE_PRESENCIA}")
        print(f"  {FILE_VITALES}")
        print(f"  {FILE_NODOS}")
        print("\nPresiona Ctrl+C para detener.\n")
        print(f"{'Hora':8} {'Estado':20} {'Conf':6} {'Resp':6} {'Pulso':6} {'Personas':8} {'Nodos':6} {'Asignacion':15}")
        print("-" * 85)

        while True:
            try:
                raw  = json.loads(await ws.recv())
                now  = datetime.now().isoformat()
                tick = raw.get("tick", 0)

                # ── Fuentes ──────────────────────────────
                clf    = raw.get("classification", {})
                feats  = raw.get("features", {})
                vitals = raw.get("vital_signs", {})
                persons = raw.get("persons", [])
                nfeats  = raw.get("node_features", [])

                motion_level = clf.get("motion_level", "unknown")
                presence     = clf.get("presence", False)
                confidence   = round(clf.get("confidence", 0), 3)
                sq           = round(vitals.get("signal_quality", 0), 3)
                person_count = len(persons)
                person_ids   = [p.get("id") for p in persons]

                presencia_confiable = (
                    presence and confidence > 0.5 and sq > 0.3
                )

                # ── 1. Presencia ──────────────────────────
                r_pres = {
                    "timestamp":          now,
                    "tick":               tick,
                    "classification":     motion_level,
                    "presence":           presence,
                    "confidence":         confidence,
                    "presencia_confiable": presencia_confiable,
                    "variance":           round(feats.get("variance", 0), 3),
                    "motion_band_power":  round(feats.get("motion_band_power", 0), 3),
                    "breathing_band":     round(feats.get("breathing_band_power", 0), 3),
                    "spectral_power":     round(feats.get("spectral_power", 0), 3),
                    "person_count":       person_count,
                    "person_ids":         person_ids,
                    "nodos_activos":      len(nfeats),
                }
                presencia_log.append(r_pres)
                guardar(FILE_PRESENCIA, presencia_log)

                # ── 2. Vitales ────────────────────────────
                asignacion = confianza_asignacion(person_count, confidence, sq)
                valido     = asignacion == "directa"

                r_vit = {
                    "timestamp":           now,
                    "tick":                tick,
                    "person_id":           person_ids[0] if person_count == 1 else None,
                    "person_ids":          person_ids,
                    "person_count_total":  person_count,
                    "asignacion":          asignacion,
                    "valido":              valido,
                    "breathing_rate_bpm":  round(vitals.get("breathing_rate_bpm", 0), 2),
                    "heart_rate_bpm":      round(vitals.get("heart_rate_bpm", 0), 2),
                    "breathing_conf":      round(vitals.get("breathing_confidence", 0), 3),
                    "heart_conf":          round(vitals.get("heartbeat_confidence", 0), 3),
                    "signal_quality":      sq,
                    "confianza_asignacion": round(
                        confidence * sq if valido else 0, 3
                    ),
                }
                vitales_log.append(r_vit)
                guardar(FILE_VITALES, vitales_log)

                # ── 3. Nodos ──────────────────────────────
                r_nodos = {
                    "timestamp": now,
                    "tick":      tick,
                    "nodos": [
                        {
                            "node_id":      n.get("node_id"),
                            "motion_level": n.get("classification", {}).get("motion_level"),
                            "presence":     n.get("classification", {}).get("presence"),
                            "confidence":   round(n.get("classification", {}).get("confidence", 0), 3),
                            "last_seen_ms": n.get("last_seen_ms", 0),
                            "stale":        n.get("stale", False),
                            "variance":     round(n.get("features", {}).get("variance", 0), 3),
                            "motion_band":  round(n.get("features", {}).get("motion_band_power", 0), 3),
                            "breathing_band": round(n.get("features", {}).get("breathing_band_power", 0), 3),
                            "frame_rate_hz": round(n.get("frame_rate_hz", 0), 2),
                            "novelty_score": round(n.get("novelty_score", 0), 3),
                        }
                        for n in nfeats
                    ]
                }
                nodos_log.append(r_nodos)
                guardar(FILE_NODOS, nodos_log)

                # ── Consola ───────────────────────────────
                print(
                    f"{now[11:19]:8} "
                    f"{motion_level.upper():20} "
                    f"{confidence:6.2f} "
                    f"{r_vit['breathing_rate_bpm']:6.1f} "
                    f"{r_vit['heart_rate_bpm']:6.1f} "
                    f"{person_count:8} "
                    f"{len(nfeats):6} "
                    f"{asignacion:15}"
                )

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(1)

try:
    asyncio.run(escuchar())
except KeyboardInterrupt:
    print(f"\nDetenido.")
    print(f"  Presencia: {len(presencia_log)} registros")
    print(f"  Vitales:   {len(vitales_log)} registros")
    print(f"  Nodos:     {len(nodos_log)} registros")
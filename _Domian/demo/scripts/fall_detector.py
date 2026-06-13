import asyncio
import websockets
import json
import requests
from datetime import datetime
from collections import deque

WS_URL   = "ws://192.168.0.8:8765/ws/sensing"
HA_URL   = "http://192.168.0.17:8123"
WEBHOOK  = "ruview_caida"

VENTANA = deque(maxlen=30)  # ~3 segundos

def detectar_caida(ventana):
    if len(ventana) < 15:
        return False, 0.0

    motions  = [f['motion'] for f in ventana]
    estados  = [f['estado'] for f in ventana]
    confs    = [f['conf'] for f in ventana]

    motion_max = max(motions[:-10])
    motion_rec = sum(motions[-5:]) / 5

    habia_movimiento = any(e in ['active', 'present_moving'] for e in estados[:-8])
    ahora_quieto     = all(e in ['absent', 'present_still'] for e in estados[-5:])
    spike_motion     = motion_max > 60 and motion_rec < 15
    conf_ok          = sum(confs[-5:]) / 5 > 0.3

    if habia_movimiento and ahora_quieto and spike_motion and conf_ok:
        score = min(1.0, (motion_max / 100) * 0.7 + (1 - motion_rec / 60) * 0.3)
        return True, score
    return False, 0.0

async def monitorear():
    print("🔍 DOMIAN Fall Detector activo...")
    print(f"{'Hora':8} {'Estado':16} {'Motion':8}")
    print("-" * 35)

    async with websockets.connect(WS_URL) as ws:
        async for msg in ws:
            data   = json.loads(msg)
            clf    = data.get('classification', {})
            feats  = data.get('features', {})
            ts     = datetime.now().strftime("%H:%M:%S")

            estado = clf.get('motion_level', 'unknown')
            conf   = clf.get('confidence', 0)
            motion = feats.get('motion_band_power', 0)

            VENTANA.append({'estado': estado, 'motion': motion, 'conf': conf})

            caida, score = detectar_caida(VENTANA)

            if caida:
                print(f"\n🚨 [{ts}] CAIDA DETECTADA — score={score:.2f}")
                try:
                    requests.post(
                        f"{HA_URL}/api/webhook/{WEBHOOK}",
                        json={
                            "evento": "caida_detectada",
                            "score":  round(score, 2),
                            "timestamp": datetime.now().isoformat()
                        },
                        timeout=3
                    )
                    print(f"   → Alerta enviada a Home Assistant ✅")
                except Exception as e:
                    print(f"   → Error HA: {e}")
            else:
                print(f"{ts:8} {estado:16} {motion:8.1f}", end='\r')

asyncio.run(monitorear())
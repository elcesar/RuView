import asyncio
import websockets
import json
from datetime import datetime
import os

OUTPUT = os.path.expanduser("~/Documents/RuView/_Domian/demo/data/historial_presencia.json")
WS_URL = "ws://192.168.0.8:8765/ws/sensing"

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

registros = []

async def escuchar():
    print(f"Conectando a {WS_URL}...")
    async with websockets.connect(WS_URL) as ws:
        print(f"Conectado. Grabando en {OUTPUT}")
        print("Presiona Ctrl+C para detener.\n")
        print(f"{'Hora':8} {'Estado':20} {'Presencia':10} {'Movimiento':12} {'Respiracion':12} {'Pulso':8} {'Conf':6} {'Personas':8}")
        print("-" * 90)

        while True:
            try:
                raw    = await ws.recv()
                data   = json.loads(raw)

                # Clasificacion
                clf    = data.get("classification", {})
                feats  = data.get("features", {})
                vitals = data.get("vital_signs", {})
                persons = data.get("persons", [])

                registro = {
                    "timestamp":          datetime.now().isoformat(),
                    "tick":               data.get("tick", 0),
                    "classification":     clf.get("motion_level", "unknown"),
                    "presence":           clf.get("presence", False),
                    "confidence":         round(clf.get("confidence", 0), 3),
                    "variance":           round(feats.get("variance", 0), 3),
                    "motion_band_power":  round(feats.get("motion_band_power", 0), 3),
                    "breathing_band":     round(feats.get("breathing_band_power", 0), 3),
                    "spectral_power":     round(feats.get("spectral_power", 0), 3),
                    "breathing_rate_bpm": round(vitals.get("breathing_rate_bpm", 0), 2),
                    "heart_rate_bpm":     round(vitals.get("heart_rate_bpm", 0), 2),
                    "breathing_conf":     round(vitals.get("breathing_confidence", 0), 3),
                    "heart_conf":         round(vitals.get("heartbeat_confidence", 0), 3),
                    "signal_quality":     round(vitals.get("signal_quality", 0), 3),
                    "person_count":       len(persons),
                    "person_ids":         [p.get("id") for p in persons],
                }

                registros.append(registro)

                # Guardar JSON
                with open(OUTPUT, "w") as f:
                    json.dump(registros, f, indent=2)

                # Consola
                estado = registro["classification"].upper()
                print(
                    f"{registro['timestamp'][11:19]:8} "
                    f"{estado:20} "
                    f"{'SI' if registro['presence'] else 'NO':10} "
                    f"{registro['motion_band_power']:12.2f} "
                    f"{registro['breathing_rate_bpm']:12.1f} "
                    f"{registro['heart_rate_bpm']:8.1f} "
                    f"{registro['confidence']:6.2f} "
                    f"{registro['person_count']:8}"
                )

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(1)

try:
    asyncio.run(escuchar())
except KeyboardInterrupt:
    print(f"\nDetenido. {len(registros)} registros guardados en {OUTPUT}")
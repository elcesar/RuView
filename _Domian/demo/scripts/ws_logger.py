import asyncio
import websockets
import json
from datetime import datetime
import os

OUTPUT = os.path.expanduser("~/Documents/RuView/data/historial_presencia.json")
WS_URL = "ws://192.168.0.8:8765"

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

registros = []

async def escuchar():
    print(f"Conectando a {WS_URL}...")
    async with websockets.connect(WS_URL) as ws:
        print(f"Conectado. Grabando en {OUTPUT}")
        print("Presiona Ctrl+C para detener.\n")
        while True:
            try:
                raw = await ws.recv()
                data = json.loads(raw)

                registro = {
                    "timestamp": datetime.now().isoformat(),
                    "presence":  data.get("presence", 0),
                    "motion":    data.get("motion", 0),
                    "rssi":      data.get("rssi", 0),
                    "classification": data.get("classification", "UNKNOWN"),
                    "confidence": data.get("confidence", 0),
                    "node_id":   4,
                }

                registros.append(registro)

                with open(OUTPUT, "w") as f:
                    json.dump(registros, f, indent=2)

                print(f"[{registro['timestamp'][11:19]}] "
                      f"{registro['classification']:20s} "
                      f"presence={registro['presence']:.2f} "
                      f"motion={registro['motion']:.2f} "
                      f"conf={registro['confidence']:.2f}")

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(1)

try:
    asyncio.run(escuchar())
except KeyboardInterrupt:
    print(f"\nDetenido. {len(registros)} registros guardados en {OUTPUT}")
import asyncio
import websockets
import json
import requests
from datetime import datetime

WS_URL             = "ws://192.168.0.8:8765/ws/sensing"
HA_URL             = "http://192.168.0.17:8123"
WEBHOOK            = "domian_presencia"
WEBHOOK_ALEXA      = "alexa_presencia"

CERTEZA_MINIMA     = 0.95  # 0.0 – 1.0  (ej: 0.90 = 90%)
SOLO_DESDE_AUSENTE = False  # True = solo gatilla si estado anterior era "ausente"

ultimo_estado    = None
webhook_enviado  = False  # se resetea cuando el estado vuelve a "ausente"

async def escuchar():
    print("Conectando a RuView...")
    async with websockets.connect(WS_URL) as ws:
        print("Conectado. Enviando eventos a Home Assistant...")
        while True:
            try:
                data = json.loads(await ws.recv())
                clf  = data.get("classification", {})
                estado = clf.get("motion_level", "unknown")
                confianza = clf.get("confidence", 0)
                presencia = clf.get("presence", False)

                global ultimo_estado, webhook_enviado

                estado_anterior = ultimo_estado
                ultimo_estado = estado  # siempre actualizar para tracking preciso

                # resetear cuando vuelve a ausente
                if estado == "ausente":
                    webhook_enviado = False

                venia_ausente = (not SOLO_DESDE_AUSENTE) or (estado_anterior == "ausente")
                if (not webhook_enviado
                        and confianza >= CERTEZA_MINIMA
                        and venia_ausente
                        and estado != estado_anterior):
                    webhook_enviado = True
                    payload = {
                        "estado":    estado,
                        "presencia": presencia,
                        "confianza": round(confianza, 3),
                        "timestamp": datetime.now().isoformat()
                    }
                    r = requests.post(
                        f"{HA_URL}/api/webhook/{WEBHOOK}",
                        json=payload
                    )
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"{estado} → HA {r.status_code}")

                    requests.post(f"{HA_URL}/api/webhook/{WEBHOOK_ALEXA}", json=payload)

            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(3)

asyncio.run(escuchar())
import asyncio
import websockets
import json
import requests
from datetime import datetime

# ── Configuración ────────────────────────────────────────────────
WS_URL          = "ws://localhost:8765/ws/sensing"
HA_URL          = "http://localhost:8123"
WEBHOOK         = "ruview_presencia"

UMBRAL_CONFIANZA = 0.9   # confianza mínima para disparar evento (0.0-1.0)
MIN_INTERVALO    = 10     # segundos mínimos entre eventos repetidos

# ── Estado ───────────────────────────────────────────────────────
ultimo_estado  = None
ultimo_cambio  = datetime.now()


def es_llegada(estado_anterior, estado_actual):
    """True si el estado anterior fue 'absent' y ahora hay presencia."""
    return estado_anterior == "absent" and estado_actual in (
        "present_still", "present_moving", "active"
    )


async def escuchar():
    global ultimo_estado, ultimo_cambio

    print("Conectando a RuView...")
    async with websockets.connect(WS_URL, ping_interval=20) as ws:
        print("Conectado. Enviando eventos a Home Assistant...")
        print(f"Umbral de confianza: {UMBRAL_CONFIANZA}")

        async for msg in ws:
            try:
                data = json.loads(msg)
                clf  = data.get("classification", {})
                estado    = clf.get("motion_level", "unknown")
                confianza = clf.get("confidence", 0)
                presencia = clf.get("presence", False)

                ahora = datetime.now()
                cambio_estado     = estado != ultimo_estado
                confianza_ok      = confianza > UMBRAL_CONFIANZA
                intervalo_ok      = (ahora - ultimo_cambio).seconds >= MIN_INTERVALO
                llegada_detectada = es_llegada(ultimo_estado, estado)

                if cambio_estado and confianza_ok and intervalo_ok:
                    estado_previo = ultimo_estado
                    ultimo_estado = estado
                    ultimo_cambio = ahora

                    payload = {
                        "estado":           estado,
                        "estado_anterior":  estado_previo,
                        "es_llegada":       llegada_detectada,
                        "presencia":        presencia,
                        "confianza":        round(confianza, 3),
                        "timestamp":        ahora.isoformat()
                    }

                    r = requests.post(
                        f"{HA_URL}/api/webhook/{WEBHOOK}",
                        json=payload,
                        timeout=3
                    )

                    tag = " 🚪LLEGADA" if llegada_detectada else ""
                    print(f"[{ahora.strftime('%H:%M:%S')}] "
                          f"{estado_previo or '?'} → {estado} "
                          f"(conf={confianza:.2f}) → HA {r.status_code}{tag}")

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"Error procesando frame: {e}")


async def main():
    retry_delay = 3
    while True:
        try:
            await escuchar()
            retry_delay = 3
        except (websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError, OSError) as e:
            print(f"Desconectado: {e} — reconectando en {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)
        except KeyboardInterrupt:
            print("\nDetenido por el usuario")
            break


if __name__ == "__main__":
    asyncio.run(main())

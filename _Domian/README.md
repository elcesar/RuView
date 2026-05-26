# _Domian / RuView Demo

Desarrollo personal sobre el proyecto open source [RuView](https://github.com/ruvnet/RuView) — sistema de detección espacial usando señales WiFi CSI (Channel State Information) sin cámaras ni wearables.

---

## Hardware

| Componente | Cantidad | Detalle |
|---|---|---|
| ESP32-S3 DevKit (8MB PSRAM) | 4 | Nodos sensores CSI |
| MacBook Air 2017 Intel | 1 | Servidor de desarrollo |
| Raspberry Pi 5 8GB | 1 | Servidor producción (Fase 6) |
| Amazon Echo Show | 1 | Dashboard domiciliario |

### Configuración de nodos

| Nodo | Canal WiFi | Posición | Node ID |
|---|---|---|---|
| N1 | 1 | Esquina sup-izq living | 1 |
| N2 | 6 | Esquina sup-der living | 2 |
| N3 | 11 | Esquina inf-izq dormitorio | 3 |
| N4 | 1 | Esquina inf-der dormitorio | 4 |

Depto: 5×6m, 2 habitaciones (living + dormitorio).

---

## Estructura del repositorio

```
_Domian/
└── demo/
    ├── scripts/          # Scripts Python de captura y análisis
    │   └── ws_logger.py  # Logger WebSocket → JSON
    ├── dashboard/        # Interfaces HTML propias
    └── data/             # Datos capturados (ignorados por Git)
```

---

## Setup rápido

### 1 — Requisitos

```bash
# Python
pip3 install websockets

# Rust (servidor)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

### 2 — Arrancar servidor

```bash
cd v2
cargo run -p wifi-densepose-sensing-server -- \
  --source esp32 \
  --bind-addr 0.0.0.0 \
  --udp-port 5005 \
  --http-port 8000 \
  --allowed-host 192.168.0.8 \
  --node-positions "0,6,2;5,6,2;0,0,2;5,0,2"
```

### 3 — Verificar nodos conectados

```bash
curl http://192.168.0.8:8000/api/v1/nodes
```

### 4 — Arrancar logger

```bash
python3 _Domian/demo/scripts/ws_logger.py
```

---

## Endpoints disponibles

| Endpoint | Descripción |
|---|---|
| `GET /` | Índice de endpoints |
| `GET /health` | Estado del servidor |
| `GET /api/v1/nodes` | Estado de los nodos conectados |
| `GET /api/v1/sensing/latest` | Último frame de sensing |
| `GET /api/v1/vital-signs` | Signos vitales estimados |
| `GET /api/v1/model/info` | Info del modelo RVF cargado |
| `WS ws://IP:8765/ws/sensing` | Stream WebSocket en tiempo real |
| `WS ws://IP:8765/ws/pose` | Stream WebSocket de pose |

---

## Roadmap de versiones

| Versión | Fase | Descripción |
|---|---|---|
| v1.0 | F4 S8 | Sistema base 4 nodos funcionando |
| v1.1 | F4 S10 | LEDs feedback en los 4 nodos |
| v1.2 | F5 S11 | Modelo fine-tuned para el depto |
| v2.0 | F5 S12 | Reconocimiento personal de habitantes |
| v2.1 | F5 S13 | Emotion detect + stress monitor |
| v3.0 | F6 S15 | Sistema autónomo RPi5 + Echo Show |

---

## Referencias

- Repositorio original: https://github.com/ruvnet/RuView
- Documentación: https://github.com/ruvnet/RuView/blob/main/docs/user-guide.md
- Modelo preentrenado: https://huggingface.co/ruvnet/wifi-densepose-pretrained
- Estándar WiFi Sensing: IEEE 802.11bf

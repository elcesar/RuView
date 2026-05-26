# Diccionario de datos — RuView WebSocket

Stream: `ws://192.168.0.8:8765/ws/sensing`
Frecuencia: ~10 frames por segundo
Formato: JSON

---

## Estructura del mensaje

```json
{
  "type":         "sensing_update",
  "timestamp":    1779763283.495,
  "source":       "esp32",
  "tick":         14913,
  "nodes":        [...],
  "features":     {...},
  "classification": {...},
  "signal_field": {...},
  "vital_signs":  {...},
  "persons":      [...],
  "node_features": [...]
}
```

---

## Campos raíz

| Campo | Tipo | Descripción | Ejemplo |
|---|---|---|---|
| `type` | string | Tipo de mensaje | `"sensing_update"` |
| `timestamp` | float | Unix timestamp en segundos | `1779763283.495` |
| `source` | string | Fuente de datos | `"esp32"` / `"simulate"` |
| `tick` | int | Contador de frames desde inicio del servidor | `14913` |

---

## `nodes[]` — Estado por nodo

Lista de nodos ESP32-S3 que enviaron datos en este frame.

| Campo | Tipo | Descripción | Ejemplo |
|---|---|---|---|
| `node_id` | int | Identificador del nodo (1-4) | `4` |
| `rssi_dbm` | float | Potencia de señal WiFi en dBm. 0.0 = no reportado por firmware | `0.0` |
| `position` | [x,y,z] | Posición configurada del nodo en metros | `[2.0, 0.0, 1.5]` |
| `amplitude` | float[] | Amplitud CSI por subportadora (56-64 valores) | `[0.0, 19.8, ...]` |
| `subcarrier_count` | int | Número de subportadoras capturadas | `64` |

### Sobre `amplitude[]`
Cada valor representa la amplitud de la señal en una subportadora WiFi diferente. Son las "huellas digitales" de cómo la señal rebota en el espacio. El modelo ML analiza el patrón completo para detectar presencia, movimiento y signos vitales.

---

## `features{}` — Características de la señal

Métricas extraídas del procesamiento de la señal CSI cruda.

| Campo | Tipo | Descripción | Rango típico |
|---|---|---|---|
| `mean_rssi` | float | RSSI promedio de los nodos | `-30` a `-80` dBm |
| `variance` | float | Variación total de la señal CSI. Alto = actividad | `0` a `200+` |
| `motion_band_power` | float | Potencia en banda de movimiento (0.5–2 Hz). Detecta movimiento corporal | `0` a `150+` |
| `breathing_band_power` | float | Potencia en banda de respiración (0.1–0.5 Hz). Detecta ciclo respiratorio | `0` a `100+` |
| `dominant_freq_hz` | float | Frecuencia dominante detectada en la señal | `0.1` a `2.0` Hz |
| `change_points` | int | Número de cambios abruptos detectados en la señal | `0` a `20+` |
| `spectral_power` | float | Potencia espectral total. Suma de todas las frecuencias | `0` a `200+` |

### Interpretación rápida de `features`

```
variance > 50        → hay actividad significativa
motion_band > 30     → hay movimiento corporal
breathing_band > 40  → hay respiración detectable
spectral_power > 80  → señal activa con presencia
change_points > 5    → movimientos frecuentes
```

---

## `classification{}` — Clasificación de presencia

Resultado del modelo de clasificación sobre las features.

| Campo | Tipo | Descripción | Valores posibles |
|---|---|---|---|
| `motion_level` | string | Estado de movimiento detectado | Ver tabla abajo |
| `presence` | bool | Hay presencia humana detectada | `true` / `false` |
| `confidence` | float | Confianza del clasificador (0-1) | `0.0` a `1.0` |

### Valores de `motion_level`

| Valor | Descripción | Típico cuando |
|---|---|---|
| `absent` | Sin presencia detectada | Habitación vacía |
| `present_still` | Persona presente y quieta | Sentado, durmiendo |
| `present_moving` | Persona presente y en movimiento | Caminando, gestos |
| `active` | Actividad intensa | Ejercicio, movimientos rápidos |
| `unknown` | Sin datos suficientes | Nodo desconectado o calibrando |

### Sobre `confidence`
- `< 0.3` → clasificación muy incierta, ignorar
- `0.3–0.6` → clasificación moderada (normal con 1 nodo)
- `0.6–0.8` → buena confianza (2-3 nodos)
- `> 0.8` → alta confianza (4 nodos calibrados)

---

## `vital_signs{}` — Signos vitales

Estimación de signos vitales a partir del análisis de la señal CSI.

| Campo | Tipo | Descripción | Rango normal |
|---|---|---|---|
| `breathing_rate_bpm` | float | Frecuencia respiratoria en respiraciones por minuto | `12`–`20` RPM en reposo |
| `heart_rate_bpm` | float | Frecuencia cardíaca en latidos por minuto | `60`–`100` BPM en reposo |
| `breathing_confidence` | float | Confianza de la medición de respiración (0-1) | `> 0.5` confiable |
| `heartbeat_confidence` | float | Confianza de la medición de pulso (0-1) | `> 0.5` confiable |
| `signal_quality` | float | Calidad general de la señal CSI (0-1) | `> 0.5` óptimo |

### Interpretación de signos vitales

```
breathing_rate:
  < 12 RPM  → bradipnea (respiración lenta)
  12-20 RPM → normal en reposo
  20-30 RPM → elevada (actividad o estrés)
  > 30 RPM  → muy elevada, verificar

heart_rate:
  < 60 BPM  → bradicardia
  60-80 BPM → normal en reposo
  80-100 BPM → elevado (actividad leve)
  > 100 BPM → taquicardia o ejercicio

signal_quality:
  < 0.3     → señal mala, datos poco confiables
  0.3-0.5   → señal moderada (1 nodo lejos)
  > 0.5     → señal buena, datos confiables
```

### Limitaciones con 1 solo nodo
Con 1 nodo la confianza de signos vitales es baja (`< 0.5`). Para mediciones confiables se necesitan mínimo 2 nodos. Con 4 nodos la precisión mejora significativamente.

---

## `persons[]` — Personas detectadas

Lista de personas rastreadas en el espacio.

| Campo | Tipo | Descripción | Ejemplo |
|---|---|---|---|
| `id` | int | ID temporal del track. Cambia entre sesiones | `453` |
| `confidence` | float | Confianza del tracking de esta persona | `0.9` |
| `keypoints` | objeto[] | 17 puntos clave del esqueleto estimado | Ver abajo |
| `bbox` | objeto | Bounding box de la persona en el espacio | Ver abajo |
| `zone` | string | Zona de tracking | `"tracked"` |

### `keypoints[]` — 17 puntos del esqueleto

Cada keypoint representa una articulación del cuerpo estimada por el modelo.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | string | Nombre de la articulación |
| `x` | float | Posición horizontal en píxeles del canvas |
| `y` | float | Posición vertical en píxeles del canvas |
| `z` | float | Profundidad estimada |
| `confidence` | float | Confianza de este keypoint específico |

### Articulaciones disponibles (17)

```
Cabeza:    nose, left_eye, right_eye, left_ear, right_ear
Torso:     left_shoulder, right_shoulder, left_hip, right_hip
Brazos:    left_elbow, right_elbow, left_wrist, right_wrist
Piernas:   left_knee, right_knee, left_ankle, right_ankle
```

### `bbox{}` — Bounding box

| Campo | Tipo | Descripción |
|---|---|---|
| `x` | float | Centro horizontal en píxeles |
| `y` | float | Centro vertical en píxeles |
| `width` | float | Ancho normalizado (0-1) |
| `height` | float | Alto normalizado (0-1) |

### Nota sobre `person_count` con 1 nodo
Con 1 solo nodo el sistema tiende a sobreestimar el número de personas (puede detectar 2-3 cuando solo hay 1). Con 4 nodos el conteo es más preciso.

---

## `node_features[]` — Features por nodo individual

Mismo contenido que `features{}` pero desglosado por cada nodo. Útil para diagnóstico.

| Campo | Tipo | Descripción |
|---|---|---|
| `node_id` | int | ID del nodo |
| `features` | objeto | Mismos campos que `features{}` raíz |
| `classification` | objeto | Clasificación individual del nodo |
| `rssi_dbm` | float | RSSI de este nodo |
| `last_seen_ms` | int | Milisegundos desde el último paquete recibido |
| `frame_rate_hz` | float | Frames por segundo de este nodo |
| `stale` | bool | `true` si el nodo no ha enviado datos recientemente |
| `novelty_score` | float | Qué tan diferente es esta señal vs el baseline aprendido |

---

## `signal_field{}` — Campo de señal 3D

Representación del campo de señal WiFi en el espacio como una grilla 3D.

| Campo | Tipo | Descripción |
|---|---|---|
| `grid_size` | [x,y,z] | Dimensiones de la grilla | `[20, 1, 20]` |
| `values` | float[] | Intensidad de señal por celda (0-1). 1.0 = máxima perturbación | `[0.11, 0.12, ...]` |

### Sobre `values`
Es la representación numérica del heatmap que ves en el Observatory. Cada valor corresponde a una celda del espacio. El valor `1.0` indica el punto de máxima perturbación — generalmente donde está la persona. Se usa para el renderizado 3D del dashboard.

---

## Campos del logger `ws_logger.py`

Los campos guardados en `historial_presencia.json` son un subconjunto simplificado del mensaje completo:

| Campo | Fuente en WebSocket | Descripción |
|---|---|---|
| `timestamp` | calculado | Fecha y hora local ISO 8601 |
| `tick` | `tick` | Contador de frames del servidor |
| `classification` | `classification.motion_level` | Estado de presencia |
| `presence` | `classification.presence` | Booleano de presencia |
| `confidence` | `classification.confidence` | Confianza general |
| `variance` | `features.variance` | Variación de señal |
| `motion_band_power` | `features.motion_band_power` | Potencia de movimiento |
| `breathing_band` | `features.breathing_band_power` | Potencia de respiración |
| `spectral_power` | `features.spectral_power` | Potencia espectral total |
| `breathing_rate_bpm` | `vital_signs.breathing_rate_bpm` | Frecuencia respiratoria |
| `heart_rate_bpm` | `vital_signs.heart_rate_bpm` | Frecuencia cardíaca |
| `breathing_conf` | `vital_signs.breathing_confidence` | Confianza respiración |
| `heart_conf` | `vital_signs.heartbeat_confidence` | Confianza pulso |
| `signal_quality` | `vital_signs.signal_quality` | Calidad de señal |
| `person_count` | `len(persons)` | Número de personas detectadas |
| `person_ids` | `persons[].id` | IDs temporales de cada persona |

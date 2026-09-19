# Arquitectura técnica

## 1. Vista general

```
┌──────────────── NAVEGADOR ────────────────┐      ┌──────────── SERVIDOR (FastAPI) ────────────┐
│ Cámara PC (getUserMedia)                  │      │                                            │
│   canvas → JPEG ──── WebSocket /ws/live ──┼─────▶│ LiveRegistry ─┐                            │
│ Subida de videos ─── POST /api/videos ────┼─────▶│ JobManager ───┼─▶ Analyzer (por sesión)    │
│ Cámara IP  ───────── POST /api/camera ────┼─────▶│ CameraStream ─┘      │                     │
│                                           │      │                      ▼                     │
│ Dashboard / Reportes ◀── REST /api/* ─────┼──────┤   Detector → Tracker → ZoneManager → Reglas│
│ Overlay en canvas  ◀── JSON por WS ───────┼──────┤                      │                     │
└───────────────────────────────────────────┘      │                      ▼                     │
                                                   │            SQLite (WAL) data/officevision.db│
                                                   │   sessions · snapshots · tracks · events    │
                                                   │   zones · employees · attendance · calls    │
                                                   └────────────────────────────────────────────┘
```

Una **sesión** es una fuente analizada (una conexión de cámara o un video). Cada sesión tiene su
propio `Analyzer`, que a su vez tiene detector, tracker y `ZoneManager` propios: el estado nunca
se mezcla entre fuentes, lo que permite analizar varias cámaras y videos a la vez.

## 2. Ciclo de un cuadro (`app/pipeline.py::Analyzer.process`)

1. **Detección.** `detector.detect(frame)` devuelve `Detection(x1,y1,x2,y2,conf,label)`.
   Se separan las detecciones de la clase principal (`person`) del resto de objetos.
2. **Seguimiento.** `Tracker.update()` asocia detecciones con tracks existentes por IoU
   (*greedy*, mayor solape primero, solo entre la misma clase). Lo no asociado crea tracks
   nuevos; los tracks sin coincidencia envejecen (`misses`) y se cierran al superar `max_age`.
   Un track se considera válido tras `min_hits` coincidencias.
   Hay **dos instancias**: una para personas y otra para objetos (con `max_age` doble,
   porque un objeto quieto se ocluye con frecuencia). Separarlos evita que el mobiliario
   contamine el aforo y permite reglas propias para cada uno.
3. **Zonas.** Para cada track activo se evalúa el punto de contacto con el piso contra cada
   polígono (`cv2.pointPolygonTest`). Comparando con las zonas del cuadro anterior se derivan
   entradas, salidas y permanencia acumulada.
4. **Reglas.** Sobre personas: aforo por zona, permanencia por track/zona, aglomeración
   global, zona inactiva y actividad fuera de horario. Sobre objetos: alta en escena
   (`objeto_nuevo`, tras un calentamiento que evita anunciar el mobiliario fijo), baja
   (`objeto_retirado`) y `objeto_sin_supervision`, que compara la distancia del objeto a
   la persona más cercana contra un radio proporcional a la diagonal del cuadro —así el
   umbral no depende de la resolución.
5. **Persistencia.**
   * eventos → `events` en el momento (con captura JPG si la severidad es warning o critical),
   * estado → `snapshots` cada `snapshot_interval_s`,
   * resumen narrado → `events(type='resumen')` cada `summary_interval_s`,
   * track cerrado → `tracks` (upsert por `session_id + track_key`).
6. **Respuesta.** Un JSON con cajas normalizadas, ocupación por zona, métricas acumuladas,
   eventos del cuadro, fps y latencia. El navegador solo dibuja.

### Manejo del tiempo

| | Cámara en vivo | Video subido |
|---|---|---|
| Reloj de permanencia | `time.monotonic()` | segundos de video (`frame_idx / fps`) |
| Sello de tiempo | `datetime.now()` | inicio de sesión + tiempo de video |

Gracias a esto, un video de una hora procesado en cinco minutos produce permanencias y
resúmenes con la misma escala temporal que una sesión en vivo.

## 3. Registro de detectores (`app/vision/detector.py`)

```python
class BaseDetector:
    def detect(self, frame: np.ndarray) -> List[Detection]: ...
```

| Backend | Requisitos | Uso típico |
|---|---|---|
| `yolo` | `ultralytics` + PyTorch | Producción; mejor precisión |
| `onnx` | Un `.onnx` en `models/` | Equipos sin PyTorch (OpenCV DNN) |
| `motion` | Nada | Respaldo garantizado, sin red ni modelos |

`build_detector()` intenta en orden y siempre deja una red de seguridad. El backend activo se
guarda en la sesión y se muestra en la interfaz, para que un resultado nunca se interprete sin
saber con qué se obtuvo.

Para añadir un modelo nuevo: crear la clase, devolver `Detection` y registrarla en
`build_detector()`. Tracking, zonas, reglas, base de datos y UI se reutilizan tal cual.

## 3.1 Detección automática de zonas (`app/vision/autozones.py`)

Ambos modos trabajan sobre una rejilla de 128×72 celdas y devuelven polígonos
normalizados, listos para el mismo editor manual.

**Por escena** (`suggest_from_image` / `suggest_from_frames`)

1. Se detecta con un juego de clases ampliado (mobiliario y equipos, no solo el
   configurado para el análisis normal).
2. Cada caja suma en la rejilla; una dilatación 7×7 une lo contiguo (un escritorio con su
   silla y su monitor forman un solo bloque).
3. `connectedComponentsWithStats` → contorno → `approxPolyDP` → polígono de ≤10 vértices.
4. Las clases dominantes dan nombre, tipo, aforo y umbral de permanencia.
5. Con varios cuadros se normaliza dividiendo entre el número de muestras: cuatro sillas
   vistas en seis cuadros son cuatro sillas, no veinticuatro.

**Por actividad** (`suggest_from_activity`)

1. Se leen las trayectorias de `tracks.path_json` (ya normalizadas).
2. Se acumulan dos rejillas: presencia (muestras por celda) y desplazamiento (distancia
   entre muestras consecutivas).
3. Umbral en el percentil 60 de la presencia → componentes conexas → polígonos.
4. Clasificación con dos señales independientes: `densidad = muestras/celdas` y
   `velocidad = desplazamiento/muestras`. Baja densidad + alta velocidad = corredor de
   paso; alta densidad = área de permanencia.
5. El aforo sugerido sale del número de trayectorias distintas que cruzan la región,
   acotado entre 2 y 20.

Las propuestas nunca se guardan solas: la API devuelve la lista con su justificación y el
usuario confirma cuáles aplicar (`POST /api/zones/apply`).

## 4. Esquema de datos

```sql
sessions(id, source_id, name, kind, status, started_at, ended_at,
         frames_seen, frames_analyzed, duration_s, progress, detector, meta_json)

snapshots(id, session_id, ts, video_ts, persons, objects,
          movement_index, fps, zones_json, classes_json)

tracks(id, session_id, track_key, label, first_ts, last_ts,
       first_video_ts, last_video_ts, duration_s, frames, avg_conf,
       distance_px, zones_json, path_json)

events(id, session_id, ts, video_ts, type, severity, track_key, zone,
       message, snapshot, meta_json)

zones(id, name, kind, polygon_json, color, max_occupancy, dwell_alert_s, enabled, created_at)

employees(emp_id, name, area, entry_time, lunch, exit_time)
attendance(emp_id, name, date, check_in, check_out, worked_min, late_min, early_min, month)
calls(ts, date, hour, direction, from_num, to_num, extension, ext_id, agent, result, duration_s, week)
```

`snapshots` es una serie temporal: todas las gráficas del dashboard son agregaciones SQL sobre
ella (`GROUP BY substr(ts,1,16)` por minuto, `substr(ts,12,2)` por hora). `tracks` responde
preguntas por persona (¿cuánto duró?, ¿por qué zonas pasó?) y `events` es la bitácora auditable.

## 5. Análisis cruzado con la operación (`app/business.py`)

* **Biométrico.** La hoja `Nomina` define horario esperado por colaborador. Cada hoja mensual
  trae bloques de 7 filas por persona (`Check-in1`, `Check-out1`, `Late Come`…) con una columna
  por día; se recorren las columnas de día, se reconstruye la fecha y se calculan horas
  trabajadas, retraso contra el horario de nómina y salida anticipada.
* **RingCentral.** Una hoja por semana; se normalizan fecha (`Sat 08/23/2025`), hora, duración
  (`hh:mm:ss` → segundos) y extensión (`9 - Camila Flores` → id + nombre).
* **Cruce horario.** Para cada hora se comparan: personal esperado por nómina, presentes según
  biométrico, personas vistas por la cámara (promedio y pico de `snapshots`) y volumen de
  llamadas (atendidas vs. perdidas). Si hay un día con ambas fuentes se usa ese día; si no, se
  construye un **día típico** con promedios históricos.
* **Hallazgos automáticos:** hora pico de llamadas, cobertura baja frente a la demanda,
  discrepancia entre lo que ve la cámara y los marcajes (visitas o personal sin marcar) y
  tramos con más de la mitad de las llamadas sin atender.

## 6. Concurrencia

* El bucle de eventos de FastAPI nunca se bloquea: todo el trabajo de CPU (decodificar JPEG,
  inferencia, escritura en base de datos) se delega con `run_in_threadpool`.
* Los videos se procesan en un `ThreadPoolExecutor` limitado por `max_concurrent_jobs`.
* SQLite en WAL con un `RLock` alrededor de cada transacción: varias sesiones escriben en
  paralelo sin bloqueos ni corrupción.
* El envío de cuadros desde el navegador es de tipo *pull* (un cuadro en vuelo por vez), lo que
  evita que la cola crezca si el servidor va más lento que la cámara.

## 7. Configuración (`config.json`)

Se crea sola con los valores por defecto y se puede editar en caliente desde la interfaz o con
`POST /api/config`. Parámetros más usados:

| Clave | Por defecto | Efecto |
|---|---|---|
| `detector` | `auto` | `auto`, `yolo`, `onnx`, `motion` |
| `model` | `yolo11n.pt` | Pesos YOLO (`yolo11s.pt` para más precisión) |
| `device` | `cpu` | `0` o `cuda` para GPU |
| `conf_threshold` | `0.35` | Umbral de confianza |
| `classes` | person, laptop, cell phone… | Clases a detectar |
| `live_target_fps` / `video_target_fps` | 6 | Cuadros analizados por segundo |
| `snapshot_interval_s` / `summary_interval_s` | 5 / 60 | Frecuencia de escritura en la base |
| `crowd_threshold` | 8 | Umbral de aglomeración |
| `track_objects` | true | Seguir también objetos, no solo personas |
| `valuable_classes` | laptop, cell phone, backpack… | Objetos vigilados |
| `unattended_alert_s` / `unattended_radius` | 120 / 0.22 | Objeto sin persona cerca |
| `object_warmup_frames` | 25 | Cuadros antes de anunciar "objeto nuevo" |
| `idle_zone_alert_s` | 900 | Zona sin actividad |
| `work_start` / `work_end` / `work_days` | 07:00 / 18:00 / lun-sáb | Horario laboral |
| `blur_faces` / `store_snapshots` / `snapshot_retention_days` | true / true / 15 | Privacidad |

## 8. Puntos de extensión

| Necesidad | Dónde tocar |
|---|---|
| Otro modelo de IA | `app/vision/detector.py` (nueva clase + `build_detector`) |
| Otro criterio de zonas automáticas | `app/vision/autozones.py` (`_nombrar`, umbrales) |
| Nueva regla de alerta | `Analyzer._global_rules` o `ZoneManager.update` |
| Otra base de datos | `app/db.py` (capa única de acceso) |
| Nueva métrica en el dashboard | consulta en `app/api.py` + gráfica en `app/templates/index.html` |
| Otra fuente operativa (ERP, CRM) | `app/business.py` siguiendo el patrón de importación |
| Notificaciones externas | `Analyzer._persist_event` (webhook, correo, Teams) |

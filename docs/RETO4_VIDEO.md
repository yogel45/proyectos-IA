# OfficeVision AI — Análisis de video con IA

**Reto 4.** Proyecto independiente: su propio servidor, su propia base de datos y su
propia interfaz. No necesita ninguno de los otros proyectos de este repositorio para
funcionar.

```bash
pip install -r requirements.txt
python run.py            # http://127.0.0.1:8000
python run.py --check    # comprobar el entorno sin arrancar nada
```

**Video demostrativo**: [`docs/video-demostrativo.mp4`](video-demostrativo.mp4) — 66
segundos de análisis real, con las personas seguidas, su permanencia, las zonas
detectadas y los rostros difuminados.

Capturas y resultados de una ejecución real: [`DEMO_VIDEO.md`](DEMO_VIDEO.md).

## Dónde está cada entregable

| Entregable pedido | Dónde está |
|---|---|
| Código fuente de la solución | GitHub: [`app/`](../app) y [`run.py`](../run.py) |
| Instrucciones de instalación, configuración y ejecución | §1 de este documento, y [`RETO4_GUIA_USO.md`](RETO4_GUIA_USO.md) paso a paso |
| Descripción del enfoque de visión por computadora | §3 |
| Modelos, librerías, herramientas o servicios empleados | §3.1 y §3.2 |
| Descripción del flujo de procesamiento de video | §4 |
| Demostración funcional, video demostrativo, capturas o resultados | [`video-demostrativo.mp4`](video-demostrativo.mp4) · [`DEMO_VIDEO.md`](DEMO_VIDEO.md) con 7 capturas · CSV en [`resultados/`](resultados/) |
| Puntos críticos definidos y métricas generadas | §5 |

---

Aplicación web lista para ejecutar que analiza **la cámara de tu PC** y **videos que subas**,
**reconoce personas y objetos** (cada uno con su propio identificador de seguimiento),
**detecta solo las zonas críticas del espacio** —no vienen impuestas— y va **llenando una
base de datos** con lo que pasó y lo que está pasando: ocupación, entradas y salidas,
permanencia, inventario de objetos, alertas y resúmenes periódicos.

Además cruza esos datos de video con la **operación real de la oficina**: marcajes del
biométrico (`Datos_Biometrico_2.xlsx`) e historial de llamadas de RingCentral
(`RingCentral_History.xlsx`).

---

## 1. Puesta en marcha (3 pasos)

```bash
# 1) Dependencias
pip install -r requirements.txt

# 2) Verificar el entorno (opcional pero recomendado)
python run.py --check

# 3) Arrancar
python run.py
```

Se abre solo en <http://127.0.0.1:8000>. No hace falta configurar nada más: la base de datos
SQLite, las zonas de ejemplo y los datos operativos de `sample_data/` se cargan en el primer
arranque. El modelo YOLO (5 MB) se descarga automáticamente la primera vez y queda guardado
en `models/`.

| Comando | Para qué sirve |
|---|---|
| `python run.py` | Arranca la app y abre el navegador |
| `python run.py --port 9000` | Otro puerto |
| `python run.py --host 0.0.0.0` | Accesible desde otras máquinas de la red |
| `python run.py --check` | Diagnóstico de dependencias y del detector activo |
| `python scripts/video_demo.py` | Genera un video sintético de prueba en `data/uploads/` |

> **Instalación ligera (sin PyTorch):** `pip install -r requirements-lite.txt`.
> La app sigue funcionando con el detector de movimiento o con un modelo `.onnx`
> que coloques en `models/`.

### Requisitos
* Python 3.9 – 3.12
* ~1.5 GB de disco para PyTorch + YOLO (o ~150 MB en modo ligero)
* Navegador moderno (Chrome, Edge o Firefox). Para usar la cámara de la PC, el navegador
  exige contexto seguro: `localhost` funciona directamente; si sirves en otra máquina usa
  HTTPS o habilita el origen como seguro.

---

## 2. Qué hace cada pantalla

| Pantalla | Contenido |
|---|---|
| **Dashboard** | KPIs (personas ahora, ocupación promedio, pico, permanencia, eventos, alertas), ocupación en el tiempo, actividad por hora, ocupación por zona, tipos de evento, **objetos reconocidos**, alertas y últimos eventos |
| **Cámara en vivo** | Captura la webcam, dibuja personas y objetos con su ID sobre el video, muestra ocupación por zona, **inventario de objetos** en tiempo real y el flujo de eventos. También conecta una cámara del servidor o **IP/RTSP** |
| **Videos** | Subida por arrastre (multi-archivo), procesamiento en segundo plano con barra de progreso, resultado por sesión con métricas, zonas, eventos, personas seguidas y **video anotado descargable** |
| **Puntos críticos** | **Detección automática de zonas** (por escena o por actividad) + editor manual sobre un fondo tomado de la cámara o de una imagen; aforo, permanencia, tipo de zona, clases a reconocer y reglas globales |
| **Operación** | Cruce de la cámara con el biométrico y las llamadas: demanda vs. personal por hora, hallazgos automáticos, asistencia del día y retrasos |
| **Reportes** | Todos los eventos filtrables (rango, severidad, tipo, sesión, texto), personas seguidas, evidencia visual y exportación CSV |

---

## 3. Enfoque de visión por computadora

El pipeline es **detección → seguimiento → geometría de zonas → reglas → persistencia**.
Cada cuadro analizado recorre estas etapas:

```
Cuadro (webcam o video)
   │
   ├─▶ 1. DETECCIÓN         YOLO11n (Ultralytics) · ONNX vía OpenCV DNN · MOG2 (respaldo)
   │                        Clases: person + laptop, cell phone, chair, backpack, cup, tv…
   │
   ├─▶ 2. SEGUIMIENTO       Tracker propio por IoU + centroides (app/vision/tracker.py)
   │                        Dos instancias: personas (P<sesión>-0001…) y objetos
   │                        (P<sesión>-O-0001…). IDs anónimos, confirmación por
   │                        min_hits y cierre por max_age
   │
   ├─▶ 3. ZONAS             Polígonos normalizados (0..1) · punto de contacto con el piso
   │                        Entradas, salidas, ocupación instantánea y permanencia por track
   │                        Las zonas se pueden detectar automáticamente (ver 3.1)
   │
   ├─▶ 4. REGLAS            Personas: aforo, permanencia excesiva, aglomeración, zona
   │                        inactiva, actividad fuera de horario
   │                        Objetos: objeto nuevo, objeto retirado, objeto de valor sin
   │                        supervisión
   │
   └─▶ 5. PERSISTENCIA      Eventos al instante · foto de estado cada N s ·
                            resumen narrado cada minuto · tracks al cerrarse
```

**Decisiones técnicas y por qué:**

* **Detección por modelo, no por movimiento.** YOLO11n da cajas y clase con ~19–22 fps en CPU,
  suficiente para vigilancia operativa, y distingue personas de objetos y de cambios de luz,
  que es el punto débil de la sustracción de fondo.
* **Tracker propio en lugar del tracker del modelo.** Así el seguimiento es idéntico con
  cualquier backend (YOLO, ONNX o movimiento) y controlamos el ciclo de vida del track, que
  es lo que permite medir permanencia y trayectoria. Asociación *greedy* por IoU con
  confirmación (`min_hits`) para evitar falsos positivos y tolerancia a oclusiones
  (`max_age`).
* **Punto de contacto con el piso.** Para decidir si alguien está en una zona se usa el centro
  del borde inferior de la caja, no el centroide: es mucho más estable en perspectiva.
* **Coordenadas normalizadas.** Las zonas se guardan en 0..1, por lo que las mismas zonas
  sirven para la webcam, para un video 4K o para una cámara IP sin volver a dibujarlas.
* **Reloj de video vs. reloj de pared.** En videos, la permanencia se mide en *tiempo de video*
  (aunque se procese 10× más rápido) y el sello de tiempo se reconstruye desde el inicio de la
  sesión; en vivo se usa el reloj monótono. Las métricas son comparables entre ambos modos.
* **Degradación garantizada.** Si falta PyTorch o no hay red, el detector cae a ONNX y luego a
  MOG2. La app nunca queda inutilizable, solo cambia la precisión (el backend activo siempre
  se muestra en pantalla).

### Reconocimiento de objetos, no solo de personas

Por defecto el sistema **reconoce las 80 clases que conoce el modelo y las nombra en
español**: persona, laptop, silla, mochila, mesa, pantalla, taza, mochila, celular… En
cada cuadro produce una frase legible de lo que ve —*"3 personas y 2 tazones"*— que
aparece en la pantalla *Cámara en vivo*, en el resumen de cada video y en los resúmenes
periódicos que se guardan en la base.

Los nombres en español viven en `app/vision/labels.py`, con singular y plural correctos;
en la base de datos se guarda siempre la clase original del modelo (`bowl`), que es la
clave estable, y la traducción se aplica al mostrarla. En *Puntos críticos* se puede
desactivar "reconocer todo" y limitar la búsqueda a las clases que marques, útil en
escenas muy cargadas.

Cada objeto detectado:

* recibe su **propio identificador de seguimiento** (`P7-O-0003`) y se guarda en `tracks`
  con su duración en escena y las zonas por las que pasó;
* alimenta un **inventario** en vivo (cuántos hay ahora y cuántos distintos se han visto);
* dispara tres reglas propias:

| Evento | Cuándo |
|---|---|
| `objeto_nuevo` | Aparece un objeto que no estaba al inicio de la escena (tras un periodo de calentamiento, para no anunciar el mobiliario fijo) |
| `objeto_retirado` | Un objeto que llevaba más de 10 s en escena deja de verse |
| `objeto_sin_supervision` | Una laptop, mochila, bolso, maleta o teléfono queda sin ninguna persona en un radio configurable durante más de N minutos |

Las reglas de aforo y aglomeración siguen contando **solo personas**: los objetos no
inflan la ocupación.

### 3.1 Detección automática de puntos críticos

Las zonas no tienen por qué dibujarse a mano ni quedarse en las de ejemplo. El botón
*Detectar* de la pantalla **Puntos críticos** las propone de dos formas
(`app/vision/autozones.py`):

* **Por escena** — se detectan los elementos del lugar (sillas, mesas, monitores, laptops,
  personas) en una foto o en 6 cuadros repartidos de un video, se proyectan a una rejilla
  de 128×72, se dilatan para unir lo que está contiguo y cada componente conexa se
  convierte en polígono. El nombre sale de lo que domina el grupo: mesa grande + sillas +
  pantalla → *Sala de juntas*; sillas + laptops → *Área de trabajo*.
* **Por actividad** — se acumulan las trayectorias ya guardadas en un mapa de calor y se
  separan dos comportamientos con dos señales independientes: **densidad** (muestras por
  celda: quedarse concentra muestras) y **velocidad** (celdas recorridas por muestra: pasar
  las dispersa). Alta densidad → *Área de permanencia*; alta velocidad y baja densidad →
  *Pasillo / Acceso*.

Cada propuesta llega con su **justificación** ("4x chair, 1x dining table, 1x tv" o
"corredor de paso: 3.0 celdas por muestra"), un aforo y un umbral de permanencia
sugeridos. Se dibujan punteadas sobre el editor y **no se guardan hasta que se aceptan**:
el sistema propone, la persona decide.

### Modelos, librerías y herramientas

| Componente | Tecnología | Rol |
|---|---|---|
| Detección | **Ultralytics YOLO11n** (COCO, 80 clases) | Detección y nombrado de personas y objetos |
| Nombres | `app/vision/labels.py` | Traducción al español con singular/plural y frase de escena |
| Detección alterna | **OpenCV DNN + ONNX** | Mismo modelo sin PyTorch |
| Respaldo sin modelo | **OpenCV MOG2 + contornos** | Funciona offline, sin descargas |
| Seguimiento | Implementación propia (IoU + centroides) | IDs anónimos, permanencia, trayectoria |
| Geometría | `cv2.pointPolygonTest` | Pertenencia a zonas poligonales |
| Backend | **FastAPI + Uvicorn** (REST + WebSocket) | API y streaming de análisis |
| Base de datos | **SQLite (WAL)** | Persistencia sin servidor |
| Zonas automáticas | OpenCV (rejilla, componentes conexas, `approxPolyDP`) | Propuesta de puntos críticos |
| Frontend | HTML + CSS + JS puro, gráficas en `<canvas>` propias | Sin CDNs: funciona offline, tema claro/oscuro |
| Datos operativos | **openpyxl** | Importación de biométrico y RingCentral |

---

## 4. Flujo de procesamiento de video

**Cámara en vivo (navegador).** El navegador captura la webcam, reduce el cuadro a la
resolución elegida (480/640/960 px), lo comprime a JPEG y lo envía por **WebSocket**. El
servidor analiza y responde con un JSON (detecciones normalizadas, zonas, métricas, eventos)
que el navegador dibuja sobre el video. El envío es *pull*: solo se manda un cuadro nuevo
cuando llegó la respuesta del anterior, así nunca se acumula retraso. **No se guarda el video**,
solo métricas y capturas de eventos críticos.

**Videos subidos.** Se guardan en `data/uploads/` y se procesan en un pool de hilos
(2 simultáneos por defecto). Se aplica **muestreo de cuadros**: si el video es de 25 fps y el
objetivo de análisis son 6 fps, se analiza 1 de cada 4 cuadros. Esto permite procesar videos
largos rápido sin perder eventos, porque la permanencia se mide en tiempo de video. En
paralelo se genera un **video anotado** con zonas, cajas, IDs y rostros difuminados (si hay
`ffmpeg` en el sistema se reconvierte a H.264 para verlo dentro del navegador).

**Cámara IP / RTSP.** `POST /api/camera/start` con `{"source": "rtsp://usuario:clave@ip:554/stream"}`
abre la fuente en el servidor y publica un stream MJPEG anotado en `/api/camera/stream`.

---

## 5. Puntos críticos y métricas generadas

**Zonas** (editables en la pantalla *Puntos críticos*): nombre, tipo (`area`, `acceso`,
`restringida`), polígono, **aforo máximo**, **mínimo de personas** con su tolerancia y
umbral de permanencia. El mínimo es lo que convierte una zona en un *puesto que debe
estar atendido*: con `min_occupancy = 1`, la recepción que se queda sola dispara una
alerta y, al volver a cubrirse, el sistema registra cuántos minutos estuvo sin nadie
(acumulados por zona en el dashboard, columna *Sin cubrir*).
Zonas precargadas: Recepción, Área de trabajo, Sala de juntas y Pasillo / Acceso.

**Eventos que se registran**

| Tipo | Severidad | Cuándo se dispara |
|---|---|---|
| `zone_enter` / `zone_exit` | info | Una persona entra o sale de una zona (con permanencia acumulada) |
| `permanencia_excesiva` | warning / critical | Supera el umbral de minutos dentro de la zona |
| `aforo_excedido` | critical | La ocupación instantánea supera el máximo de la zona |
| `aglomeracion` | critical | Más de N personas simultáneas en el encuadre |
| `zona_inactiva` | warning | Zona sin actividad durante el horario laboral |
| `puesto_desatendido` | critical / warning | La zona baja de su **mínimo de personas** más tiempo del tolerado (recepción sin nadie, sala con menos gente de la requerida). Crítico si queda vacía |
| `puesto_atendido` | info | La zona vuelve a cubrirse, indicando cuánto tiempo estuvo sin cubrir |
| `objeto_nuevo` | info | Aparece en escena un objeto que antes no estaba, nombrado en español ("Reconocido en escena: mochila (P4-O-0003) en Recepción") |
| `objeto_retirado` | info / warning | Un objeto deja de verse (warning si es de valor) |
| `objeto_sin_supervision` | warning | Objeto de valor sin ninguna persona cerca |
| `actividad_fuera_horario` | warning | Presencia detectada fuera de la jornada configurada |
| `resumen` | info | Cada minuto: promedio y pico de personas, entradas por zona, eventos y alertas |

**Métricas disponibles**: personas simultáneas (instantánea, promedio y pico), personas únicas
(tracks confirmados), permanencia por persona y por zona, entradas/salidas por zona,
ocupación vs. aforo, índice de movimiento (proporción de píxeles que cambian), fps de
procesamiento y latencia por cuadro, **objetos únicos por clase con su permanencia en
escena** e inventario instantáneo.

---

## 6. Base de datos

SQLite en `data/officevision.db` (modo WAL, escrituras serializadas entre hilos).

| Tabla | Contenido |
|---|---|
| `sources` / `sessions` | Cada cámara o video analizado, con estado, progreso y métricas finales |
| `snapshots` | Foto del estado cada N segundos: personas, objetos, movimiento, ocupación por zona |
| `tracks` | Una fila por persona seguida: duración, cuadros, confianza, distancia recorrida, permanencia por zona y trayectoria |
| `events` | Entradas/salidas, alertas y resúmenes, con severidad, zona, ID de track y evidencia |
| `zones` | Puntos críticos configurados |
| `employees` / `attendance` | Nómina y marcajes del biométrico |
| `calls` | Historial de llamadas de RingCentral |

Todo es exportable a CSV desde *Reportes* o vía `GET /api/export/{events,snapshots,tracks,operacion}.csv`.

---

## 7. Integración y escalabilidad

* **API REST documentada** (OpenAPI en `/docs`): todo lo que hace la interfaz está disponible
  como endpoint, listo para un dashboard externo, un ERP o un bot de alertas.
* **WebSocket** `/ws/live` para consumir el análisis cuadro a cuadro desde otra aplicación.
* **Más cámaras**: cada sesión es independiente (detector, tracker y zonas propios). Se pueden
  abrir varias pestañas en vivo o varias fuentes RTSP; los hilos de video se limitan con
  `max_concurrent_jobs`.
* **Más modelos**: `app/vision/detector.py` es un registro de backends. Añadir un modelo nuevo
  (pose, EPP, ocupación de escritorios, conteo de vehículos) es implementar `detect()` y
  devolver `Detection`. Todo lo demás —tracking, zonas, reglas, base de datos— se reutiliza.
* **Más clases sin tocar código**: el selector de clases de la pantalla *Puntos críticos*
  cambia en caliente qué elementos se reconocen, de las 80 clases del modelo.
* **Nuevo espacio físico**: en una cámara nueva, la detección automática de zonas propone
  los puntos críticos en segundos en lugar de redibujarlos a mano.
* **Migrar a otro motor de datos**: las escrituras pasan por `app/db.py`; cambiar SQLite por
  PostgreSQL o TimescaleDB es sustituir esa capa.
* **GPU**: `"device": "0"` en `config.json` (o desde `POST /api/config`) usa CUDA sin tocar código.

---

## 8. Privacidad y seguridad

* **Sin reconocimiento facial y sin identificación de personas.** Los IDs (`P3-0007`) son
  anónimos y se reinician en cada sesión: sirven para contar y medir, no para identificar.
* **No se almacena video de la cámara en vivo.** Solo métricas, y capturas JPG **únicamente**
  en eventos de severidad warning o critical.
* **Difuminado de rostros** activado por defecto en toda imagen anotada (`blur_faces`).
* **Retención configurable**: las capturas se borran automáticamente a los 15 días
  (`snapshot_retention_days`).
* **Todo queda en local**: no hay servicios externos ni telemetría; la app escucha en
  `127.0.0.1` salvo que se pida lo contrario.
* Los datos de nómina, asistencia y llamadas viven en la misma base local; si se expone el
  servidor en red conviene ponerlo detrás de un proxy con autenticación.

---

## 9. Rendimiento medido

Medido en este proyecto sobre CPU de 4 núcleos, sin GPU:

| Resolución | YOLO11n | Modo movimiento |
|---|---|---|
| 640×360 | 52 ms/cuadro (**19 fps**) | 8 ms (124 fps) |
| 960×540 | 53 ms/cuadro (**19 fps**) | 19 ms (53 fps) |
| 1280×720 | 44 ms/cuadro (**22 fps**) | 34 ms (29 fps) |

Un video de 30 s a 20 fps (600 cuadros) se procesa con muestreo a 6 fps en ~13 s, generando
video anotado, 200 cuadros analizados, tracks, eventos y resúmenes. La latencia extremo a
extremo en vivo (captura → análisis → dibujo) se mantiene por debajo de 100 ms en 640 px.

---

## 10. Limitaciones y mejoras futuras

**Limitaciones actuales**
* Una cámara mal ubicada (contrapicado extremo, mucha oclusión) degrada el conteo: el tracker
  puede dividir una persona en dos IDs tras una oclusión larga.
* El modo de respaldo por movimiento cuenta de más cuando hay cambios de iluminación.
* Sin re-identificación entre cámaras: una persona que pasa de una cámara a otra es un track nuevo.
* El cruce con el biométrico es a nivel agregado por hora (por diseño: no se identifica a nadie).

* La detección automática de zonas propone, no adivina la intención del negocio: un
  pasillo muy transitado y una fila de espera se parecen mucho en los datos.
* El reconocimiento de objetos hereda los límites del modelo COCO: reconoce categorías
  genéricas (laptop, silla, mochila), no modelos ni pertenencias concretas.

**Mejoras previstas**
* Re-identificación por apariencia (OSNet/FastReID) para trayectorias entre cámaras.
* Mapa de calor acumulado y planos en planta (homografía) para métricas en metros.
* Detección de posturas (caídas, personas en el piso) y de EPP con un modelo secundario.
* Alertas salientes por correo, Teams o webhook, y agregados por turno en tablas materializadas.
* Modelo más grande (`yolo11s/m`) o GPU para escenas con mucha gente.

---

## 11. Estructura del proyecto

```
proyectos-IA/
├── run.py                     OfficeVision AI (video): arranque y diagnóstico
├── run_documentos.py          DocuFlow AI (documentos): arranque y diagnóstico
├── requirements.txt           Dependencias (lite en requirements-lite.txt)
├── config.json                Configuración (se crea sola, editable en caliente)
├── app/
│   ├── main.py                App FastAPI, páginas y arranque
│   ├── api.py                 API REST + WebSocket
│   ├── pipeline.py            Analyzer: cuadro → eventos → base de datos
│   ├── workers.py             Cámara en vivo, cámara IP y trabajos de video
│   ├── business.py            Biométrico + RingCentral y análisis cruzado
│   ├── db.py                  Esquema y acceso a SQLite
│   ├── config.py              Configuración persistente
│   ├── vision/
│   │   ├── detector.py        Backends YOLO / ONNX / movimiento
│   │   ├── tracker.py         Seguimiento multi-objeto (personas y objetos)
│   │   ├── labels.py          Nombres en espanol de las 80 clases
│   │   ├── autozones.py       Deteccion automatica de puntos criticos
│   │   └── zones.py           Polígonos, aforo y permanencia
│   ├── templates/             6 páginas (Jinja2)
│   └── static/                CSS y JS (gráficas propias en canvas)
├── docsai/                    DocuFlow AI: aplicación de documentos completa
│   ├── main.py · api.py       Servidor, páginas y endpoints propios
│   ├── config.py · db.py      Configuración y base de datos propias
│   ├── extract.py             Texto de PDF, DOCX, imágenes, correos (+OCR)
│   ├── entities.py            Expediente, fechas, partes, montos, emisor
│   ├── classify.py            Reglas ponderadas + Naive Bayes entrenable
│   ├── naming.py              Convención de nombres y carpetas
│   ├── pipeline.py            Flujo completo y cola de trabajo
│   └── templates/ · static/   Interfaz propia
├── contactos/                 Directorio vivo: aplicación de contactos completa
│   ├── main.py · api.py       Servidor, siete páginas y endpoints propios
│   ├── config.py · db.py      Configuración y base de datos propias
│   ├── modelo.py              Personas, identificadores, casos e hitos
│   ├── fuentes.py             Importa nómina, llamadas y documentos
│   ├── busqueda.py            Una sola caja, con el porqué de cada resultado
│   ├── duplicados.py          Detección explicada y fusión reversible
│   ├── extraccion.py          Alta pegando una firma de correo
│   └── templates/ · static/   Interfaz propia
├── scripts/video_demo.py      Generador de video sintético de prueba
├── scripts/documentos_demo.py Generador de documentos de ejemplo
├── scripts/contactos_demo.py  Arma el directorio desde cero y mide el resultado
├── pruebas/                   Pruebas de trafico, carga y tolerancia a errores
│   ├── carga.py               Motor: llegadas de Poisson, 1 o N procesos, percentiles
│   ├── escenarios.py          La mezcla de trafico y los 26 casos borde
│   ├── monitor.py             CPU, memoria, hilos y conexiones de cada servidor
│   ├── orquesta.py            Ciclo de vida de los servidores y los 7 escenarios
│   └── reporte.py             Graficas de latencia, caudal, errores y recursos
├── sample_data/               Biométrico y RingCentral de ejemplo
├── docs/                      Arquitectura y guía de uso
└── data/                      Base de datos, subidas, salidas y capturas
```

---


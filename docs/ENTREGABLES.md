# Entregables y criterios, reto por reto

**Cada reto es una entrega independiente.** Esta tabla dice dónde está cada cosa, para
que puedas entregar uno solo sin arrastrar los demás.

| Reto | Proyecto | Se arranca con | Documento único |
|---|---|---|---|
| 4 | OfficeVision AI (video) | `python run.py` | [`RETO4_VIDEO.md`](RETO4_VIDEO.md) |
| 5 | DocuFlow AI (documentos) | `python run_documentos.py` | [`RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) |
| 6 | Directorio vivo (contactos) | `python run_contactos.py` | [`RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) |
| 7 | Pruebas de carga | `python run_pruebas.py` | [`RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) |

---

## Reto 4 — Análisis de video con IA y visión por computadora

Aplicación: **OfficeVision AI** (`python run.py`).

### Entregables

| Entregable | Dónde está |
|---|---|
| Código fuente en GitHub | `app/` (aplicación), `run.py` (arranque), `scripts/video_demo.py` |
| Instrucciones de instalación, configuración y ejecución | [`docs/RETO4_VIDEO.md`](RETO4_VIDEO.md) §Puesta en marcha · [`docs/RETO4_GUIA_USO.md`](RETO4_GUIA_USO.md) · `python run.py --check` |
| Descripción del enfoque de visión por computadora | [`docs/RETO4_VIDEO.md`](RETO4_VIDEO.md) §Enfoque · [`docs/RETO4_ARQUITECTURA.md`](RETO4_ARQUITECTURA.md) §2 |
| Modelos, librerías, herramientas empleadas | [`docs/RETO4_VIDEO.md`](RETO4_VIDEO.md) §Modelos, librerías y herramientas · [`docs/RETO4_ARQUITECTURA.md`](RETO4_ARQUITECTURA.md) §3 |
| Descripción del flujo de procesamiento de video | [`docs/RETO4_VIDEO.md`](RETO4_VIDEO.md) §Flujo · [`docs/RETO4_ARQUITECTURA.md`](RETO4_ARQUITECTURA.md) §2 |
| Demostración funcional, video demostrativo, capturas o resultados procesados | **[`docs/video-demostrativo.mp4`](video-demostrativo.mp4)** (66 s de análisis real) · [`docs/DEMO_VIDEO.md`](DEMO_VIDEO.md) con 7 capturas · CSV en [`docs/resultados/`](resultados/) |
| Puntos críticos definidos y métricas generadas | [`docs/RETO4_VIDEO.md`](RETO4_VIDEO.md) §5 · [`docs/DEMO_VIDEO.md`](DEMO_VIDEO.md) §5 |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Enfoque técnico** | Pipeline detección → seguimiento → zonas → reglas → persistencia, con tres backends en cascada (YOLO11n / ONNX / MOG2) para que nunca deje de funcionar. Tracker propio para que el seguimiento sea idéntico con cualquier modelo. |
| **Detección o reconocimiento** | Personas y las 80 clases COCO, nombradas en español, cada una con identificador de seguimiento propio. Eventos de objeto nuevo, retirado y sin supervisión. |
| **Gestión de puntos críticos** | Zonas poligonales normalizadas, **detectadas automáticamente** por escena o por actividad, con aforo máximo, mínimo de personas, permanencia y conteo de accesos. |
| **Precisión del sistema** | Evaluado sobre grabación real: 12 personas únicas, pico 5, permanencia media 19,8 s. Punto de contacto con el piso para decidir zona (estable en perspectiva); confirmación por `min_hits` y tolerancia a oclusión por `max_age`. |
| **Rendimiento** | 44–53 ms por cuadro (19–22 fps) en CPU de 4 núcleos; 81 ms de latencia extremo a extremo en vivo. Muestreo de cuadros configurable para videos largos (en la demo, 1 de cada 10 sobre 59,9 fps). |
| **Utilidad de los resultados** | Alertas accionables con evidencia visual, resúmenes narrados por minuto y cruce con biométrico y llamadas para decisiones de cobertura. |
| **Arquitectura e integración** | API REST documentada en `/docs`, WebSocket de análisis, exportación CSV, cámaras IP/RTSP, registro de detectores para añadir modelos y capa de datos aislada. [`docs/RETO4_ARQUITECTURA.md`](RETO4_ARQUITECTURA.md) §8. |
| **Documentación** | README + arquitectura + guía de uso + demostración, con limitaciones y mejoras declaradas. |

---

## Reto 5 — Clasificación, organización y nombramiento de documentos

Aplicación: **DocuFlow AI** (`python run_documentos.py`).

### Entregables

| Entregable | Dónde está |
|---|---|
| Código fuente de la solución | `docsai/` (aplicación completa), `run_documentos.py`, `scripts/documentos_demo.py` |
| Instrucciones de instalación, configuración y ejecución | [`docs/RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) §Puesta en marcha · `python run_documentos.py --check` |
| Descripción del flujo de procesamiento documental | [`docs/RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) §1 |
| Convención de nombramiento propuesta | [`docs/RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) §4 · configurable desde *Reglas y nombres* |
| Uso de IA, OCR, NLP, reglas, modelos o herramientas | [`docs/RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) §5 |
| Demostración y resultados procesados | [`docs/DEMO_DOCUMENTOS.md`](DEMO_DOCUMENTOS.md) · [`docs/resultados/documentos.csv`](resultados/documentos.csv) |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Análisis documental** | Extracción por formato con degradación (PyMuPDF, OCR, python-docx, .eml, texto) y datos clave con su procedencia: expediente, fecha, partes, tribunal, emisor, montos, reclamo y póliza. |
| **Clasificación** | 14 categorías definidas por *por qué existe el documento en el expediente*, no por su formato. Reglas ponderadas que explican su decisión + Naive Bayes entrenado con las correcciones. 13/13 correctas en la prueba. |
| **Nombramiento automatizado** | `{fecha}_{CATEGORIA}_{expediente}_{descriptor}`, fecha ISO para que el orden alfabético sea cronológico, marcadores explícitos para lo que falte, versionado ante colisión y plantilla configurable. |
| **Uso adecuado de IA** | OCR sólo cuando hace falta; reglas donde la explicabilidad importa; modelo entrenable donde aporta; hash para duplicados. Se justifica también **por qué no un LLM de entrada** y dónde sí tendría sentido. |
| **Automatización del proceso** | De la carga al archivado sin intervención: carpeta vigilada o subida web, cola en segundo plano, archivado en carpetas y revisión humana sólo para lo dudoso. 100 % automático en la prueba. |
| **Arquitectura e integración** | Aplicación independiente con API REST completa, exportación CSV, carpeta vigilada para escáner o carpeta de red y puntos de extensión documentados para categorías, formatos y almacenamiento. |
| **Documentación** | [`docs/RETO5_DOCUMENTOS.md`](RETO5_DOCUMENTOS.md) cubre enfoque, categorías, convención, métricas, privacidad, limitaciones y mejoras. |

---

## Reto 6 — Análisis crítico y rediseño de plataformas de contactos

Entregable documental + **aplicación que corre**: [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md)
y `python run_contactos.py` (puerto 8200).

### Entregables

| Entregable | Dónde está |
|---|---|
| Documento con el análisis de plataformas existentes | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §2 (Google, Apple, Outlook, software jurídico y **gestión documental**: SharePoint, iManage, NetDocuments) y §3 (los nueve supuestos de diseño) |
| Listado de funcionalidades o flujos a eliminar, simplificar o rediseñar | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §4, en cuatro tablas: eliminar, simplificar, rediseñar y mantener |
| Propuesta de experiencia o flujo mejorado | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §5 (los seis flujos) y §6: **la aplicación construida y funcionando**, con capturas y resultados medidos sobre los datos reales del despacho |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Simplificación** | Ocho funciones eliminadas y siete flujos simplificados, cada uno con el riesgo que se asume escrito. Se quita la lista paralela de "otros contactos", los campos de catálogo fijo, los grupos manuales, la fusión masiva, la importación con mapeo de 40 columnas y —del lado documental— **elegir carpeta al guardar** y **escribir metadatos a mano**. |
| **Innovación** | Cuatro ideas que ninguna de las plataformas analizadas tiene, **implementadas, no descritas**: la ficha como **línea de tiempo** en lugar de formulario, los **roles derivados** de los documentos ya clasificados (cero mantenimiento), la vista **"quién es quién en el expediente"** y el **documento archivado solo que aparece en la ficha de quien lo firmó**, que cierra la separación entre libreta y gestor documental. El alta pegando una firma reutiliza el extractor del Reto 5. |
| **Justificación** | Cada crítica se apoya en documentación oficial o en foros donde los usuarios describen la fricción (§9), y cada cambio propuesto declara su riesgo (§8) y cómo se mediría su impacto (§7). Cinco cambios están medidos sobre los datos reales; el resto se presenta como hipótesis a validar, y la falta de pruebas con usuarios se declara como la limitación principal. |

---

## Reto 7 — Pruebas de tráfico, carga y actividad automatizada

Entregable: [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) y el paquete `pruebas/`
(`python run_pruebas.py`).

**El sistema puesto a prueba es ContactHub**, la agenda de contactos con API REST,
JWT y SQLite. El arnés no importa su código, no abre su base de datos y no lee su
configuración: habla con él sólo por HTTP.

### Entregables

| Entregable | Dónde está |
|---|---|
| Scripts y configuración de las pruebas, con instrucciones para reproducirlas | `pruebas/` (6 módulos) y `run_pruebas.py`; instrucciones en [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §2 y §3. Un solo comando arranca, entra, siembra, mide y limpia |
| Instrucciones de instalación, configuración y ejecución de la solución | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §3: un comando, más las variables de entorno por si ContactHub está en otra máquina. Sin herramientas externas |
| Descripción del escenario de prueba diseñado y su justificación | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §1: la mezcla de tráfico sale de la hora punta real del historial de la centralita (56 llamadas) y del tamaño real de la plantilla (26 personas), operación por operación |
| Resultados de las pruebas ejecutadas: logs, métricas, reportes, gráficos o capturas | §4 a §10. **Logs**: transcripción completa de la sesión ([`carga-registro.txt`](resultados/carga-registro.txt)), extracto del registro del propio ContactHub con las trazas que sostienen el diagnóstico ([`carga-log-contacthub.txt`](resultados/carga-log-contacthub.txt)) y las muestras en crudo, una fila por petición. **Métricas**: 12 tablas y [`carga-informe.json`](resultados/carga-informe.json). **Gráficos**: 6 |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Diseño de las pruebas** | El caudal nominal (0,090 pet./s = 325 peticiones en la hora punta) se deriva de datos reales, operación por operación, y se dice en voz alta lo que eso significa: la demanda de este despacho es diminuta, y las cifras de tres dígitos son margen, no expectativa. Nueve escenarios: arranque en frío, ráfaga, escrituras concurrentes, sólo consultas caras, resistencia, importación pesada en paralelo, 43 casos borde, integridad y escalada hasta el colapso. Llegadas de Poisson en vez de bucle cerrado, y se mide la espera del usuario para no caer en *coordinated omission*. La escalada va **la última** a propósito: es el único escenario que destruye el servicio. |
| **Implementación de las pruebas** | Un comando hace todo: localiza o arranca ContactHub, se registra y entra por el endpoint público, **renueva el token** antes de que caduque, siembra 2 000 contactos por el propio importador de CSV, mide, dibuja y borra lo que escribió. Cada escenario comprueba que el servicio está en pie antes de medir. Semilla fija; `--rapido`, `--solo`, `--ruta` y `--contactos` para iterar. |
| **Monitoreo y análisis** | `psutil` muestrea cada segundo CPU, memoria, hilos y conexiones. Eso permitió **atribuir la saturación**: durante el colapso la CPU estaba al 19 % de media, lo que descarta la falta de máquina y apunta a un recurso bloqueado. El volcado de pila con `py-spy` lo confirmó: 40 de 44 hilos parados esperando una conexión a la base, dentro de la dependencia de autenticación. La corrección propuesta se probó y se midió. |
| **Documentación** | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) explica el escenario y su porqué, los resultados con sus tablas y gráficas, **los dos defectos de ContactHub con causa raíz y corrección probada**, **los ocho fallos de la propia prueba** —con lo que decían y lo que pasaba de verdad—, una hipótesis mía que resultó falsa y por qué la descarté, y siete limitaciones declaradas (§10), incluida que la fuga de memoria no está descartada, sólo no medida. |

---

## Nota sobre los datos de prueba

No se recibieron las carpetas `Desktop/Hackathon/Reto 4/Recursos` ni
`Desktop/Hackathon/Reto 5/Documentos`. La evaluación se hizo con:

* **Video**: grabaciones públicas de personas en movimiento y un generador de
  video sintético (`scripts/video_demo.py`) para probar el flujo sin cámara.
* **Documentos**: una demanda federal real aportada como muestra
  (`doc_0011.pdf`, no incluida en el repositorio por contener datos personales)
  y 12 documentos representativos generados por `scripts/documentos_demo.py`.

Ambas aplicaciones procesan las carpetas reales sin ningún cambio: basta subir
los archivos desde la interfaz o dejarlos en `data/documentos/entrada`.

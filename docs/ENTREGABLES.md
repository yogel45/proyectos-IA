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
| Demostración funcional, capturas o resultados procesados | [`docs/DEMO_VIDEO.md`](DEMO_VIDEO.md) · CSV en [`docs/resultados/`](resultados/) · video anotado descargable desde la app |
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
| Documento con el análisis de plataformas existentes | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §2 (Google, Apple, Outlook y software jurídico) y §3 (supuestos de diseño) |
| Listado de funcionalidades o flujos a eliminar, simplificar o rediseñar | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §4, en cuatro tablas: eliminar, simplificar, rediseñar y mantener |
| Propuesta de experiencia o flujo mejorado | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §5 (los cinco flujos) y §6: **la aplicación construida y funcionando**, con capturas y resultados medidos sobre los datos reales del despacho |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Simplificación** | Seis funciones eliminadas y cinco flujos simplificados, cada uno con el riesgo que se asume escrito. Se quita la lista paralela de "otros contactos", los campos de catálogo fijo, los grupos manuales, la fusión masiva y la importación con mapeo de 40 columnas. |
| **Innovación** | Tres ideas que ninguna de las plataformas analizadas tiene, **implementadas, no descritas**: la ficha como **línea de tiempo** en lugar de formulario, los **roles derivados** de los documentos ya clasificados (cero mantenimiento) y la vista **"quién es quién en el expediente"**. El alta pegando una firma reutiliza el extractor del Reto 5. |
| **Justificación** | Cada crítica se apoya en documentación oficial o en foros donde los usuarios describen la fricción (§9), y cada cambio propuesto declara su riesgo (§8) y cómo se mediría su impacto (§7). Tres cambios están medidos sobre los datos reales; el resto se presenta como hipótesis a validar, y la falta de pruebas con usuarios se declara como la limitación principal. |

---

## Reto 7 — Pruebas de tráfico, carga y actividad automatizada

Entregable: [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) y el paquete `pruebas/`
(`python run_pruebas.py`).

### Entregables

| Entregable | Dónde está |
|---|---|
| Scripts y configuración de las pruebas, con instrucciones para reproducirlas | `pruebas/` (5 módulos) y `run_pruebas.py`; instrucciones en [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §2 y §3. Un solo comando arranca, mide y limpia |
| Instrucciones de instalación, configuración y ejecución de la solución | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §3: un solo comando instala, arranca lo que haga falta y ejecuta. Sin herramientas externas |
| Descripción del escenario de prueba diseñado y su justificación | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) §1: la carga sale de medir la hora pico real del historial de llamadas (56 llamadas), no de una cifra inventada |
| Resultados de las pruebas ejecutadas: logs, métricas, reportes, gráficos o capturas | §5 a §7. **Logs**: transcripción completa de la sesión ([`carga-registro.txt`](resultados/carga-registro.txt)), registro de 7 952 peticiones una por fila ([`carga-peticiones-x245.csv`](resultados/carga-peticiones-x245.csv)) y salida de cada servidor. **Métricas**: 10 tablas y [`carga-informe.json`](resultados/carga-informe.json). **Gráficos**: 7. **Capturas**: 3 pantallas tomadas mientras el sistema estaba bajo carga (§5.10). La sesión se repitió dos veces y se comparan (§5.9) |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Diseño de las pruebas** | El caudal nominal (1,63 pet./s) se deriva de datos reales: 56 llamadas en la hora pico de 24 días, 25 empleados, 8 paneles refrescando cada 5 s. Siete escenarios que cubren carga sostenida, ráfaga, escritura concurrente, resistencia, trabajo pesado en paralelo, arranque en frío y 26 casos borde. Llegadas de Poisson en vez de bucle cerrado, y se mide la espera del usuario (no sólo la del servidor) para no caer en *coordinated omission*. |
| **Implementación de las pruebas** | Un comando (`python run_pruebas.py`) hace todo: levanta lo que no esté corriendo, respeta lo que sí, mide, dibuja y **borra los datos que la propia prueba escribió**. Semilla fija para que sea repetible; `--rapido`, `--solo` y `--sin-video` para iterar. Sin dependencias nuevas más allá de `psutil` y `matplotlib`. |
| **Monitoreo y análisis** | `psutil` muestrea cada segundo CPU, memoria, hilos y conexiones de cada servidor, con los procesos hijos incluidos. Eso permitió **atribuir la saturación**: un proceso al 100 % de un núcleo mientras los otros tres están ociosos, es decir un trabajador de uvicorn, y no falta de máquina. También permitió descubrir que el primer generador era el cuello de botella y descartar una fuga de memoria (0 MB de deriva en 120 s). |
| **Documentación** | [`docs/RETO7_PRUEBAS.md`](RETO7_PRUEBAS.md) explica el escenario y su porqué, los resultados con sus tablas y gráficas, **los cuatro fallos que las pruebas encontraron y cómo se arreglaron**, la decisión de no usar varios trabajadores de uvicorn y por qué, y siete limitaciones declaradas (§9), incluida la más incómoda: el primer intento de medición estaba mal y por qué. |

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

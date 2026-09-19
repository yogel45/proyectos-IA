# Entregables y criterios de evaluación

Dónde está cubierto cada punto que piden los dos retos. Las referencias son a
archivos de este repositorio.

---

## Reto 4 — Análisis de video con IA y visión por computadora

Aplicación: **OfficeVision AI** (`python run.py`).

### Entregables

| Entregable | Dónde está |
|---|---|
| Código fuente en GitHub | `app/` (aplicación), `run.py` (arranque), `scripts/video_demo.py` |
| Instrucciones de instalación, configuración y ejecución | [`README.md`](../README.md) §Puesta en marcha · [`docs/GUIA_USO.md`](GUIA_USO.md) · `python run.py --check` |
| Descripción del enfoque de visión por computadora | [`README.md`](../README.md) §Enfoque · [`docs/ARQUITECTURA.md`](ARQUITECTURA.md) §2 |
| Modelos, librerías, herramientas empleadas | [`README.md`](../README.md) §Modelos, librerías y herramientas · [`docs/ARQUITECTURA.md`](ARQUITECTURA.md) §3 |
| Descripción del flujo de procesamiento de video | [`README.md`](../README.md) §Flujo · [`docs/ARQUITECTURA.md`](ARQUITECTURA.md) §2 |
| Demostración funcional, capturas o resultados procesados | [`docs/DEMOSTRACION.md`](DEMOSTRACION.md) §1 · CSV en [`docs/resultados/`](resultados/) · video anotado descargable desde la app |
| Puntos críticos definidos y métricas generadas | [`README.md`](../README.md) §Puntos críticos y métricas · [`docs/DEMOSTRACION.md`](DEMOSTRACION.md) §1.5 |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Enfoque técnico** | Pipeline detección → seguimiento → zonas → reglas → persistencia, con tres backends en cascada (YOLO11n / ONNX / MOG2) para que nunca deje de funcionar. Tracker propio para que el seguimiento sea idéntico con cualquier modelo. |
| **Detección o reconocimiento** | Personas y las 80 clases COCO, nombradas en español, cada una con identificador de seguimiento propio. Eventos de objeto nuevo, retirado y sin supervisión. |
| **Gestión de puntos críticos** | Zonas poligonales normalizadas, **detectadas automáticamente** por escena o por actividad, con aforo máximo, mínimo de personas, permanencia y conteo de accesos. |
| **Precisión del sistema** | Evaluado sobre grabación real: 12 personas únicas, pico 5, permanencia media 19,8 s. Punto de contacto con el piso para decidir zona (estable en perspectiva); confirmación por `min_hits` y tolerancia a oclusión por `max_age`. |
| **Rendimiento** | 44–53 ms por cuadro (19–22 fps) en CPU de 4 núcleos; 81 ms de latencia extremo a extremo en vivo. Muestreo de cuadros configurable para videos largos (en la demo, 1 de cada 10 sobre 59,9 fps). |
| **Utilidad de los resultados** | Alertas accionables con evidencia visual, resúmenes narrados por minuto y cruce con biométrico y llamadas para decisiones de cobertura. |
| **Arquitectura e integración** | API REST documentada en `/docs`, WebSocket de análisis, exportación CSV, cámaras IP/RTSP, registro de detectores para añadir modelos y capa de datos aislada. [`docs/ARQUITECTURA.md`](ARQUITECTURA.md) §8. |
| **Documentación** | README + arquitectura + guía de uso + demostración, con limitaciones y mejoras declaradas. |

---

## Reto 5 — Clasificación, organización y nombramiento de documentos

Aplicación: **DocuFlow AI** (`python run_documentos.py`).

### Entregables

| Entregable | Dónde está |
|---|---|
| Código fuente de la solución | `docsai/` (aplicación completa), `run_documentos.py`, `scripts/documentos_demo.py` |
| Instrucciones de instalación, configuración y ejecución | [`docs/DOCUMENTOS.md`](DOCUMENTOS.md) §Puesta en marcha · `python run_documentos.py --check` |
| Descripción del flujo de procesamiento documental | [`docs/DOCUMENTOS.md`](DOCUMENTOS.md) §1 |
| Convención de nombramiento propuesta | [`docs/DOCUMENTOS.md`](DOCUMENTOS.md) §4 · configurable desde *Reglas y nombres* |
| Uso de IA, OCR, NLP, reglas, modelos o herramientas | [`docs/DOCUMENTOS.md`](DOCUMENTOS.md) §5 |
| Demostración y resultados procesados | [`docs/DEMOSTRACION.md`](DEMOSTRACION.md) §2 · [`docs/resultados/documentos.csv`](resultados/documentos.csv) |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Análisis documental** | Extracción por formato con degradación (PyMuPDF, OCR, python-docx, .eml, texto) y datos clave con su procedencia: expediente, fecha, partes, tribunal, emisor, montos, reclamo y póliza. |
| **Clasificación** | 14 categorías definidas por *por qué existe el documento en el expediente*, no por su formato. Reglas ponderadas que explican su decisión + Naive Bayes entrenado con las correcciones. 13/13 correctas en la prueba. |
| **Nombramiento automatizado** | `{fecha}_{CATEGORIA}_{expediente}_{descriptor}`, fecha ISO para que el orden alfabético sea cronológico, marcadores explícitos para lo que falte, versionado ante colisión y plantilla configurable. |
| **Uso adecuado de IA** | OCR sólo cuando hace falta; reglas donde la explicabilidad importa; modelo entrenable donde aporta; hash para duplicados. Se justifica también **por qué no un LLM de entrada** y dónde sí tendría sentido. |
| **Automatización del proceso** | De la carga al archivado sin intervención: carpeta vigilada o subida web, cola en segundo plano, archivado en carpetas y revisión humana sólo para lo dudoso. 100 % automático en la prueba. |
| **Arquitectura e integración** | Aplicación independiente con API REST completa, exportación CSV, carpeta vigilada para escáner o carpeta de red y puntos de extensión documentados para categorías, formatos y almacenamiento. |
| **Documentación** | [`docs/DOCUMENTOS.md`](DOCUMENTOS.md) cubre enfoque, categorías, convención, métricas, privacidad, limitaciones y mejoras. |

---

## Reto 6 — Análisis crítico y rediseño de plataformas de contactos

Entregable documental + prototipo: [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) y
[`prototipo-contactos/`](../prototipo-contactos/).

### Entregables

| Entregable | Dónde está |
|---|---|
| Documento con el análisis de plataformas existentes | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §2 (Google, Apple, Outlook y software jurídico) y §3 (supuestos de diseño) |
| Listado de funcionalidades o flujos a eliminar, simplificar o rediseñar | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §4, en cuatro tablas: eliminar, simplificar, rediseñar y mantener |
| Propuesta de experiencia o flujo mejorado | [`docs/RETO6_CONTACTOS.md`](RETO6_CONTACTOS.md) §5 y **prototipo navegable** en `prototipo-contactos/index.html` (§6, con capturas) |

### Criterios de evaluación

| Criterio | Cómo se atiende |
|---|---|
| **Simplificación** | Seis funciones eliminadas y cinco flujos simplificados, cada uno con el riesgo que se asume escrito. Se quita la lista paralela de "otros contactos", los campos de catálogo fijo, los grupos manuales, la fusión masiva y la importación con mapeo de 40 columnas. |
| **Innovación** | Tres ideas que ninguna de las plataformas analizadas tiene: la ficha como **línea de tiempo** en lugar de formulario, los **roles derivados** de los documentos ya clasificados (cero mantenimiento) y la vista **"quién es quién en el expediente"**. El alta pegando una firma reutiliza el extractor del Reto 5. |
| **Justificación** | Cada crítica se apoya en documentación oficial o en foros donde los usuarios describen la fricción (§9), y cada cambio propuesto declara su riesgo (§8) y cómo se mediría su impacto (§7). Las estimaciones se presentan como hipótesis a validar, no como resultados. |

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

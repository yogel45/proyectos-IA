# Clasificación, organización y nombramiento automático de documentos

**DocuFlow AI** es una aplicación independiente que recibe documentos de cualquier
origen, entiende qué son, extrae los datos que los identifican, les pone un nombre
consistente y los archiva en una estructura de carpetas predecible.

**Reto 5.** Proyecto independiente: **este documento se lee solo**, no hace falta
ninguno de los otros del repositorio.

DocuFlow AI tiene su propio servidor, su propia base de datos
(`data/documentos/documentos.db`), su propia configuración (`config_documentos.json`) y
su propia interfaz. **No importa código de ningún otro proyecto** y puede correr a la vez
que ellos, en su propio puerto.

## Puesta en marcha

```bash
pip install -r requirements.txt
python run_documentos.py --check     # diagnostico (opcional)
python run_documentos.py             # http://127.0.0.1:8100
```

Se abre solo en <http://127.0.0.1:8100>. Para probarlo sin documentos propios:

```bash
python scripts/documentos_demo.py    # genera ejemplos en data/documentos/entrada
```

y en la **Bandeja** pulsa *Procesar carpeta de entrada*.

| Comando | Para qué |
|---|---|
| `python run_documentos.py` | Arranca la app y abre el navegador |
| `python run_documentos.py --port 9100` | Otro puerto |
| `python run_documentos.py --host 0.0.0.0` | Accesible desde la red local |
| `python run_documentos.py --check` | Diagnóstico de dependencias, OCR y configuración |

Probado sobre documentos reales de un despacho: demandas federales (FTCA),
citaciones, mociones, órdenes, reclamaciones Standard Form 95, reportes de
accidente, expedientes médicos, facturas, pólizas, contratos, declaraciones
juradas y correspondencia.

---

## 1. Flujo de procesamiento

```
Archivo (subida web o carpeta vigilada data/documentos/entrada)
   │
   ├─▶ 1. HUELLA          SHA-256 del contenido → duplicado exacto se marca
   │                       y se enlaza al original, sin volver a archivarlo
   │
   ├─▶ 2. EXTRACCIÓN      PDF nativo (PyMuPDF) · PDF escaneado → OCR (Tesseract)
   │                       DOCX (python-docx) · EML (stdlib) · imágenes → OCR
   │                       TXT/CSV/HTML con detección de codificación
   │
   ├─▶ 3. DATOS CLAVE     Expediente, fecha del documento, partes, tribunal,
   │                       emisor, montos, números de reclamo/póliza/factura,
   │                       correos y teléfonos                (entities.py)
   │
   ├─▶ 4. CLASIFICACIÓN   Reglas ponderadas + modelo entrenado con correcciones
   │                       → categoría + confianza + evidencia  (classify.py)
   │
   ├─▶ 5. NOMBRE          Plantilla configurable, campos faltantes explícitos,
   │                       versionado si el nombre ya existe      (naming.py)
   │
   ├─▶ 6. ARCHIVADO       Copia (o mueve) a data/documentos/organizados/…
   │                       según el esquema de carpetas elegido
   │
   └─▶ 7. REGISTRO        Fila en SQLite con todo lo anterior, más el texto
                           extraído para búsquedas. Si la confianza no llega al
                           umbral, queda en estado `revision`.
```

El flujo es **semiautomático a propósito**: todo se procesa solo, pero lo dudoso
se marca en vez de archivarse a ciegas. Cada corrección humana se guarda como
ejemplo de entrenamiento.

---

## 2. Análisis de documentos

### Extracción de texto

| Formato | Herramienta | Notas |
|---|---|---|
| PDF con texto | **PyMuPDF** | Rápido y sin dependencias externas |
| PDF escaneado | **PyMuPDF + Tesseract** | Se detecta por densidad de texto (< 90 caracteres por página) y se rasteriza a 200 dpi |
| DOCX | **python-docx** | Párrafos y tablas |
| Imágenes | **Tesseract** (`spa+eng`) | Fotos de documentos |
| EML | biblioteca estándar | Cabeceras + cuerpo |
| TXT/CSV/HTML | lectura directa | Prueba UTF-8, Latin-1 y CP1252 |

Si un PDF es un escaneo y **no hay Tesseract instalado**, el documento no se
descarta: se procesa con lo que haya y se marca para revisión, indicando el
motivo. El sistema nunca se queda sin respuesta por una dependencia ausente.

### Datos que se extraen

Expresiones regulares con reglas de posición, porque son verificables y cada
dato guarda de dónde salió:

| Dato | Cómo se obtiene |
|---|---|
| **Expediente** | Patrón federal `3:24-cv-05148-MGL`, etiquetas "Case/Civil Action/Expediente No.", o el nombre del archivo |
| **Fecha del documento** | Ver abajo: se elige por la etiqueta más cercana |
| **Partes** | Líneas terminadas en *Plaintiff/Defendant/Demandante/Demandado* o la línea con `v.` |
| **Tribunal** | Primera línea del encabezado que contiene *court/tribunal/juzgado* |
| **Emisor** | Línea con forma jurídica (`LLP`, `P.A.`, `& Associates`, *Law Offices*) o autor en metadatos |
| **Montos** | `$1,234.56`, se guarda el mayor como principal |
| **Reclamo / póliza / factura** | Etiquetas *Claim No.*, *Policy No.*, *Invoice No.* |
| **Título** | Línea que se comporta como título: mayúsculas, arriba, corta, penalizando las de sede judicial |

**Elección de la fecha.** Un documento trae varias fechas (nacimiento,
incidente, presentación, firma) y elegir la primera es un error clásico: en un
expediente médico eso da la fecha de nacimiento del paciente. Aquí cada fecha se
puntúa por la **etiqueta más cercana que la precede**:

| Etiqueta | Prioridad |
|---|---|
| *Date Filed* / fecha de presentación | 100 |
| *Date submitted* / fecha de envío | 90 |
| *Date of service* / fecha de atención | 85 |
| *executed on*, *dated this*, *given this*, *sworn this* | 82 |
| *Invoice date*, *statement date* | 80 |
| Campo genérico `Date:` / `Fecha:` | 70 |
| *Date of birth*, *date of incident*, *collision on*… | −50 (es la fecha de un hecho, no del documento) |

Medido sobre el juego de prueba: **13 de 13 fechas correctas**, incluidos los
casos trampa (expediente médico con fecha de nacimiento primero, Form 95 con
fecha de incidente antes que la de envío, contrato firmado meses después del
hecho).

---

## 3. Clasificación

### Categorías propuestas

Pensadas para el trabajo real de un despacho: el criterio es **por qué existe el
documento en el expediente**, no por su formato.

| Código | Categoría | Qué agrupa |
|---|---|---|
| `DEMANDA` | Demanda / Complaint | Escrito que inicia el litigio |
| `CITACION` | Citación / Summons | Emplazamiento a la parte demandada |
| `MOCION` | Moción / Motion | Solicitudes al tribunal |
| `ORDEN` | Orden / Resolución | Decisiones del tribunal |
| `NOTIFICACION` | Notificación / Aviso | Avisos y constancias de notificación |
| `RECLAMACION` | Reclamación administrativa | Form 95 y reclamos previos a la agencia |
| `REPORTE-POLICIAL` | Reporte policial / accidente | Partes de autoridad sobre el incidente |
| `EXPEDIENTE-MEDICO` | Expediente médico | Historia clínica, notas, estudios |
| `SEGURO` | Póliza / aseguradora | Pólizas, ajustes, cartas de aseguradora |
| `FACTURA` | Factura / estado de cuenta | Cobros de cualquier proveedor |
| `CONTRATO` | Contrato / acuerdo | Convenios, transacciones, liberaciones |
| `DECLARACION` | Declaración jurada | Affidavits, deposiciones, transcripciones |
| `IDENTIFICACION` | Identificación | Licencias y credenciales |
| `CORRESPONDENCIA` | Correspondencia | Cartas y correos |
| `CONTESTACION` | Contestación / Answer | Respuesta del demandado, con sus defensas |
| `DESCUBRIMIENTO` | Descubrimiento de prueba | Interrogatorios, requerimientos y admisiones |
| `CARATULA` | Carátula del caso | Hoja de datos que abre el expediente (JS 44) |
| `ACUSE` | Acuse de notificación | Constancia de que una parte fue notificada |
| `ESCRITO` | Escrito / alegato | Memoriales y alegatos de derecho |
| `TRANSCRIPCION` | Transcripción | Audiencias, deposiciones, llamadas |
| `PRUEBA` | Prueba / anexo | Anexos que acompañan a otro escrito |
| `SIN-CLASIFICAR` | Sin clasificar | No alcanzó la confianza mínima → revisión |

Son **21 categorías de fábrica**, y se pueden añadir más sin tocar código (abajo).

### Los dos clasificadores

**1. Reglas ponderadas (siempre activas).** Cada categoría tiene frases con peso
(fuerte 3.0, medio 1.5, leve 0.7). Lo que aparece en los primeros 1 500
caracteres —donde va el título— multiplica su aporte por 1.7. La confianza
combina cuánta evidencia hay con cuánto le saca a la segunda opción:

```
confianza = 0.45 · min(1, puntaje/9) + 0.55 · (puntaje₁ − puntaje₂)/puntaje₁
```

Ventaja: funciona desde el primer documento, sin datos previos, y **siempre
explica su decisión**. La interfaz muestra los términos que pesaron, dónde
aparecieron y cuánto aportaron.

**2. Naive Bayes entrenado con las correcciones (aprende con el uso).** Cada vez
que alguien corrige o confirma una categoría en la interfaz, ese documento se
guarda como ejemplo. A partir de 6 ejemplos en 2 categorías, el modelo entra a
votar:

* si **coincide** con las reglas → sube la confianza;
* si las reglas **dudaban** (confianza < umbral) y el modelo está seguro (≥ 75 %)
  → manda lo aprendido;
* si **discrepan** con las reglas seguras → se marca para revisión humana.

Es un multinomial con suavizado de Laplace sobre los 400 términos más frecuentes
del documento, implementado en el propio proyecto (sin dependencias de ML), y se
reentrena solo al registrar cada corrección.

### Qué pasa cuando un documento no encaja en ninguna

Es el caso normal cuando llega un tipo de documento que el catálogo no previó. El
sistema **no lo archiva mal ni lo descarta**: lo deja en `SIN-CLASIFICAR`, lo marca
para revisión y, en el panel de detalle, ofrece los **términos característicos del
documento** — las palabras y frases de dos palabras que más se repiten y que lo
distinguen— para que la persona defina la categoría con ellas.

![Documento sin clasificar con términos propuestos](img/docs-sin-clasificar.png)

Desde ese mismo panel: se marcan los términos, se escribe un código y un nombre, y
con un clic la categoría queda creada y **se reprocesa todo lo que estaba en
revisión** reutilizando el texto ya extraído (no hay que volver a subir nada). Lo
que cambie de categoría se renombra y se mueve a su carpeta.

Ejemplo real de la prueba: un certificado de ocupación municipal, que ninguna de las
21 categorías cubre.

| Momento | Categoría | Confianza | Nombre |
|---|---|---|---|
| Al subirlo | `SIN-CLASIFICAR` (en revisión) | 0 % | `2024-06-12_SIN-CLASIFICAR_sin-expediente_Owner-Andelytica-Services.pdf` |
| Tras crear `PERMISO` con los términos propuestos y reprocesar | `PERMISO` | **99 %** | `2024-06-12_PERMISO_sin-expediente_Owner-Andelytica-Services.pdf` en `PERMISO/2024/` |

Las categorías propias se administran también desde *Reglas y nombres*, donde se
pueden crear con sus palabras clave, ver cuántos documentos tiene cada una y
borrarlas. Borrar una categoría propia no toca los documentos ya clasificados.

### Resultados medidos

Sobre el juego de prueba de 13 documentos (12 sintéticos representativos + la
demanda federal real):

| Métrica | Valor |
|---|---|
| Categoría correcta | **13 / 13 (100 %)** |
| Confianza media | **89,5 %** |
| Archivados sin intervención | **100 %** |
| Fechas correctas | **13 / 13** |
| Duplicados detectados | 1 de 1 (copia byte a byte) |
| Expedientes agrupados | 7 documentos bajo `3:24-cv-05148-MGL` |

---

## 4. Convención de nombramiento

```
{fecha}_{CATEGORIA}_{expediente}_{descriptor}[_vNN].ext

2024-09-18_DEMANDA_3-24-cv-05148-MGL_Dona-M-Fry-v-United-State-America.pdf
2024-02-08_RECLAMACION_3-24-cv-05148-MGL_STANDARD-FORM-95.pdf
2023-01-15_EXPEDIENTE-MEDICO_sin-expediente_LEXINGTON-MEDICAL-CENTER.pdf
```

**Por qué así:**

* **Fecha ISO al principio** → el orden alfabético es el orden cronológico, en
  cualquier sistema operativo y en cualquier gestor documental.
* **Categoría en mayúsculas** → se distingue de un vistazo y agrupa sin abrir nada.
* **Expediente** → enlaza el archivo con su caso, que es la unidad de trabajo real.
* **Descriptor** → contexto humano: las partes si las hay, si no el título o el emisor.
* **Versión sólo cuando hace falta** → el caso normal queda limpio; si ya existe
  ese nombre se añade `_v02`, nunca se sobrescribe.

**Reglas de saneamiento:** sin acentos ni caracteres especiales (ASCII), sin
espacios (`-` dentro de cada campo, `_` entre campos), se eliminan palabras
vacías del descriptor, largo máximo configurable (120 por defecto).

**Campos faltantes:** si no se detecta un dato se escribe un marcador explícito
(`sin-fecha`, `sin-expediente`) en lugar de dejar el nombre incompleto o inventar
algo. Así el hueco es visible y se puede buscar.

**Todo es configurable** desde la interfaz: plantilla (`{fecha} {anio} {mes}
{categoria} {expediente} {descriptor} {emisor} {monto} {original} {hash}`),
separador, largo máximo y umbral de revisión. El botón *Reorganizar lo ya
archivado* vuelve a aplicar la convención vigente a todo el histórico.

### Estructura de carpetas

Cuatro esquemas, elegibles en caliente:

| Esquema | Resultado |
|---|---|
| `categoria_anio` (por defecto) | `DEMANDA/2024/2024-09-18_DEMANDA_…pdf` |
| `expediente` | `3-24-cv-05148-MGL/DEMANDA/…pdf` |
| `anio_mes` | `2024/09/…pdf` |
| `categoria` | `DEMANDA/…pdf` |
| `plano` | todo junto |

---

## 5. Uso de IA, OCR, NLP y reglas

| Técnica | Dónde se usa | Por qué esa elección |
|---|---|---|
| **OCR** (Tesseract) | PDFs escaneados e imágenes | Sólo se activa cuando hace falta: rasterizar y reconocer es caro comparado con leer texto nativo |
| **Reglas ponderadas** | Clasificación base | Explicables, auditables y funcionan sin datos previos. En un despacho, poder justificar una clasificación importa tanto como acertarla |
| **Naive Bayes** | Clasificación aprendida | Entrena en milisegundos con decenas de ejemplos, corre sin GPU y mejora con cada corrección |
| **NLP ligero** (tokenización, palabras vacías, bolsa de palabras) | Rasgos del modelo | Suficiente para documentos con vocabulario muy marcado |
| **Reglas de posición y contexto** | Fechas y entidades | La etiqueta más cercana resuelve las ambigüedades que un modelo genérico erraría |
| **Hash SHA-256** | Duplicados | Detección exacta, instantánea y sin falsos positivos |

**Por qué no un LLM de entrada:** el volumen es alto y repetitivo, el vocabulario
es cerrado y la precisión medida ya es del 100 % en el juego de prueba, con coste
nulo y sin enviar documentos confidenciales fuera del equipo. El punto de
extensión está preparado (ver mejoras): un LLM tiene sentido para lo que las
reglas no cubren —resúmenes, extracción de cláusulas, documentos atípicos—, no
para lo que ya se resuelve con un patrón.

---

## 6. Métricas y reportes

La **Bandeja** muestra:

* total procesado, páginas y tamaño;
* **tasa de archivado automático** (% que no necesitó intervención);
* documentos en revisión y confianza media;
* duplicados y errores;
* correcciones aprendidas y si el modelo entrenado ya está activo;
* documentos por categoría y expedientes con más documentos;
* por cada documento: nombre generado, categoría, confianza, expediente, fecha,
  estado y el original del que viene.

Exportable a CSV (`/api/export.csv`) para un dashboard externo.

---

## 7. Estructura del proyecto

```
docsai/                    Aplicacion completa
├── main.py                Servidor FastAPI y paginas
├── api.py                 Endpoints /api/*
├── config.py              Configuracion propia (config_documentos.json)
├── db.py                  SQLite propio (data/documentos/documentos.db)
├── extract.py             Texto de PDF, DOCX, imagenes, correos (+OCR)
├── entities.py            Expediente, fechas, partes, montos, emisor
├── classify.py            Reglas ponderadas + Naive Bayes entrenable
├── naming.py              Convencion de nombres y carpetas
├── pipeline.py            Flujo completo, correcciones y cola de trabajo
├── templates/             Bandeja y configuracion
└── static/                CSS y JS
run_documentos.py          Arranque y diagnostico
scripts/documentos_demo.py Generador de documentos de ejemplo
```

## 8. API

| Endpoint | Para qué |
|---|---|
| `POST /api/upload` | Subir uno o varios documentos |
| `POST /api/procesar-entrada` | Procesar lo que haya en `data/documentos/entrada` |
| `GET /api/lotes/{id}` | Progreso del lote |
| `GET /api/documentos?estado=&categoria=&q=` | Listado con filtros (busca también en el texto) |
| `GET /api/documentos/{id}` | Detalle: datos extraídos, evidencia y texto |
| `POST /api/documentos/{id}/reclasificar` | Corregir categoría (renombra, mueve y entrena) |
| `POST /api/documentos/{id}/aprobar` | Confirmar la propuesta |
| `POST /api/categorias` | Crear una categoría propia con sus términos |
| `DELETE /api/categorias/{codigo}` | Eliminar una categoría propia |
| `POST /api/reprocesar` | Reclasificar lo ya guardado con las reglas actuales |
| `GET /api/documentos/{id}/archivo` | Descargar el archivo ya renombrado |
| `GET/POST /api/convencion` | Leer o cambiar la convención de nombres |
| `POST /api/renombrar-todos` | Re-aplicar la convención al histórico |
| `GET /api/metricas` | Métricas del módulo |
| `GET /api/export.csv` | Exportación tabular |

---

## 9. Integración y escalabilidad

* **Aplicación independiente**: se despliega, se versiona y se escala por su cuenta;
  no arrastra las dependencias de visión por computadora del otro módulo.
* **Carpeta vigilada**: dejar archivos en `data/documentos/entrada` y pulsar
  *Procesar carpeta de entrada* (o llamar al endpoint desde un cron) permite
  conectar un escáner, una carpeta de red o una bandeja de correo sin tocar código.
* **API REST completa**: cualquier sistema del despacho puede empujar documentos
  y leer resultados; el CSV alimenta dashboards externos.
* **Nuevas categorías**: se crean **desde la interfaz**, con sus palabras clave, y
  entran a competir con las de fábrica sin tocar código ni reiniciar. Para el
  catálogo base se editan en `CATEGORIAS` (`docsai/classify.py`).
* **Nuevos formatos**: se añade una función en `docsai/extract.py` que devuelva la misma
  estructura; clasificación, nombrado y archivado se reutilizan.
* **Otro almacenamiento**: el archivado está aislado en `docsai/pipeline.py`;
  cambiar la carpeta local por S3, SharePoint o un gestor documental es sustituir
  esa llamada.
* **Volumen**: el procesamiento corre en un pool de hilos configurable
  (`max_trabajos`). Un PDF de 4 páginas con texto nativo tarda decenas de
  milisegundos; el OCR es el único paso realmente costoso y sólo se activa cuando
  el documento lo necesita.

---

## 10. Privacidad y seguridad

* Todo el procesamiento es **local**: ningún documento sale del equipo.
* El texto extraído se guarda en la base local sólo para búsqueda, y puede
  desactivarse (`guardar_texto`).
* Por defecto los originales **se conservan** (`conservar_original`): el
  sistema copia, no mueve, hasta que se confíe en el flujo.
* Nunca se sobrescribe un archivo: colisión de nombre → sufijo de versión.
* Los duplicados se detectan por hash, así que un mismo documento no se
  multiplica en el archivo.

---

## 11. Limitaciones y mejoras futuras

**Limitaciones**

* Sin Tesseract instalado, los PDFs escaneados se clasifican con poco texto y
  caen en revisión (el sistema lo dice explícitamente).
* Las reglas están afinadas para documentos legales en inglés y español; otro
  dominio necesita su propio catálogo de términos, que ya puede crearse desde la
  interfaz sin programar.
* La detección de duplicados es exacta: dos escaneos distintos del mismo
  documento no se reconocen como el mismo.
* El expediente se detecta bien en formato federal; otros formatos de numeración
  requieren añadir su patrón.

**Mejoras previstas**

* Duplicados aproximados por similitud de texto (shingling / MinHash).
* Extracción de cláusulas y resumen por documento con un LLM local para los casos
  que las reglas no cubren.
* Detección de firmas y sellos para separar borradores de documentos ejecutados.
* Enlace automático con el expediente en el sistema de gestión del despacho.
* Cola persistente y reintentos para volúmenes grandes (hoy la cola vive en memoria).

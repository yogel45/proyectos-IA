# Proyectos de IA para la oficina

Este repositorio contiene **cuatro proyectos independientes**, uno por reto. **No son un
solo producto**: cada uno se instala, se ejecuta, se documenta y se entrega por separado.

| Reto | Proyecto | Qué hace | Cómo se arranca | Puerto |
|---|---|---|---|---|
| **4** | **OfficeVision AI** | Análisis de video con IA: cámara de la PC, videos y cámaras IP; personas, objetos, zonas críticas y alertas | `python run.py` | 8000 |
| **5** | **DocuFlow AI** | Clasificación, nombramiento y archivado automático de documentos | `python run_documentos.py` | 8100 |
| **6** | **Directorio vivo** | Contactos que se arman solos con las llamadas, los documentos y la nómina | `python run_contactos.py` | 8200 |
| **7** | **Pruebas de carga** | Tráfico simulado, carga, resistencia y tolerancia a errores sobre los otros tres | `python run_pruebas.py` | — |

```bash
pip install -r requirements.txt     # dependencias comunes, una sola vez
```

## Cada reto, por separado

| Reto | Documento único de ese proyecto | Demostración con capturas |
|---|---|---|
| 4 | [`docs/RETO4_VIDEO.md`](docs/RETO4_VIDEO.md) | [`docs/DEMO_VIDEO.md`](docs/DEMO_VIDEO.md) |
| 5 | [`docs/RETO5_DOCUMENTOS.md`](docs/RETO5_DOCUMENTOS.md) | [`docs/DEMO_DOCUMENTOS.md`](docs/DEMO_DOCUMENTOS.md) |
| 6 | [`docs/RETO6_CONTACTOS.md`](docs/RETO6_CONTACTOS.md) | [`docs/DEMO_CONTACTOS.md`](docs/DEMO_CONTACTOS.md) |
| 7 | [`docs/RETO7_PRUEBAS.md`](docs/RETO7_PRUEBAS.md) | incluida en el mismo documento |

Cada uno de esos documentos **se lee solo**: lleva sus propias instrucciones de
instalación y ejecución, su enfoque técnico, sus resultados medidos y sus limitaciones.
No hace falta leer los demás.

Mapa de entregables y criterios de evaluación, reto por reto:
[`docs/ENTREGABLES.md`](docs/ENTREGABLES.md).

## Qué comparten y qué no

Los cuatro viven en el mismo repositorio porque se instalan con el mismo
`requirements.txt`, pero **están separados de verdad**:

* Cada proyecto tiene **su propio servidor, su propia base de datos y su propia
  configuración** (`config.json`, `config_documentos.json`, `config_contactos.json`).
* Los tres primeros **pueden correr a la vez o por separado**, en puertos distintos.
* **Ninguno importa código de otro.**
* La única conexión es opcional y de una sola dirección: el Reto 6 puede leer la base del
  Reto 5 **en modo sólo lectura** para saber quién es quién en cada expediente. Si esa
  base no existe, el Reto 6 funciona igual y lo dice.
* El Reto 7 **no toca a ninguno de los tres**: pone a prueba ContactHub, la agenda de
  contactos, y sólo por HTTP —no importa su código ni abre su base de datos—.

## Estructura

```
proyectos-IA/
├── app/                    Reto 4 · OfficeVision AI      → run.py
├── docsai/                 Reto 5 · DocuFlow AI          → run_documentos.py
├── contactos/              Reto 6 · Directorio vivo      → run_contactos.py
├── pruebas/                Reto 7 · Pruebas sobre ContactHub → run_pruebas.py
├── docs/                   Un documento por reto, cada uno independiente
├── scripts/                Generadores de datos de ejemplo, uno por proyecto
├── sample_data/            Biométrico y RingCentral reales
├── models/                 Pesos del detector (se descargan solos)
└── data/                   Bases de datos, subidas, salidas y resultados
```

## Requisitos comunes

* Python 3.9 o superior (probado en 3.11).
* Windows 10/11, macOS o Linux.
* Unos 3 GB libres: las dependencias de visión por computadora pesan.
* Todo el procesamiento es **local**. Nada sale de la computadora.

Para comprobar el entorno de cualquier proyecto sin arrancarlo:

```bash
python run.py --check
python run_documentos.py --check
python run_contactos.py --check
python run_pruebas.py --check
```

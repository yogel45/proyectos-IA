"""Los escenarios de prueba, y por que son esos y no otros.

El tamano de la carga no se invento: sale de los datos reales del despacho.
En el historial de RingCentral (4 000 llamadas, 24 dias) la hora mas cargada
fue el 23/08/2025 a las 09:00, con **56 llamadas**; la mediana de una hora
laborable es de 16. Con 25 personas en nomina, esa hora pico es el techo real
de la oficina. Todo lo demas se deriva de ahi:

* cada llamada entrante provoca **una busqueda en el directorio** (es el gesto
  que motivo el Reto 6: saber quien llama antes de contestar);
* durante esa hora hay **pantallas abiertas** del panel de video que se
  refrescan solas cada 5 segundos;
* se suben **documentos** al clasificador a lo largo del dia;
* y alguien esta consultando fichas y expedientes.

Esa mezcla es la "carga nominal" (1x). Como probar solo el caso comodo no
demuestra nada, la misma mezcla se repite multiplicada hasta encontrar donde
se rompe.
"""
from __future__ import annotations

import io
import random
from typing import Any, Dict, List, Sequence

from .carga import Peticion

VIDEO = "http://127.0.0.1:8000"
DOCS = "http://127.0.0.1:8100"
CONTACTOS = "http://127.0.0.1:8200"

# Medido en sample_data/RingCentral_History.xlsx
PICO_LLAMADAS_HORA = 56
MEDIANA_LLAMADAS_HORA = 16
EMPLEADOS = 25
PANELES_ABIERTOS = 8          # pantallas del panel de video en la oficina
REFRESCO_PANEL_S = 5

_rnd = random.Random(20260919)

# Consultas reales: telefonos que estan en el historial, apellidos del
# expediente, numeros de caso y papeles procesales.
CONSULTAS = [
    "(803) 359-5523", "(929) 876-9687", "fry", "united states", "cunningham",
    "3:24-cv-05148-MGL", "demandante", "demandado", "abogado", "mcwhirter",
    "ortiz", "gonzalez", "paralegal", "(509) 674-7878", "flores",
]


def _rps_nominal() -> Dict[str, float]:
    """Peticiones por segundo de una hora pico real, desglosadas."""
    busquedas = PICO_LLAMADAS_HORA / 3600.0            # 1 busqueda por llamada
    paneles = PANELES_ABIERTOS / REFRESCO_PANEL_S      # refresco automatico
    fichas = (PICO_LLAMADAS_HORA * 0.6) / 3600.0       # 6 de cada 10 se abren
    documentos = 12 / 3600.0                           # lote de la manana
    return {"busquedas": busquedas, "paneles": paneles,
            "fichas": fichas, "documentos": documentos}


RPS_NOMINAL = sum(_rps_nominal().values())


# --------------------------------------------------------------------------
# Mezcla de la oficina: lo que de verdad se pide en una hora pico
# --------------------------------------------------------------------------
def mezcla_oficina(persona_id: int = 26, caso_id: int = 1) -> List[Peticion]:
    """Los identificadores se descubren en el sistema, no se dan por hechos.

    En la primera ejecucion en la maquina del despacho, con la base vacia, el
    escenario pedia la ficha 26 y el expediente 1 porque estaban escritos a
    mano. Esas peticiones devolvian 404 y la prueba las contaba como fallos del
    sistema: un 0,6 % de error que no era real. Ahora se consultan antes.
    """
    partes = _rps_nominal()
    return [
        # --- Directorio vivo: el que recibe la llamada busca quien es -------
        Peticion("buscar contacto", "GET",
                 f"{CONTACTOS}/api/buscar?q={{}}", peso=partes["busquedas"] * 0.7),
        Peticion("abrir ficha", "GET", f"{CONTACTOS}/api/personas/{persona_id}",
                 peso=partes["fichas"] * 0.6),
        Peticion("quien es quien", "GET", f"{CONTACTOS}/api/casos/{caso_id}",
                 peso=partes["fichas"] * 0.25),
        Peticion("contactos recientes", "GET", f"{CONTACTOS}/api/recientes",
                 peso=partes["busquedas"] * 0.3),
        Peticion("metricas contactos", "GET", f"{CONTACTOS}/api/metricas",
                 peso=partes["fichas"] * 0.15),

        # --- OfficeVision: paneles abiertos refrescandose solos -------------
        Peticion("panel en vivo", "GET", f"{VIDEO}/api/metrics/live",
                 peso=partes["paneles"] * 0.45),
        Peticion("eventos recientes", "GET", f"{VIDEO}/api/events?limit=50",
                 peso=partes["paneles"] * 0.25),
        Peticion("resumen de video", "GET", f"{VIDEO}/api/metrics/summary",
                 peso=partes["paneles"] * 0.20),
        Peticion("estado del sistema", "GET", f"{VIDEO}/api/system",
                 peso=partes["paneles"] * 0.10),

        # --- DocuFlow: consulta de la bandeja -------------------------------
        Peticion("bandeja de documentos", "GET", f"{DOCS}/api/documentos?limite=40",
                 peso=partes["documentos"] * 0.6),
        Peticion("metricas documentos", "GET", f"{DOCS}/api/metricas",
                 peso=partes["documentos"] * 0.4),
    ]


def con_consultas(peticiones: Sequence[Peticion]) -> List[Peticion]:
    """Sustituye el marcador {} de las busquedas por consultas reales distintas.

    Importa: repetir siempre la misma consulta mediria la cache del sistema
    operativo, no la busqueda.
    """
    salida: List[Peticion] = []
    for p in peticiones:
        if "{}" in p.url:
            for consulta in CONSULTAS:
                salida.append(Peticion(
                    p.nombre, p.metodo,
                    p.url.replace("{}", consulta.replace(" ", "%20")
                                  .replace("(", "%28").replace(")", "%29")),
                    peso=p.peso / len(CONSULTAS), esperado=p.esperado))
        else:
            salida.append(p)
    return salida


# --------------------------------------------------------------------------
# Solo lectura pesada: la peor consulta de cada aplicacion
# --------------------------------------------------------------------------
def mezcla_lectura_pesada() -> List[Peticion]:
    return [
        Peticion("buscar 'a' (muchos resultados)", "GET",
                 f"{CONTACTOS}/api/buscar?q=ar&limite=25", peso=3),
        Peticion("duplicados (recorre toda la base)", "GET",
                 f"{CONTACTOS}/api/duplicados", peso=1),
        Peticion("resumen de video", "GET", f"{VIDEO}/api/metrics/summary", peso=2),
        Peticion("exportar eventos CSV", "GET", f"{VIDEO}/api/export/events.csv", peso=1),
        Peticion("bandeja de documentos", "GET",
                 f"{DOCS}/api/documentos?limite=100", peso=2),
    ]


# --------------------------------------------------------------------------
# Escrituras concurrentes: donde de verdad duele SQLite
# --------------------------------------------------------------------------
def mezcla_escrituras(persona_id: int = 26) -> List[Peticion]:
    """Varias personas anotando y dando de alta a la vez.

    Es el escenario que pone a prueba la decision de arquitectura mas
    discutible del proyecto: una sola conexion SQLite serializada con un
    cerrojo. Si esto se degrada, hay que saberlo.
    """
    contador = {"n": 0}

    def nota() -> Dict[str, Any]:
        contador["n"] += 1
        return {"texto": f"Nota de prueba de carga #{contador['n']}"}

    def alta() -> Dict[str, Any]:
        contador["n"] += 1
        n = contador["n"]
        return {"nombre": f"Carga Prueba {n}", "rol": "Contacto de prueba",
                "organizacion": "Prueba de carga",
                "identificadores": [{"tipo": "telefono",
                                     "valor": f"(999) {n // 10000 % 10}{n % 10000:04d}"[:14]}]}

    def leer_firma() -> Dict[str, Any]:
        return {"texto": "GRUPO DE PRUEBA, P.A.\nJuan Perez, Esq.\n"
                         "Federal Bar No. 99999\n123 Test Road\nQuito, Pichincha 170101\n"
                         "P: (999) 111-2222  F: (999) 111-3333\njuan@prueba.test"}

    return [
        Peticion("anotar en una ficha", "POST",
                 f"{CONTACTOS}/api/personas/{persona_id}/nota", datos=nota, peso=3),
        Peticion("alta de contacto", "POST",
                 f"{CONTACTOS}/api/personas", datos=alta, peso=2),
        Peticion("leer una firma", "POST",
                 f"{CONTACTOS}/api/leer", datos=leer_firma, peso=2),
        Peticion("buscar contacto", "GET",
                 f"{CONTACTOS}/api/buscar?q=carga", peso=3),
    ]


# --------------------------------------------------------------------------
# Tolerancia a errores: lo que pasa cuando la peticion viene mal
# --------------------------------------------------------------------------
PDF_MINIMO = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
              b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
              b"trailer<</Root 1 0 R>>\n%%EOF\n")


def casos_borde(ficha: int = 26) -> List[Dict[str, Any]]:
    """Cada caso dice que se espera, para poder juzgar si respondio bien.

    La regla: un error del cliente debe contestarse con 4xx y un mensaje, no
    con 500 ni con un proceso caido. Y despues de todos ellos, los datos deben
    seguir intactos.
    """
    gigante = "x" * 200_000
    return [
        {"nombre": "ficha que no existe", "metodo": "GET",
         "url": f"{CONTACTOS}/api/personas/999999", "esperado": [404]},
        {"nombre": "expediente que no existe", "metodo": "GET",
         "url": f"{CONTACTOS}/api/casos/999999", "esperado": [404]},
        {"nombre": "documento que no existe", "metodo": "GET",
         "url": f"{DOCS}/api/documentos/999999", "esperado": [404]},
        {"nombre": "id no numerico", "metodo": "GET",
         "url": f"{CONTACTOS}/api/personas/abc", "esperado": [422]},
        {"nombre": "alta sin nombre", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas", "json": {"rol": "sin nombre"},
         "esperado": [400]},
        {"nombre": "JSON malformado", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas", "crudo": b'{"nombre": ', "esperado": [400, 422]},
        {"nombre": "cuerpo vacio donde se espera JSON", "metodo": "POST",
         "url": f"{CONTACTOS}/api/leer", "crudo": b"", "esperado": [400, 422]},
        {"nombre": "nota vacia", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas/{ficha}/nota", "json": {"texto": "   "},
         "esperado": [400]},
        {"nombre": "consulta de 200 000 caracteres", "metodo": "POST",
         "url": f"{CONTACTOS}/api/leer", "json": {"texto": gigante},
         "esperado": [200, 413, 422]},
        {"nombre": "intento de inyeccion SQL", "metodo": "GET",
         "url": f"{CONTACTOS}/api/buscar?q=%27%3B+DROP+TABLE+personas%3B--",
         "esperado": [200]},
        {"nombre": "anotar en una ficha que no existe", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas/999999/nota", "json": {"texto": "prueba"},
         "esperado": [404]},
        {"nombre": "agregar un dato a una ficha que no existe", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas/999999/identificadores",
         "json": {"tipo": "telefono", "valor": "(999) 111-2222"}, "esperado": [404]},
        {"nombre": "vincular a un expediente una ficha que no existe", "metodo": "POST",
         "url": f"{CONTACTOS}/api/personas/999999/casos",
         "json": {"expediente": "1:11-cv-11111"}, "esperado": [404]},
        {"nombre": "editar una ficha que no existe", "metodo": "PATCH",
         "url": f"{CONTACTOS}/api/personas/999999", "json": {"rol": "x"},
         "esperado": [404]},
        {"nombre": "fusionar una ficha consigo misma", "metodo": "POST",
         "url": f"{CONTACTOS}/api/duplicados/fusionar",
         "json": {"principal_id": ficha, "absorbida_id": ficha}, "esperado": [400]},
        {"nombre": "fusionar con ficha inexistente", "metodo": "POST",
         "url": f"{CONTACTOS}/api/duplicados/fusionar",
         "json": {"principal_id": ficha, "absorbida_id": 999999}, "esperado": [400]},
        {"nombre": "deshacer una fusion que no existe", "metodo": "POST",
         "url": f"{CONTACTOS}/api/fusiones/999999/deshacer", "esperado": [400]},
        {"nombre": "fuente desconocida", "metodo": "POST",
         "url": f"{CONTACTOS}/api/importar/inventada", "esperado": [404]},
        {"nombre": "subir un tipo de archivo no soportado", "metodo": "POST",
         "url": f"{DOCS}/api/upload",
         "archivo": ("prueba.exe", b"MZ\x90\x00" * 100, "application/octet-stream"),
         "esperado": [200, 400, 415]},
        {"nombre": "subir un PDF vacio/corrupto", "metodo": "POST",
         "url": f"{DOCS}/api/upload",
         "archivo": ("corrupto.pdf", b"%PDF-1.4 roto", "application/pdf"),
         "esperado": [200, 400]},
        {"nombre": "nombre de archivo con ../ (path traversal)", "metodo": "POST",
         "url": f"{DOCS}/api/upload",
         "archivo": ("../../../../etc/passwd.pdf", PDF_MINIMO, "application/pdf"),
         "esperado": [200, 400]},
        {"nombre": "categoria sin codigo", "metodo": "POST",
         "url": f"{DOCS}/api/categorias", "json": {"nombre": "sin codigo"},
         "esperado": [400]},
        {"nombre": "zona con poligono invalido", "metodo": "POST",
         "url": f"{VIDEO}/api/zones",
         "json": {"name": "rota", "polygon": [[0.1, 0.1]]}, "esperado": [400, 422]},
        {"nombre": "trabajo de video inexistente", "metodo": "GET",
         "url": f"{VIDEO}/api/jobs/999999", "esperado": [404]},
        {"nombre": "cancelar un trabajo inexistente", "metodo": "POST",
         "url": f"{VIDEO}/api/jobs/999999/cancel", "esperado": [404, 400]},
        {"nombre": "parametro negativo donde se espera positivo", "metodo": "GET",
         "url": f"{VIDEO}/api/events?limit=-5", "esperado": [200, 422]},
    ]

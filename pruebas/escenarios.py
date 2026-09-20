"""Que se le pide a ContactHub, cuanto, y por que ese y no otro.

La carga no se inventa: sale de dos archivos reales de la oficina que estan
en `sample_data/`.

* El historial de la centralita (RingCentral) da la hora punta real: 56
  llamadas entrantes en la hora mas cargada del ano. Cada llamada entrante es
  una busqueda en la libreta — es literalmente para lo que se abre ContactHub
  cuando suena el telefono.
* La nomina del biometrico da el tamano de la oficina: 26 personas.

De ahi sale la tabla de abajo, que es el escenario "una hora punta de
verdad". Todo lo demas de esta prueba es ese escenario multiplicado.

Conviene decirlo claro porque es el resultado mas util de todo el reto: la
demanda real de esta oficina es de **decimas de peticion por segundo**. Las
cifras de tres digitos que salen en la escalada no son la carga esperada,
son el margen que hay antes de que el sistema se rompa.
"""
from __future__ import annotations

import random
import string
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .carga import Peticion
from .contacthub import API, BASE

# --------------------------------------------------------------------------
# De donde sale la carga nominal
# --------------------------------------------------------------------------
PICO_LLAMADAS_HORA = 56       # hora mas cargada del historial de la centralita
MEDIANA_LLAMADAS_HORA = 16    # hora tipica
EMPLEADOS = 26                # personas en la hoja "Nomina" del biometrico
PANTALLAS_ABIERTAS = 6        # equipos con la libreta abierta a la vez
REFRESCO_RESUMEN_MIN = 5      # cada cuanto se refresca el panel de resumen

# Operacion -> veces en la hora punta. Es el reparto que decide los pesos.
HORA_PUNTA: Dict[str, int] = {
    "buscar por texto":      PICO_LLAMADAS_HORA,            # una por llamada
    "abrir ficha":           round(PICO_LLAMADAS_HORA * 0.7),  # 7 de cada 10 se abren
    "listar libreta":        EMPLEADOS * 3,                 # 3 aperturas por persona
    "resumen":               PANTALLAS_ABIERTAS * (60 // REFRESCO_RESUMEN_MIN),
    "etiquetas":             EMPLEADOS,                     # el menu lateral
    "filtrar":               20,                            # por empresa o etiqueta
    "historial de la ficha": 8,
    "duplicados":            1,                             # limpieza ocasional
    "alta de contacto":      9,
    "editar contacto":       12,
    "accion en bloque":      4,
}
LECTURAS = {k: v for k, v in HORA_PUNTA.items()
            if k not in ("alta de contacto", "editar contacto", "accion en bloque")}
ESCRITURAS = {k: v for k, v in HORA_PUNTA.items() if k not in LECTURAS}

RPS_NOMINAL = sum(HORA_PUNTA.values()) / 3600.0
RPS_LECTURA = sum(LECTURAS.values()) / 3600.0


def multiplo(rps: float) -> float:
    """Cuantas horas punta reales caben en ese caudal."""
    return rps / RPS_NOMINAL if RPS_NOMINAL else 0.0


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _reparte(nombre: str, urls: Sequence[str], peso: float) -> List[Peticion]:
    """Una operacion repartida entre varios objetivos reales.

    Buscar 200 veces el mismo apellido o abrir 200 veces la misma ficha mide
    la cache, no el sistema. Se reparte el peso entre todos los objetivos que
    se encontraron en la libreta.
    """
    if not urls:
        return []
    trozo = peso / len(urls)
    return [Peticion(nombre, "GET", u, peso=trozo) for u in urls]


def _cita(texto: str) -> str:
    from urllib.parse import quote
    return quote(str(texto), safe="")


# --------------------------------------------------------------------------
# Mezcla de lectura: la hora punta de la oficina
# --------------------------------------------------------------------------
def mezcla_oficina(inv: Dict[str, Any]) -> List[Peticion]:
    """La libreta usada como se usa: suena el telefono y alguien busca."""
    ids = inv.get("ids") or []
    textos = inv.get("textos") or ["a"]
    empresas = inv.get("empresas") or []
    etiquetas = inv.get("etiquetas") or []
    p = LECTURAS

    pets: List[Peticion] = []
    pets += _reparte("buscar por texto",
                     [f"{API}/contacts?q={_cita(t)}&limit=25" for t in textos[:40]],
                     p["buscar por texto"])
    pets += _reparte("abrir ficha",
                     [f"{API}/contacts/{i}" for i in ids[:60]],
                     p["abrir ficha"])
    pets += _reparte("listar libreta",
                     [f"{API}/contacts?limit=50&offset={o}&sort=name"
                      for o in (0, 50, 100, 150)],
                     p["listar libreta"])
    pets.append(Peticion("resumen", "GET", f"{API}/stats", peso=p["resumen"]))
    pets.append(Peticion("etiquetas", "GET", f"{API}/labels", peso=p["etiquetas"]))
    filtros = [f"{API}/contacts?company={_cita(e)}&limit=25" for e in empresas[:6]]
    filtros += [f"{API}/contacts?label={_cita(e)}&limit=25" for e in etiquetas[:4]]
    filtros.append(f"{API}/contacts?has_email=true&favorite=true&limit=25")
    pets += _reparte("filtrar", filtros, p["filtrar"])
    pets += _reparte("historial de la ficha",
                     [f"{API}/contacts/{i}/history" for i in ids[:20]],
                     p["historial de la ficha"])
    pets.append(Peticion("duplicados", "GET", f"{API}/contacts/duplicates",
                         peso=p["duplicados"], timeout=60))
    return [x for x in pets if x.peso > 0]


def mezcla_busqueda_dura(inv: Dict[str, Any]) -> List[Peticion]:
    """Lo que de verdad cuesta: texto libre, paginas hondas y duplicados.

    No es la mezcla de un dia normal; es la mezcla con la que se descubre
    donde estan los limites del indice.
    """
    textos = inv.get("textos") or ["a"]
    total = max(inv.get("total") or 0, 200)
    hondo = max(total - 200, 0)
    pets = [
        Peticion("texto libre", "GET",
                 f"{API}/contacts?q={_cita(textos[0])}&limit=200", peso=4),
        Peticion("pagina honda", "GET",
                 f"{API}/contacts?limit=200&offset={hondo}&sort=updated", peso=3),
        Peticion("orden por empresa", "GET",
                 f"{API}/contacts?limit=200&sort=company", peso=2),
        Peticion("duplicados", "GET", f"{API}/contacts/duplicates",
                 peso=1, timeout=120),
        Peticion("resumen", "GET", f"{API}/stats", peso=2),
    ]
    return pets


# --------------------------------------------------------------------------
# Mezcla de escritura
# --------------------------------------------------------------------------
_MARCA = "Prueba de carga"      # con esto se localiza y se borra despues
_AZAR = random.Random(20260920)


def _sufijo() -> str:
    return "".join(_AZAR.choice(string.ascii_lowercase + string.digits)
                   for _ in range(8))


def mezcla_escrituras(inv: Dict[str, Any]) -> List[Peticion]:
    """Varias personas dando de alta y corrigiendo fichas a la vez.

    Es la prueba que mas veces ha encontrado fallos reales: SQLite serializa
    las escrituras, y lo que se ve aqui es si esa cola se convierte en espera
    para el usuario o en errores.
    """
    ids = inv.get("ids") or []
    p = ESCRITURAS

    def alta() -> Dict[str, Any]:
        s = _sufijo()
        return {"first_name": "Carga", "last_name": f"Prueba {s}",
                "company": _MARCA, "job_title": "Contacto generado por la prueba",
                "category": "Interno",
                "labels": ["Prueba de carga"],
                "emails": [{"label": "Work", "value": f"carga.{s}@example.com",
                            "is_primary": True}],
                "phones": [{"label": "Work", "value": f"+1843555{_AZAR.randint(0, 9999):04d}"}],
                "notes": "Alta creada por la prueba de carga del reto 7."}

    def edicion() -> Dict[str, Any]:
        return {"notes": f"Revisado por la prueba de carga {time.strftime('%H:%M:%S')}",
                "category": _AZAR.choice(["Cliente", "Contraparte", "Proveedor"])}

    pets: List[Peticion] = [
        Peticion("alta de contacto", "POST", f"{API}/contacts",
                 peso=p["alta de contacto"], datos=alta, esperado=(201,)),
    ]
    if ids:
        trozo = p["editar contacto"] / min(len(ids), 40)
        for i in ids[:40]:
            pets.append(Peticion("editar contacto", "PATCH", f"{API}/contacts/{i}",
                                 peso=trozo, datos=edicion, esperado=(200, 409)))
        # una accion en bloque de verdad: etiquetar 20 fichas de una vez
        lote = ids[:20]

        def bloque() -> Dict[str, Any]:
            return {"ids": lote, "action": "add_label", "value": "Revisado"}

        pets.append(Peticion("accion en bloque", "POST", f"{API}/contacts/bulk",
                             peso=p["accion en bloque"], datos=bloque,
                             esperado=(200,)))
    return pets


# --------------------------------------------------------------------------
# Bateria de casos borde
# --------------------------------------------------------------------------
UUID_FANTASMA = "00000000-0000-4000-8000-000000000000"

# Un JWT con la estructura correcta pero firmado con otra clave.
TOKEN_FALSO = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDAiLCJleHAiOjk5OTk5OTk5OTl9."
    "ZmlybWFfaW52ZW50YWRhX3F1ZV9ub19kZWJlcmlhX3ZhbGVy")


def casos_borde(inv: Dict[str, Any], sesion) -> List[Dict[str, Any]]:
    """Peticiones mal formadas, sin permiso o maliciosas, una a una.

    Lo que se comprueba no es que fallen, sino *como* fallan: un 401 o un 422
    es el sistema defendiendose; un 500 es el sistema roto. Cada caso lleva el
    codigo que deberia devolver, y el resumen cuenta cuantos aciertan.
    """
    ids = inv.get("ids") or [UUID_FANTASMA]
    ficha = ids[0]
    cab = sesion.cabeceras()
    sin_cab: Dict[str, str] = {}
    json_h = {"Content-Type": "application/json"}

    def c(nombre, metodo, url, esperado, **extra):
        base = {"nombre": nombre, "metodo": metodo, "url": url,
                "esperado": esperado, "cabeceras": cab}
        base.update(extra)
        return base

    casos: List[Dict[str, Any]] = [
        # --- puerta de entrada -------------------------------------------
        c("sin token", "GET", f"{API}/contacts", (401, 403), cabeceras=sin_cab),
        c("token inventado", "GET", f"{API}/contacts", (401,),
          cabeceras={"Authorization": f"Bearer {TOKEN_FALSO}"}),
        # Sin espacio final: httpx se niega a enviar "Bearer " (cabecera
        # ilegal) y la peticion no llegaba nunca al servidor. Contaba como
        # fallo de ContactHub y era fallo de la prueba.
        c("Bearer sin token", "GET", f"{API}/contacts", (401, 403),
          cabeceras={"Authorization": "Bearer"}),
        c("esquema equivocado", "GET", f"{API}/contacts", (401, 403),
          cabeceras={"Authorization": f"Basic {sesion.token}"}),
        c("token en la URL en vez de la cabecera", "GET",
          f"{API}/contacts?access_token={sesion.token}", (401, 403),
          cabeceras=sin_cab),
        c("refresh con un token que no es de refresco", "POST",
          f"{API}/auth/refresh", (401, 422), json={"refresh_token": sesion.token},
          cabeceras=sin_cab),
        c("perfil de administrador siendo usuario normal", "GET",
          f"{API}/admin/users", (403,)),

        # --- identificadores ---------------------------------------------
        c("contacto que no existe", "GET", f"{API}/contacts/{UUID_FANTASMA}", (404,)),
        c("id que no es un uuid", "GET", f"{API}/contacts/12345", (422,)),
        c("id con inyeccion", "GET", f"{API}/contacts/1%20OR%201=1", (422,)),
        c("historial de un contacto que no existe", "GET",
          f"{API}/contacts/{UUID_FANTASMA}/history", (404,)),
        c("importacion que no existe", "GET",
          f"{API}/imports/{UUID_FANTASMA}", (404,)),

        # --- cuerpo de la peticion ---------------------------------------
        c("JSON malformado", "POST", f"{API}/contacts", (400, 422),
          crudo=b'{"first_name": "Ana", ', cabeceras={**cab, **json_h}),
        c("cuerpo vacio donde se espera JSON", "POST", f"{API}/contacts",
          (400, 422), crudo=b"", cabeceras={**cab, **json_h}),
        c("contacto sin nombre ni telefono ni correo", "POST", f"{API}/contacts",
          (422,), json={"notes": "sin identidad"}),
        c("correo invalido", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "emails": [{"value": "esto-no-es-un-correo"}]}),
        c("telefono invalido", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "phones": [{"value": "abc"}]}),
        c("fecha de nacimiento imposible", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "birthday": "1990-02-31"}),
        c("campo que no existe en el esquema", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "es_administrador": True}),
        c("photo_url apuntando a un archivo local", "POST", f"{API}/contacts",
          (422,), json={"first_name": "Ana", "photo_url": "file:///etc/passwd"}),
        c("nota de 200 000 caracteres", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "notes": "x" * 200000}),
        c("51 etiquetas en un contacto", "POST", f"{API}/contacts", (422,),
          json={"first_name": "Ana", "labels": [f"e{i}" for i in range(51)]}),

        # --- parametros de busqueda --------------------------------------
        # 20 000 y no 200 000: con 200 000 httpx aborta por su cuenta
        # ("URL too long") y la peticion no llega, asi que no medía nada del
        # servidor. Con 20 000 si llega, y ContactHub la rechaza con 422
        # (el limite declarado de `q` son 100 caracteres).
        c("busqueda de 20 000 caracteres", "GET",
          f"{API}/contacts?q={'a' * 20000}", (414, 422)),
        c("intento de inyeccion SQL en la busqueda", "GET",
          f"{API}/contacts?q={_cita(chr(39) + ' OR 1=1; DROP TABLE contacts;--')}",
          (200,)),
        c("limite 0", "GET", f"{API}/contacts?limit=0", (422,)),
        c("limite 5000", "GET", f"{API}/contacts?limit=5000", (422,)),
        c("desplazamiento negativo", "GET", f"{API}/contacts?offset=-1", (422,)),
        c("orden que no existe", "GET", f"{API}/contacts?sort=loquesea", (422,)),
        c("fecha con formato invalido", "GET",
          f"{API}/contacts?updated_since=ayer", (422,)),

        # --- operaciones sobre varios ------------------------------------
        c("fusionar un contacto consigo mismo", "POST", f"{API}/contacts/merge",
          (400, 404, 422),
          json={"primary_id": ficha, "duplicate_ids": [ficha]}),
        c("fusionar con un contacto inexistente", "POST", f"{API}/contacts/merge",
          (400, 404), json={"primary_id": ficha, "duplicate_ids": [UUID_FANTASMA]}),
        c("accion en bloque sin ids", "POST", f"{API}/contacts/bulk", (422,),
          json={"ids": [], "action": "delete"}),
        c("etiquetar en bloque sin decir que etiqueta", "POST",
          f"{API}/contacts/bulk", (422,),
          json={"ids": [ficha], "action": "add_label"}),
        c("accion en bloque que no existe", "POST", f"{API}/contacts/bulk", (422,),
          json={"ids": [ficha], "action": "incinerar"}),
        # ContactHub acepta restaurar algo que no estaba borrado: es
        # idempotente. Se deja como esta (200) y se anota aparte que la
        # operacion, aun sin cambiar nada, sube la version del contacto.
        c("restaurar algo que no esta en la papelera", "POST",
          f"{API}/contacts/{ficha}/restore", (200,)),

        # --- concurrencia optimista --------------------------------------
        c("editar con una version vieja", "PATCH", f"{API}/contacts/{ficha}",
          (409,), json={"version": 1, "notes": "choque de versiones"}),

        # --- archivos -----------------------------------------------------
        c("subir como foto algo que no es una imagen", "POST",
          f"{API}/contacts/{ficha}/photo", (400, 415, 422),
          archivo=("foto.png", b"esto no es un png", "image/png")),
        c("importar un CSV que no es de Google Contacts", "POST",
          f"{API}/imports/google-csv", (400,),
          archivo=("cualquiera.csv", b"columna_a,columna_b\n1,2\n", "text/csv")),
        c("importar un .vcf vacio", "POST", f"{API}/imports/vcard", (400,),
          archivo=("vacio.vcf", b"", "text/vcard")),
        c("nombre de archivo con ../ (path traversal)", "POST",
          f"{API}/imports/vcard", (202, 400),
          archivo=("../../../../etc/passwd.vcf",
                   b"BEGIN:VCARD\nVERSION:3.0\nFN:Ana\nEND:VCARD\n", "text/vcard")),

        # --- registro ------------------------------------------------------
        c("registrarse con un correo ya usado", "POST", f"{API}/auth/register",
          (400, 403, 409), cabeceras=sin_cab,
          json={"email": sesion.usuario, "password": "OtraClaveLarga2026!"}),
        c("contrasena demasiado corta", "POST", f"{API}/auth/register", (422, 403),
          cabeceras=sin_cab,
          json={"email": f"corta.{uuid.uuid4().hex[:8]}@example.com",
                "password": "abc"}),
        c("contrasena de un solo caracter repetido", "POST",
          f"{API}/auth/register", (422, 403), cabeceras=sin_cab,
          json={"email": f"debil.{uuid.uuid4().hex[:8]}@example.com",
                "password": "aaaaaaaaaaaa"}),
    ]
    return casos


def cerrojo_de_intentos(correo: Optional[str] = None) -> Dict[str, Any]:
    """Comprueba que la puerta se cierra sola tras varios intentos fallidos.

    Va aparte de la bateria porque deja bloqueada la clave "ip + correo"
    durante 15 minutos: se usa una cuenta inventada, nunca la de la prueba,
    para no quedarse fuera a mitad de la sesion.
    """
    import httpx
    # example.com y no .test: email-validator rechaza los dominios de uso
    # especial (.test, .invalid, .localhost) con un 422 de validacion, y la
    # peticion moria antes de llegar al limitador. La prueba decia entonces
    # que ContactHub no cierra la puerta, y si la cierra.
    correo = correo or f"intruso.{uuid.uuid4().hex[:10]}@example.com"
    codigos: List[int] = []
    with httpx.Client(timeout=30) as c:
        for _ in range(7):
            r = c.post(f"{API}/auth/login",
                       json={"email": correo, "password": "clave-equivocada"})
            codigos.append(r.status_code)
    corto = 429 in codigos
    return {"correo": correo, "codigos": codigos,
            "corta_despues_de": (codigos.index(429) if corto else None),
            "bloquea": corto}

"""Endpoints REST de Directorio vivo."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from . import busqueda, db, duplicados, extraccion, fuentes, modelo
from .config import CONFIG

router = APIRouter(prefix="/api")


async def _cuerpo(request: Request) -> Dict[str, Any]:
    """Lee el JSON de la peticion. Si viene roto o vacio, es un 400, no un 500.

    Lo encontro la prueba de carga del Reto 7: un cuerpo mal formado hacia
    estallar el endpoint con un error interno, que es mentira — el servidor
    esta bien, quien mando mal la peticion es el cliente.
    """
    try:
        datos = await request.json()
    except Exception:
        raise HTTPException(400, "El cuerpo de la peticion no es JSON valido")
    if not isinstance(datos, dict):
        raise HTTPException(400, "Se esperaba un objeto JSON")
    return datos



# --------------------------------------------------------------------------
# Estado general
# --------------------------------------------------------------------------
@router.get("/metricas")
def metricas() -> Dict[str, Any]:
    fila = db.query_one(
        """SELECT (SELECT COUNT(*) FROM personas WHERE activo=1)        personas,
                  (SELECT COUNT(*) FROM personas WHERE activo=1 AND interno=1) internas,
                  (SELECT COUNT(*) FROM casos)                          casos,
                  (SELECT COUNT(*) FROM interacciones)                  hitos,
                  (SELECT COUNT(*) FROM interacciones WHERE persona_id IS NULL) sueltos,
                  (SELECT COUNT(*) FROM identificadores)                datos,
                  (SELECT COUNT(*) FROM fusiones WHERE deshecha=0)      fusiones""") or {}
    origenes = db.query(
        """SELECT COALESCE(origen,'manual') origen, COUNT(*) n FROM personas
           WHERE activo=1 GROUP BY origen ORDER BY n DESC""")
    ultimas = db.query("SELECT * FROM importaciones ORDER BY id DESC LIMIT 6")
    return {"resumen": fila, "origenes": origenes, "importaciones": ultimas,
            "config": CONFIG.as_dict()}


@router.get("/buscar")
def buscar(q: str = "", limite: int = 0) -> Dict[str, Any]:
    return busqueda.buscar(q, limite)


@router.get("/recientes")
def recientes(limite: int = 12) -> List[Dict[str, Any]]:
    """Con quien se ha tenido contacto ultimamente."""
    filas = db.query(
        """SELECT p.id, p.nombre, p.organizacion, p.rol, MAX(i.ts) ultimo_ts,
                  COUNT(*) hitos
           FROM interacciones i JOIN personas p ON p.id = i.persona_id
           WHERE p.activo=1 GROUP BY p.id ORDER BY ultimo_ts DESC LIMIT ?""", (limite,))
    return filas


# --------------------------------------------------------------------------
# Personas
# --------------------------------------------------------------------------
def _persona_o_404(persona_id: int) -> Dict[str, Any]:
    """Comprueba que la ficha existe antes de escribir sobre ella.

    Sin esto, escribir en una ficha inexistente reventaba con un 500 de clave
    foranea, o —peor— devolvia 200 sin haber hecho nada. Lo encontro la prueba
    de carga del Reto 7 al ejecutarse contra una base vacia.
    """
    fila = db.query_one("SELECT * FROM personas WHERE id=?", (persona_id,))
    if not fila:
        raise HTTPException(404, f"No existe la ficha {persona_id}")
    return fila
@router.get("/personas")
def listar_personas(limite: int = 60, interno: Optional[int] = None) -> List[Dict[str, Any]]:
    sql = ["SELECT id FROM personas WHERE activo=1"]
    params: List[Any] = []
    if interno is not None:
        sql.append("AND interno=?")
        params.append(int(interno))
    sql.append("ORDER BY nombre LIMIT ?")
    params.append(limite)
    return [modelo.resumen_persona(f["id"]) for f in db.query(" ".join(sql), params)]


@router.get("/personas/{persona_id}")
def ver_persona(persona_id: int) -> Dict[str, Any]:
    ficha = modelo.ficha(persona_id)
    if not ficha:
        raise HTTPException(404, "Esa ficha no existe")
    ficha["fusiones"] = [
        {**f, "motivos": json.loads(f.get("motivos_json") or "[]")}
        for f in ficha.get("fusiones", [])]
    return ficha


@router.post("/personas")
async def crear_persona(request: Request) -> Dict[str, Any]:
    datos = await _cuerpo(request)
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise HTTPException(400, "Hace falta un nombre")
    identificadores = [(d.get("tipo") or "telefono", d.get("valor") or "",
                        d.get("etiqueta") or "")
                       for d in (datos.get("identificadores") or []) if d.get("valor")]
    if datos.get("aparte"):
        # Un telefono compartido no hace a dos personas la misma: el conmutador de
        # un despacho aparece en la firma de cada abogado que trabaja ahi.
        persona_id = modelo.crear_persona(
            nombre, organizacion=(datos.get("organizacion") or "").strip(),
            rol=(datos.get("rol") or "").strip(),
            lugar=(datos.get("lugar") or "").strip(),
            origen="manual", interno=bool(datos.get("interno")))
        for tipo, valor, etiqueta in identificadores:
            modelo.agregar_identificador(persona_id, tipo, valor, etiqueta, "manual")
        creada = True
        if datos.get("distinta_de"):
            duplicados.descartar(persona_id, int(datos["distinta_de"]))
    else:
        persona_id, creada = modelo.asegurar_persona(
            nombre, identificadores=identificadores,
            organizacion=(datos.get("organizacion") or "").strip(),
            rol=(datos.get("rol") or "").strip(),
            lugar=(datos.get("lugar") or "").strip(),
            origen="manual", interno=bool(datos.get("interno")))

    notas = (datos.get("notas") or "").strip()
    if notas:
        actual = db.query_one("SELECT notas FROM personas WHERE id=?", (persona_id,)) or {}
        previo = (actual.get("notas") or "").strip()
        modelo.actualizar_persona(
            persona_id, notas=(previo + "\n" + notas).strip() if previo else notas)

    expediente = (datos.get("expediente") or "").strip()
    if expediente:
        caso_id = modelo.asegurar_caso(expediente)
        modelo.asegurar_participacion(persona_id, caso_id,
                                      (datos.get("rol_caso") or datos.get("rol") or "").strip(),
                                      origen="alta manual")
    modelo.registrar_interaccion(
        persona_id, "hecho", db.now_iso(),
        "Ficha creada a mano" if creada else "Ficha completada a mano",
        detalle=datos.get("fuente_texto", "")[:400], origen="manual")
    return {"id": persona_id, "creada": creada, "ficha": modelo.ficha(persona_id)}


@router.patch("/personas/{persona_id}")
async def editar_persona(persona_id: int, request: Request) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    datos = await _cuerpo(request)
    modelo.actualizar_persona(persona_id, **datos)
    return modelo.ficha(persona_id) or {}


@router.post("/personas/{persona_id}/identificadores")
async def agregar_identificador(persona_id: int, request: Request) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    datos = await _cuerpo(request)
    valor = (datos.get("valor") or "").strip()
    if not valor:
        raise HTTPException(400, "Falta el dato")
    modelo.agregar_identificador(persona_id, datos.get("tipo") or "telefono", valor,
                                 datos.get("etiqueta") or "", "manual")
    return {"identificadores": modelo.identificadores_de(persona_id)}


@router.delete("/personas/{persona_id}/identificadores")
async def quitar_identificador(persona_id: int, tipo: str, valor: str) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    db.execute("DELETE FROM identificadores WHERE persona_id=? AND tipo=? AND valor_norm=?",
               (persona_id, tipo, modelo.normalizar(tipo, valor)))
    return {"identificadores": modelo.identificadores_de(persona_id)}


@router.post("/personas/{persona_id}/nota")
async def agregar_nota(persona_id: int, request: Request) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    datos = await _cuerpo(request)
    texto = (datos.get("texto") or "").strip()
    if not texto:
        raise HTTPException(400, "La nota esta vacia")
    caso_id = None
    expediente = (datos.get("expediente") or "").strip()
    if expediente:
        caso_id = modelo.asegurar_caso(expediente)
    modelo.registrar_interaccion(persona_id, "nota", db.now_iso(), texto[:120],
                                 detalle=texto, caso_id=caso_id, origen="manual")
    return modelo.ficha(persona_id) or {}


@router.post("/personas/{persona_id}/casos")
async def vincular_caso(persona_id: int, request: Request) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    datos = await _cuerpo(request)
    expediente = (datos.get("expediente") or "").strip()
    if not expediente:
        raise HTTPException(400, "Falta el expediente")
    caso_id = modelo.asegurar_caso(expediente, nombre=(datos.get("nombre") or "").strip())
    modelo.asegurar_participacion(persona_id, caso_id, (datos.get("rol") or "").strip(),
                                  origen="manual")
    return modelo.ficha(persona_id) or {}


@router.delete("/personas/{persona_id}")
def archivar_persona(persona_id: int) -> Dict[str, Any]:
    _persona_o_404(persona_id)
    modelo.actualizar_persona(persona_id, activo=0)
    return {"ok": True}


# --------------------------------------------------------------------------
# Casos: quien es quien
# --------------------------------------------------------------------------
@router.get("/casos")
def listar_casos(limite: int = 60) -> List[Dict[str, Any]]:
    return db.query(
        """SELECT c.*, (SELECT COUNT(*) FROM participaciones p WHERE p.caso_id=c.id) partes
           FROM casos c ORDER BY c.id DESC LIMIT ?""", (limite,))


@router.get("/casos/{caso_id}")
def ver_caso(caso_id: int) -> Dict[str, Any]:
    caso = db.query_one("SELECT * FROM casos WHERE id=?", (caso_id,))
    if not caso:
        raise HTTPException(404, "Ese expediente no existe")
    caso["partes"] = db.query(
        """SELECT p.id, p.nombre, p.organizacion, p.rol AS rol_persona, pa.rol,
                  pa.origen AS rol_origen, pa.confianza
           FROM participaciones pa JOIN personas p ON p.id = pa.persona_id
           WHERE pa.caso_id=? AND p.activo=1 ORDER BY pa.rol, p.nombre""", (caso_id,))
    for parte in caso["partes"]:
        parte["identificadores"] = modelo.identificadores_de(parte["id"])
    caso["linea"] = db.query(
        """SELECT i.tipo, i.ts, i.titulo, i.detalle, i.origen, p.nombre AS persona,
                  i.persona_id
           FROM interacciones i LEFT JOIN personas p ON p.id = i.persona_id
           WHERE i.caso_id=? ORDER BY i.ts DESC, i.id DESC LIMIT 60""", (caso_id,))
    return caso


# --------------------------------------------------------------------------
# Alta en un paso: pegar una firma y leerla
# --------------------------------------------------------------------------
@router.post("/leer")
async def leer_texto(request: Request) -> Dict[str, Any]:
    datos = await _cuerpo(request)
    lectura = extraccion.leer(datos.get("texto") or "")
    campos = lectura["campos"]
    coincide = None
    for ident in lectura["identificadores"]:
        encontrada = modelo.buscar_por_identificador(ident["tipo"], ident["valor"])
        if encontrada:
            coincide = {"id": encontrada["id"], "nombre": encontrada["nombre"],
                        "por": f"ya tienes ese {ident['etiqueta'] or ident['tipo']}"}
            break
    if not coincide and campos.get("nombre"):
        encontrada = modelo.buscar_por_nombre(campos["nombre"])
        if encontrada:
            coincide = {"id": encontrada["id"], "nombre": encontrada["nombre"],
                        "por": "ya existe una ficha con ese nombre"}
    lectura["coincide"] = coincide
    return lectura


# --------------------------------------------------------------------------
# Duplicados
# --------------------------------------------------------------------------
@router.get("/duplicados")
def ver_duplicados(limite: int = 50) -> List[Dict[str, Any]]:
    return duplicados.detectar(limite)


@router.post("/duplicados/fusionar")
async def fusionar(request: Request) -> Dict[str, Any]:
    datos = await _cuerpo(request)
    try:
        return duplicados.fusionar(int(datos["principal_id"]), int(datos["absorbida_id"]),
                                   datos.get("motivos") or [],
                                   float(datos.get("confianza") or 0))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/duplicados/descartar")
async def descartar(request: Request) -> Dict[str, Any]:
    datos = await _cuerpo(request)
    return duplicados.descartar(int(datos["a_id"]), int(datos["b_id"]))


@router.get("/fusiones")
def listar_fusiones(limite: int = 30) -> List[Dict[str, Any]]:
    filas = db.query(
        """SELECT f.*, pp.nombre AS principal, pa.nombre AS absorbida
           FROM fusiones f
           LEFT JOIN personas pp ON pp.id = f.principal_id
           LEFT JOIN personas pa ON pa.id = f.absorbida_id
           ORDER BY f.id DESC LIMIT ?""", (limite,))
    for fila in filas:
        try:
            fila["motivos"] = json.loads(fila.pop("motivos_json") or "[]")
        except json.JSONDecodeError:
            fila["motivos"] = []
        fila.pop("movido_json", None)
    return filas


@router.post("/fusiones/{fusion_id}/deshacer")
def deshacer(fusion_id: int) -> Dict[str, Any]:
    try:
        return duplicados.deshacer(fusion_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# --------------------------------------------------------------------------
# Fuentes
# --------------------------------------------------------------------------
@router.get("/fuentes")
def ver_fuentes() -> Dict[str, Any]:
    from .config import DOCS_DB, SAMPLE_DIR
    nomina, llamadas = fuentes.ruta_nomina(), fuentes.ruta_llamadas()
    return {
        "historial": db.query("SELECT * FROM importaciones ORDER BY id DESC LIMIT 25"),
        "disponibles": [
            {"clave": "nomina", "nombre": "Nomina del despacho",
             "detalle": "Quien trabaja aqui, su area y su extension",
             "ruta": str(nomina or SAMPLE_DIR / "(*Biometric*.xlsx)"),
             "listo": bool(nomina)},
            {"clave": "llamadas", "nombre": "Llamadas (RingCentral)",
             "detalle": "Historial de llamadas; crea ficha solo con trato sostenido",
             "ruta": str(llamadas or SAMPLE_DIR / "(*RingCentral*.xlsx)"),
             "listo": bool(llamadas)},
            {"clave": "documentos", "nombre": "Documentos de DocuFlow AI",
             "detalle": "Partes, abogados y expedientes de lo ya clasificado",
             "ruta": str(DOCS_DB), "listo": DOCS_DB.exists()},
        ],
    }


@router.post("/importar/{clave}")
async def importar(clave: str) -> Dict[str, Any]:
    acciones = {"nomina": fuentes.importar_nomina,
                "llamadas": fuentes.importar_llamadas,
                "documentos": fuentes.importar_documentos}
    if clave == "todo":
        return {"resultados": await run_in_threadpool(fuentes.importar_todo)}
    if clave not in acciones:
        raise HTTPException(404, f"No conozco la fuente '{clave}'")
    return {"resultados": [await run_in_threadpool(acciones[clave])]}


# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------
@router.get("/config")
def ver_config() -> Dict[str, Any]:
    return CONFIG.as_dict()


@router.post("/config")
async def poner_config(request: Request) -> Dict[str, Any]:
    return CONFIG.update(await _cuerpo(request))

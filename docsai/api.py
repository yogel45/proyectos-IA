"""Endpoints REST del modulo de documentos."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from . import db
from .config import CONFIG, ENTRADA_DIR
from . import classify, naming, pipeline
from .extract import SOPORTADOS

router = APIRouter(prefix="/api")


def _fila(doc: Dict[str, Any], con_texto: bool = False) -> Dict[str, Any]:
    salida = dict(doc)
    for clave, destino in (("evidencia_json", "evidencia"), ("puntajes_json", "puntajes"),
                           ("entidades_json", "entidades")):
        try:
            salida[destino] = json.loads(salida.pop(clave) or ("[]" if "evid" in clave else "{}"))
        except (json.JSONDecodeError, TypeError):
            salida[destino] = [] if "evid" in clave else {}
    texto = salida.pop("texto", "") or ""
    if con_texto:
        salida["texto"] = texto[:12000]
        salida["texto_truncado"] = len(texto) > 12000
    return salida


# --------------------------------------------------------------------------
# Catalogos y configuracion (antes de las rutas con {id})
# --------------------------------------------------------------------------
@router.get("/categorias")
def categorias() -> List[Dict[str, Any]]:
    return classify.catalogo()


@router.get("/convencion")
def convencion() -> Dict[str, Any]:
    return naming.describir_convencion()


@router.post("/convencion")
async def guardar_convencion(request: Request) -> Dict[str, Any]:
    datos = await request.json()
    permitidas = {"plantilla_nombre", "separador", "max_nombre", "esquema_carpetas",
                  "umbral_revision", "conservar_original", "guardar_texto",
                  "max_trabajos"}
    CONFIG.update({k: v for k, v in datos.items() if k in permitidas})
    return naming.describir_convencion()


@router.get("/metricas")
def metricas() -> Dict[str, Any]:
    return pipeline.metricas()


@router.post("/renombrar-todos")
async def renombrar_todos() -> Dict[str, Any]:
    return await run_in_threadpool(pipeline.renombrar_todos)


# --------------------------------------------------------------------------
# Carga y procesamiento
# --------------------------------------------------------------------------
@router.post("/upload")
async def subir(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    rutas, nombres, rechazados = [], [], []
    for archivo in files:
        nombre = archivo.filename or "documento"
        extension = Path(nombre).suffix.lower()
        if extension not in SOPORTADOS:
            rechazados.append({"archivo": nombre, "motivo": f"formato {extension} no soportado"})
            continue
        destino = ENTRADA_DIR / f"{uuid.uuid4().hex[:8]}_{Path(nombre).name}"
        with destino.open("wb") as fh:
            shutil.copyfileobj(archivo.file, fh)
        rutas.append(destino)
        nombres.append(nombre)
    if not rutas:
        raise HTTPException(400, f"Ningun archivo utilizable. {rechazados}")
    lote = await run_in_threadpool(pipeline.COLA.enviar, rutas, nombres)
    return {"ok": True, "lote": lote.como_dict(), "rechazados": rechazados}


@router.post("/procesar-entrada")
async def procesar_entrada() -> Dict[str, Any]:
    """Procesa lo que ya este en data/documentos/entrada (carpeta vigilada)."""
    pendientes = [p for p in sorted(ENTRADA_DIR.glob("*"))
                  if p.is_file() and p.suffix.lower() in SOPORTADOS]
    if not pendientes:
        return {"ok": True, "mensaje": "La carpeta de entrada esta vacia.", "lote": None}
    lote = await run_in_threadpool(pipeline.COLA.enviar, pendientes,
                                   [p.name for p in pendientes])
    return {"ok": True, "lote": lote.como_dict(),
            "mensaje": f"{len(pendientes)} documento(s) en proceso."}


@router.get("/lotes")
def lotes() -> List[Dict[str, Any]]:
    return pipeline.COLA.listar()


@router.get("/lotes/{lote_id}")
def lote(lote_id: str) -> Dict[str, Any]:
    encontrado = pipeline.COLA.obtener(lote_id)
    if not encontrado:
        raise HTTPException(404, "Lote no encontrado")
    return encontrado.como_dict()


# --------------------------------------------------------------------------
# Consulta y revision
# --------------------------------------------------------------------------
@router.get("/documentos")
def listar(estado: str = "", categoria: str = "", expediente: str = "",
           q: str = "", limite: int = 200) -> List[Dict[str, Any]]:
    sql = """SELECT id, nombre_original, nombre_propuesto, nombre_final, carpeta,
                    categoria, categoria_nombre, confianza, estado, corregido,
                    expediente, fecha_doc, titulo, paginas, bytes, extension,
                    metodo, metodo_extraccion, requiere_ocr, duplicado_de, creado
             FROM documentos WHERE 1=1"""
    params: List[Any] = []
    if estado:
        sql += " AND estado=?"
        params.append(estado)
    if categoria:
        sql += " AND categoria=?"
        params.append(categoria)
    if expediente:
        sql += " AND expediente=?"
        params.append(expediente)
    if q:
        sql += (" AND (nombre_original LIKE ? OR nombre_final LIKE ? OR titulo LIKE ?"
                " OR expediente LIKE ? OR texto LIKE ?)")
        params += [f"%{q}%"] * 5
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limite, 1000)))
    return db.query(sql, params)


@router.get("/export.csv")
def exportar() -> Any:
    import csv
    import io

    from starlette.responses import StreamingResponse

    filas = db.query(
        """SELECT id, nombre_original, nombre_final, carpeta, categoria, categoria_nombre,
                  ROUND(confianza,3) confianza, estado, corregido, expediente, fecha_doc,
                  titulo, paginas, bytes, metodo, metodo_extraccion, creado
           FROM documentos ORDER BY id""")
    buffer = io.StringIO()
    if filas:
        escritor = csv.DictWriter(buffer, fieldnames=list(filas[0].keys()))
        escritor.writeheader()
        escritor.writerows(filas)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="documentos.csv"'})


@router.get("/documentos/{documento_id}")
def detalle(documento_id: int) -> Dict[str, Any]:
    doc = db.query_one("SELECT * FROM documentos WHERE id=?", (documento_id,))
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    return _fila(doc, con_texto=True)


@router.get("/documentos/{documento_id}/archivo")
def archivo(documento_id: int) -> FileResponse:
    doc = db.query_one("SELECT ruta_archivada, nombre_final FROM documentos WHERE id=?",
                       (documento_id,))
    if not doc or not doc["ruta_archivada"] or not Path(doc["ruta_archivada"]).exists():
        raise HTTPException(404, "El archivo no esta disponible")
    return FileResponse(doc["ruta_archivada"], filename=doc["nombre_final"])


@router.post("/documentos/{documento_id}/reclasificar")
async def reclasificar(documento_id: int, request: Request) -> Dict[str, Any]:
    datos = await request.json()
    categoria = (datos.get("categoria") or "").strip().upper()
    validas = {c["codigo"] for c in classify.catalogo()}
    if categoria not in validas:
        raise HTTPException(400, f"Categoria desconocida: {categoria}")
    doc = await run_in_threadpool(pipeline.reclasificar, documento_id, categoria,
                                  bool(datos.get("aprender", True)))
    return _fila(doc)


@router.post("/documentos/{documento_id}/aprobar")
async def aprobar(documento_id: int) -> Dict[str, Any]:
    doc = await run_in_threadpool(pipeline.aprobar, documento_id)
    return _fila(doc)


@router.delete("/documentos/{documento_id}")
def eliminar(documento_id: int) -> Dict[str, Any]:
    doc = db.query_one("SELECT ruta_archivada FROM documentos WHERE id=?", (documento_id,))
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    db.execute("DELETE FROM documentos WHERE id=?", (documento_id,))
    return {"ok": True, "archivo_conservado": doc["ruta_archivada"]}

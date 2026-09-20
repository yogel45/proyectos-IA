"""Flujo automatico de documentos: de un archivo suelto a un archivo archivado.

    carga -> huella -> extraccion -> entidades -> clasificacion -> nombre
          -> archivado en carpetas -> registro en la base -> revision humana

El flujo es *semiautomatico* a proposito: todo se procesa solo, pero los
documentos cuya clasificacion no alcanza la confianza minima quedan marcados
para que una persona los confirme. Cada correccion se guarda como ejemplo de
entrenamiento, asi que el sistema mejora con el uso.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import db
from .config import CONFIG, ENTRADA_DIR, ORGANIZADOS_DIR
from . import classify, naming
from .entities import Entidades, extraer_entidades
from .extract import SOPORTADOS, extraer

log = logging.getLogger("officevision.docs")


def huella(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Procesamiento de un documento
# --------------------------------------------------------------------------
def procesar(ruta: Path, nombre_original: Optional[str] = None) -> Dict[str, Any]:
    nombre_original = nombre_original or ruta.name
    ahora = db.now_iso()
    sha = huella(ruta)

    # --- duplicado exacto -------------------------------------------------
    previo = db.query_one(
        "SELECT id, nombre_final, nombre_propuesto, ruta_archivada FROM documentos "
        "WHERE hash_sha256=? AND estado <> 'duplicado' ORDER BY id LIMIT 1", (sha,))
    if previo:
        doc_id = db.execute(
            """INSERT INTO documentos (nombre_original, nombre_propuesto, ruta_origen,
                   extension, bytes, hash_sha256, duplicado_de, categoria,
                   categoria_nombre, confianza, motivo, estado, creado, actualizado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,'duplicado',?,?)""",
            (nombre_original, previo["nombre_final"] or previo["nombre_propuesto"],
             str(ruta), ruta.suffix.lower(), ruta.stat().st_size, sha, previo["id"],
             "DUPLICADO", "Duplicado", 1.0,
             f"Mismo contenido (SHA-256) que el documento #{previo['id']}.",
             ahora, ahora))
        return dict(db.query_one("SELECT * FROM documentos WHERE id=?", (doc_id,)))

    # --- extraccion -------------------------------------------------------
    ext = extraer(ruta)
    if ext.error and not ext.texto:
        doc_id = db.execute(
            """INSERT INTO documentos (nombre_original, nombre_propuesto, ruta_origen,
                   extension, bytes, hash_sha256, categoria, categoria_nombre,
                   confianza, motivo, estado, error, creado, actualizado)
               VALUES (?,?,?,?,?,?,?,?,?,?,'error',?,?,?)""",
            (nombre_original, nombre_original, str(ruta), ruta.suffix.lower(),
             ruta.stat().st_size, sha, "SIN-CLASIFICAR", "Sin clasificar", 0.0,
             ext.error, ext.error, ahora, ahora))
        return dict(db.query_one("SELECT * FROM documentos WHERE id=?", (doc_id,)))

    # --- entidades y clasificacion ---------------------------------------
    entidades = extraer_entidades(
        ext.texto, ext.metadatos, nombre_original,
        respaldo_fecha=datetime.fromtimestamp(ruta.stat().st_mtime))
    resultado = classify.clasificar(ext.texto, entidades.titulo, nombre_original)

    umbral = float(CONFIG.get("umbral_revision") or classify.UMBRAL_REVISION)
    requiere_revision = resultado.confianza < umbral
    if ext.requiere_ocr and not ext.ocr_disponible:
        requiere_revision = True
        resultado.motivo += (" El documento parece escaneado y no hay OCR disponible: "
                             "la clasificacion se hizo con poco texto.")

    # --- nombre y archivado ----------------------------------------------
    nombre = naming.construir(entidades, resultado.categoria, entidades.titulo,
                              nombre_original, sha[:8])
    destino_dir = ORGANIZADOS_DIR / nombre.carpeta if nombre.carpeta else ORGANIZADOS_DIR
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = naming.version_disponible(destino_dir, nombre)
    try:
        if CONFIG.get("conservar_original"):
            shutil.copy2(ruta, destino)
        else:
            shutil.move(str(ruta), destino)
    except OSError as exc:                       # el registro vale aunque falle el copiado
        log.warning("No se pudo archivar %s: %s", nombre_original, exc)
        destino = None

    doc_id = db.execute(
        """INSERT INTO documentos (nombre_original, nombre_propuesto, nombre_final,
               ruta_origen, ruta_archivada, carpeta, extension, bytes, hash_sha256,
               categoria, categoria_nombre, confianza, metodo, motivo, evidencia_json,
               puntajes_json, entidades_json, expediente, fecha_doc, titulo, paginas,
               caracteres, idioma, metodo_extraccion, requiere_ocr, texto, estado,
               creado, actualizado)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (nombre_original, nombre.nombre, destino.name if destino else None,
         str(ruta), str(destino) if destino else None, nombre.carpeta,
         ruta.suffix.lower(), ruta.stat().st_size, sha,
         resultado.categoria, resultado.nombre, resultado.confianza, resultado.metodo,
         resultado.motivo, json.dumps(resultado.evidencia[:12], ensure_ascii=False),
         json.dumps({k: round(v, 2) for k, v in resultado.puntajes.items()}),
         json.dumps(entidades.como_dict(), ensure_ascii=False),
         entidades.expediente, entidades.fecha, entidades.titulo, ext.paginas,
         ext.caracteres, ext.idioma_probable, ext.metodo, 1 if ext.requiere_ocr else 0,
         (ext.texto[:60000] if CONFIG.get("guardar_texto") else ""),
         "revision" if requiere_revision else "procesado", ahora, ahora))
    return dict(db.query_one("SELECT * FROM documentos WHERE id=?", (doc_id,)))


# --------------------------------------------------------------------------
# Correcciones y reorganizacion
# --------------------------------------------------------------------------
def reclasificar(documento_id: int, categoria: str,
                 aprender: bool = True) -> Dict[str, Any]:
    """Corrige la categoria, renombra y mueve el archivo, y entrena el modelo."""
    doc = db.query_one("SELECT * FROM documentos WHERE id=?", (documento_id,))
    if not doc:
        raise ValueError("Documento no encontrado")

    entidades = _entidades_desde(doc)
    nombre = naming.construir(entidades, categoria, doc["titulo"] or "",
                              doc["nombre_original"], (doc["hash_sha256"] or "")[:8])
    destino_final = _mover_archivado(doc, nombre)

    db.execute(
        """UPDATE documentos SET categoria=?, categoria_nombre=?, nombre_propuesto=?,
               nombre_final=?, carpeta=?, ruta_archivada=?, estado='aprobado',
               corregido=1, confianza=1.0, metodo='correccion humana',
               motivo=?, actualizado=? WHERE id=?""",
        (categoria, classify.nombre_categoria(categoria), nombre.nombre,
         Path(destino_final).name if destino_final else nombre.nombre,
         nombre.carpeta, destino_final,
         f"Categoria confirmada por una persona (antes: {doc['categoria']}).",
         db.now_iso(), documento_id))

    if aprender and doc["texto"]:
        classify.registrar_correccion(doc["texto"], categoria, documento_id)
    return dict(db.query_one("SELECT * FROM documentos WHERE id=?", (documento_id,)))


def aprobar(documento_id: int, aprender: bool = True) -> Dict[str, Any]:
    """Confirma la clasificacion propuesta tal cual."""
    doc = db.query_one("SELECT * FROM documentos WHERE id=?", (documento_id,))
    if not doc:
        raise ValueError("Documento no encontrado")
    db.execute("UPDATE documentos SET estado='aprobado', actualizado=? WHERE id=?",
               (db.now_iso(), documento_id))
    if aprender and doc["texto"] and doc["categoria"] != "SIN-CLASIFICAR":
        classify.registrar_correccion(doc["texto"], doc["categoria"], documento_id)
    return dict(db.query_one("SELECT * FROM documentos WHERE id=?", (documento_id,)))


def reprocesar(solo_revision: bool = True) -> Dict[str, Any]:
    """Vuelve a clasificar documentos ya guardados con las reglas actuales.

    Sirve despues de crear una categoria nueva o de afinar sus terminos: no hace
    falta volver a subir nada, se reaprovecha el texto ya extraido.
    """
    condicion = "WHERE estado IN ('revision','procesado')" if solo_revision else \
                "WHERE estado <> 'duplicado'"
    filas = db.query(f"SELECT id FROM documentos {condicion} ORDER BY id")
    cambiados, revisados = 0, 0
    for fila in filas:
        doc = db.query_one("SELECT * FROM documentos WHERE id=?", (fila["id"],))
        if not doc or not doc["texto"]:
            continue
        revisados += 1
        anterior = doc["categoria"]
        resultado = classify.clasificar(doc["texto"], doc["titulo"] or "",
                                        doc["nombre_original"])
        umbral = float(CONFIG.get("umbral_revision") or classify.UMBRAL_REVISION)
        entidades = _entidades_desde(doc)
        nombre = naming.construir(entidades, resultado.categoria, doc["titulo"] or "",
                                  doc["nombre_original"], (doc["hash_sha256"] or "")[:8])
        destino_final = _mover_archivado(doc, nombre)
        db.execute(
            """UPDATE documentos SET categoria=?, categoria_nombre=?, confianza=?,
                   metodo=?, motivo=?, evidencia_json=?, puntajes_json=?,
                   nombre_propuesto=?, nombre_final=?, carpeta=?, ruta_archivada=?,
                   estado=?, actualizado=? WHERE id=?""",
            (resultado.categoria, resultado.nombre, resultado.confianza,
             resultado.metodo, resultado.motivo,
             json.dumps(resultado.evidencia[:12], ensure_ascii=False),
             json.dumps({k: round(v, 2) for k, v in resultado.puntajes.items()}),
             nombre.nombre,
             Path(destino_final).name if destino_final else nombre.nombre,
             nombre.carpeta, destino_final,
             "revision" if resultado.confianza < umbral else "procesado",
             db.now_iso(), doc["id"]))
        if resultado.categoria != anterior:
            cambiados += 1
    return {"revisados": revisados, "cambiados": cambiados, "total": len(filas)}


def _entidades_desde(doc: Dict[str, Any]) -> Entidades:
    datos = json.loads(doc["entidades_json"] or "{}")
    return Entidades(**{k: v for k, v in datos.items()
                        if k in Entidades.__dataclass_fields__})


def _mover_archivado(doc: Dict[str, Any], nombre: naming.Nombre) -> Optional[str]:
    """Mueve el archivo a la carpeta que le toca con su nombre nuevo."""
    if not doc["ruta_archivada"]:
        return doc["ruta_archivada"]
    origen = Path(doc["ruta_archivada"])
    destino_dir = ORGANIZADOS_DIR / nombre.carpeta if nombre.carpeta else ORGANIZADOS_DIR
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = naming.version_disponible(destino_dir, nombre)
    if origen.resolve() == destino.resolve():
        return str(origen)
    try:
        if origen.exists():
            shutil.move(str(origen), destino)
        return str(destino)
    except OSError as exc:
        log.warning("No se pudo mover %s: %s", origen, exc)
        return str(origen)


def renombrar_todos() -> Dict[str, int]:
    """Re-aplica la convencion vigente a todo lo archivado (tras cambiarla)."""
    filas = db.query("SELECT id FROM documentos WHERE estado IN ('procesado','revision','aprobado')")
    movidos = 0
    for fila in filas:
        doc = db.query_one("SELECT * FROM documentos WHERE id=?", (fila["id"],))
        try:
            reclasificar(doc["id"], doc["categoria"], aprender=False)
            movidos += 1
        except Exception as exc:  # pragma: no cover
            log.warning("No se pudo renombrar %s: %s", doc["id"], exc)
    return {"renombrados": movidos, "total": len(filas)}


# --------------------------------------------------------------------------
# Cola de trabajo
# --------------------------------------------------------------------------
@dataclass
class Lote:
    id: str
    total: int = 0
    procesados: int = 0
    estado: str = "en_proceso"
    resultados: List[Dict[str, Any]] = field(default_factory=list)
    iniciado: str = ""
    terminado: str = ""

    def como_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "total": self.total, "procesados": self.procesados,
                "estado": self.estado, "iniciado": self.iniciado,
                "terminado": self.terminado,
                "progreso": round(self.procesados / self.total * 100, 1) if self.total else 0,
                "resultados": [
                    {k: r.get(k) for k in ("id", "nombre_original", "nombre_final",
                                           "categoria", "categoria_nombre", "confianza",
                                           "estado", "expediente", "fecha_doc")}
                    for r in self.resultados]}


class Cola:
    def __init__(self) -> None:
        self.pool = ThreadPoolExecutor(
            max_workers=max(1, int(CONFIG.get("max_trabajos") or 3)),
            thread_name_prefix="docjob")
        self.lotes: Dict[str, Lote] = {}
        self._lock = threading.Lock()

    def enviar(self, rutas: List[Path], nombres: Optional[List[str]] = None) -> Lote:
        lote = Lote(id=uuid.uuid4().hex[:10], total=len(rutas), iniciado=db.now_iso())
        with self._lock:
            self.lotes[lote.id] = lote
        nombres = nombres or [r.name for r in rutas]
        for ruta, nombre in zip(rutas, nombres):
            self.pool.submit(self._trabajo, lote, ruta, nombre)
        return lote

    def _trabajo(self, lote: Lote, ruta: Path, nombre: str) -> None:
        try:
            resultado = procesar(ruta, nombre)
        except Exception as exc:  # pragma: no cover
            log.exception("Error procesando %s", nombre)
            resultado = {"nombre_original": nombre, "estado": "error",
                         "categoria": "SIN-CLASIFICAR", "motivo": str(exc)}
        with self._lock:
            lote.resultados.append(resultado)
            lote.procesados += 1
            if lote.procesados >= lote.total:
                lote.estado = "terminado"
                lote.terminado = db.now_iso()

    def obtener(self, lote_id: str) -> Optional[Lote]:
        return self.lotes.get(lote_id)

    def listar(self) -> List[Dict[str, Any]]:
        return sorted((l.como_dict() for l in self.lotes.values()),
                      key=lambda l: l["iniciado"], reverse=True)


COLA = Cola()


# --------------------------------------------------------------------------
# Metricas
# --------------------------------------------------------------------------
def metricas() -> Dict[str, Any]:
    resumen = db.query_one(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN estado='revision' THEN 1 ELSE 0 END) en_revision,
                  SUM(CASE WHEN estado='aprobado' THEN 1 ELSE 0 END) aprobados,
                  SUM(CASE WHEN estado='duplicado' THEN 1 ELSE 0 END) duplicados,
                  SUM(CASE WHEN estado='error' THEN 1 ELSE 0 END) errores,
                  SUM(CASE WHEN corregido=1 THEN 1 ELSE 0 END) corregidos,
                  ROUND(AVG(confianza),3) confianza_media,
                  SUM(paginas) paginas, SUM(bytes) bytes
           FROM documentos""") or {}
    por_categoria = db.query(
        """SELECT categoria, categoria_nombre, COUNT(*) n, ROUND(AVG(confianza),3) confianza
           FROM documentos WHERE estado <> 'duplicado'
           GROUP BY categoria ORDER BY n DESC""")
    por_expediente = db.query(
        """SELECT expediente, COUNT(*) n, MIN(fecha_doc) desde, MAX(fecha_doc) hasta
           FROM documentos WHERE expediente IS NOT NULL AND expediente <> ''
           GROUP BY expediente ORDER BY n DESC LIMIT 15""")
    por_mes = db.query(
        """SELECT substr(fecha_doc,1,7) mes, COUNT(*) n FROM documentos
           WHERE fecha_doc IS NOT NULL AND fecha_doc <> ''
           GROUP BY mes ORDER BY mes DESC LIMIT 18""")
    entrenamiento = db.query_one(
        "SELECT COUNT(*) n, COUNT(DISTINCT categoria) categorias FROM doc_entrenamiento") or {}
    modelo = classify.modelo_actual()
    total = resumen.get("total") or 0
    automaticos = total - (resumen.get("en_revision") or 0) - (resumen.get("errores") or 0)
    return {
        "resumen": resumen,
        "tasa_automatica": round(automaticos / total * 100, 1) if total else 0.0,
        "por_categoria": por_categoria,
        "por_expediente": por_expediente,
        "por_mes": por_mes,
        "entrenamiento": {**entrenamiento, "modelo_activo": modelo.listo,
                          "minimo_para_activar": classify.MIN_EJEMPLOS_NB},
        "convencion": naming.describir_convencion(),
    }

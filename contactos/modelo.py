"""Operaciones sobre el directorio: normalizar, crear, enlazar y consultar.

La normalizacion es el corazon del sistema: si "Fry, Dona M.", "Dona M. Fry" y
un telefono suelto no se reconocen como la misma persona, todo lo demas sobra.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import db

TITULOS = {"dr", "dra", "mr", "mrs", "ms", "lic", "ing", "esq", "esquire", "md",
           "phd", "jr", "sr", "ii", "iii", "hon", "atty"}


def sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def norm_nombre(nombre: str) -> str:
    """Clave estable de un nombre: sin acentos, sin titulos y en orden alfabetico.

    Asi "Fry, Dona M.", "Dona M. Fry" y "DONA FRY" caen en la misma clave.
    """
    texto = sin_acentos(nombre or "").lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    partes = [p for p in texto.split() if p not in TITULOS and len(p) > 1]
    return " ".join(sorted(partes))


def norm_telefono(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    return digitos[-10:] if len(digitos) >= 10 else digitos


def norm_correo(valor: str) -> str:
    return (valor or "").strip().lower()


def normalizar(tipo: str, valor: str) -> str:
    if tipo == "telefono":
        return norm_telefono(valor)
    if tipo == "correo":
        return norm_correo(valor)
    return sin_acentos(valor or "").strip().lower()


def formatear_telefono(valor: str) -> str:
    d = norm_telefono(valor)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else (valor or "")


# --------------------------------------------------------------------------
# Personas
# --------------------------------------------------------------------------
def buscar_por_identificador(tipo: str, valor: str) -> Optional[Dict[str, Any]]:
    norma = normalizar(tipo, valor)
    if not norma:
        return None
    return db.query_one(
        """SELECT p.* FROM identificadores i JOIN personas p ON p.id = i.persona_id
           WHERE i.tipo=? AND i.valor_norm=? AND p.activo=1 LIMIT 1""", (tipo, norma))


def buscar_por_nombre(nombre: str) -> Optional[Dict[str, Any]]:
    clave = norm_nombre(nombre)
    if not clave:
        return None
    return db.query_one(
        "SELECT * FROM personas WHERE nombre_norm=? AND activo=1 LIMIT 1", (clave,))


def crear_persona(nombre: str, *, organizacion: str = "", rol: str = "",
                  lugar: str = "", origen: str = "manual", interno: bool = False,
                  notas: str = "") -> int:
    ahora = db.now_iso()
    return db.execute(
        """INSERT INTO personas (nombre, nombre_norm, organizacion, rol, lugar, notas,
                                 origen, interno, creado, actualizado)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (nombre.strip(), norm_nombre(nombre), organizacion.strip(), rol.strip(),
         lugar.strip(), notas.strip(), origen, 1 if interno else 0, ahora, ahora))


def asegurar_persona(nombre: str, *, identificadores: Optional[List[Tuple[str, str, str]]] = None,
                     organizacion: str = "", rol: str = "", lugar: str = "",
                     origen: str = "manual", interno: bool = False) -> Tuple[int, bool]:
    """Devuelve (id, creada). Busca primero por identificador y luego por nombre."""
    identificadores = identificadores or []
    for tipo, valor, _etiqueta in identificadores:
        encontrada = buscar_por_identificador(tipo, valor)
        if encontrada:
            _completar(encontrada, organizacion, rol, lugar, nombre)
            for t, v, e in identificadores:
                agregar_identificador(encontrada["id"], t, v, e, origen)
            return encontrada["id"], False

    if nombre.strip():
        encontrada = buscar_por_nombre(nombre)
        if encontrada:
            _completar(encontrada, organizacion, rol, lugar, nombre)
            for t, v, e in identificadores:
                agregar_identificador(encontrada["id"], t, v, e, origen)
            return encontrada["id"], False

    persona_id = crear_persona(nombre or "(sin nombre)", organizacion=organizacion,
                               rol=rol, lugar=lugar, origen=origen, interno=interno)
    for t, v, e in identificadores:
        agregar_identificador(persona_id, t, v, e, origen)
    return persona_id, True


def _completar(persona: Dict[str, Any], organizacion: str, rol: str, lugar: str,
               nombre: str) -> None:
    """Rellena solo los huecos: nunca pisa un dato que ya existe."""
    cambios: Dict[str, Any] = {}
    if organizacion and not persona.get("organizacion"):
        cambios["organizacion"] = organizacion
    if rol and not persona.get("rol"):
        cambios["rol"] = rol
    if lugar and not persona.get("lugar"):
        cambios["lugar"] = lugar
    # un nombre real sustituye a un marcador de numero suelto
    if nombre and persona.get("nombre", "").startswith("("):
        cambios["nombre"] = nombre.strip()
        cambios["nombre_norm"] = norm_nombre(nombre)
    if cambios:
        actualizar_persona(persona["id"], **cambios)


def actualizar_persona(persona_id: int, **campos: Any) -> None:
    permitidos = {"nombre", "nombre_norm", "organizacion", "rol", "lugar", "notas",
                  "interno", "activo", "fusionada_en"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if "nombre" in campos and "nombre_norm" not in campos:
        campos["nombre_norm"] = norm_nombre(str(campos["nombre"]))
    if not campos:
        return
    campos["actualizado"] = db.now_iso()
    sets = ", ".join(f"{k}=?" for k in campos)
    db.execute(f"UPDATE personas SET {sets} WHERE id=?", (*campos.values(), persona_id))


def agregar_identificador(persona_id: int, tipo: str, valor: str,
                          etiqueta: str = "", origen: str = "manual") -> None:
    norma = normalizar(tipo, valor)
    if not norma:
        return
    ya = db.query_one(
        "SELECT id FROM identificadores WHERE persona_id=? AND tipo=? AND valor_norm=?",
        (persona_id, tipo, norma))
    if ya:
        return
    presentacion = formatear_telefono(valor) if tipo == "telefono" else valor.strip()
    db.execute(
        """INSERT INTO identificadores (persona_id, tipo, valor, valor_norm, etiqueta,
                                        origen, creado)
           VALUES (?,?,?,?,?,?,?)""",
        (persona_id, tipo, presentacion, norma, etiqueta, origen, db.now_iso()))


# --------------------------------------------------------------------------
# Casos y participaciones
# --------------------------------------------------------------------------
def asegurar_caso(expediente: str, *, nombre: str = "", tribunal: str = "",
                  monto: Optional[float] = None) -> int:
    expediente = (expediente or "").strip()
    if not expediente:
        return 0
    fila = db.query_one("SELECT * FROM casos WHERE expediente=?", (expediente,))
    if fila:
        cambios = {}
        if nombre and not fila.get("nombre"):
            cambios["nombre"] = nombre
        if tribunal and not fila.get("tribunal"):
            cambios["tribunal"] = tribunal
        if monto and not fila.get("monto"):
            cambios["monto"] = monto
        if cambios:
            sets = ", ".join(f"{k}=?" for k in cambios)
            db.execute(f"UPDATE casos SET {sets} WHERE id=?", (*cambios.values(), fila["id"]))
        return fila["id"]
    return db.execute(
        """INSERT INTO casos (expediente, nombre, tribunal, monto, creado)
           VALUES (?,?,?,?,?)""",
        (expediente, nombre, tribunal, monto, db.now_iso()))


def asegurar_participacion(persona_id: int, caso_id: int, rol: str,
                           origen: str = "", confianza: float = 1.0) -> None:
    if not persona_id or not caso_id:
        return
    fila = db.query_one(
        "SELECT * FROM participaciones WHERE persona_id=? AND caso_id=?",
        (persona_id, caso_id))
    if fila:
        # se queda el rol de mayor confianza
        if rol and confianza > (fila["confianza"] or 0):
            db.execute(
                "UPDATE participaciones SET rol=?, origen=?, confianza=? WHERE id=?",
                (rol, origen, confianza, fila["id"]))
        return
    db.execute(
        """INSERT INTO participaciones (persona_id, caso_id, rol, origen, confianza, creado)
           VALUES (?,?,?,?,?,?)""",
        (persona_id, caso_id, rol, origen, confianza, db.now_iso()))


def registrar_interaccion(persona_id: Optional[int], tipo: str, ts: str, titulo: str, *,
                          detalle: str = "", caso_id: Optional[int] = None,
                          origen: str = "", referencia: str = "",
                          meta: Optional[Dict[str, Any]] = None) -> bool:
    """Guarda un hito. Devuelve False si ya estaba (se identifica por referencia)."""
    if referencia:
        ya = (db.query_one(
                  "SELECT id FROM interacciones WHERE tipo=? AND referencia=? AND persona_id=?",
                  (tipo, referencia, persona_id))
              if persona_id else
              db.query_one(
                  "SELECT id FROM interacciones WHERE tipo=? AND referencia=? "
                  "AND persona_id IS NULL", (tipo, referencia)))
        if ya:
            return False
    db.execute(
        """INSERT INTO interacciones (persona_id, caso_id, tipo, ts, titulo, detalle,
                                      origen, referencia, meta_json, creado)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (persona_id, caso_id, tipo, ts, titulo, detalle, origen, referencia,
         json.dumps(meta or {}, ensure_ascii=False), db.now_iso()))
    return True


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def identificadores_de(persona_id: int) -> List[Dict[str, Any]]:
    return db.query(
        "SELECT tipo, valor, etiqueta, origen FROM identificadores WHERE persona_id=? "
        "ORDER BY tipo, id", (persona_id,))


def ficha(persona_id: int) -> Optional[Dict[str, Any]]:
    persona = db.query_one("SELECT * FROM personas WHERE id=?", (persona_id,))
    if not persona:
        return None
    persona["identificadores"] = identificadores_de(persona_id)
    persona["casos"] = db.query(
        """SELECT c.id, c.expediente, c.nombre, c.tribunal, c.estado,
                  p.rol, p.origen AS rol_origen, p.confianza
           FROM participaciones p JOIN casos c ON c.id = p.caso_id
           WHERE p.persona_id=? ORDER BY c.id""", (persona_id,))
    from .config import CONFIG
    persona["linea"] = db.query(
        """SELECT i.tipo, i.ts, i.titulo, i.detalle, i.origen, c.expediente
           FROM interacciones i LEFT JOIN casos c ON c.id = i.caso_id
           WHERE i.persona_id=? ORDER BY i.ts DESC, i.id DESC LIMIT ?""",
        (persona_id, int(CONFIG.get("hitos_por_ficha") or 40)))
    persona["fusiones"] = db.query(
        "SELECT * FROM fusiones WHERE principal_id=? AND deshecha=0 ORDER BY id DESC",
        (persona_id,))
    return persona


def resumen_persona(persona_id: int) -> Dict[str, Any]:
    fila = db.query_one(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM interacciones i WHERE i.persona_id=p.id) hitos,
                  (SELECT MAX(ts) FROM interacciones i WHERE i.persona_id=p.id) ultimo_ts,
                  (SELECT titulo FROM interacciones i WHERE i.persona_id=p.id
                   ORDER BY ts DESC, id DESC LIMIT 1) ultimo
           FROM personas p WHERE p.id=?""", (persona_id,))
    if not fila:
        return {}
    fila["identificadores"] = identificadores_de(persona_id)
    return fila

"""Duplicados explicados y reversibles.

La critica al estado del arte era doble: las plataformas fusionan en bloque sin
decir en que se basan, y lo hecho no se puede deshacer. Aqui cada propuesta
llega con sus motivos escritos, se acepta de una en una y queda registrado que
se movio, de modo que siempre se puede volver atras.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple

from . import db, modelo
from .config import CONFIG


def _tokens(nombre: str) -> Set[str]:
    return set((modelo.norm_nombre(nombre) or "").split())


def _casi_igual(a: str, b: str) -> bool:
    """Dos palabras que difieren en una letra: 'states' y 'state', 'Gonzalez'
    y 'Gonzalez'. Los errores de tecleo y las erratas de un documento no
    deberian partir a una persona en dos fichas."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    corta, larga = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(larga)):
        if larga[:i] + larga[i + 1:] == corta:
            return True
    return False


def _parecido(a: str, b: str) -> float:
    """Similitud de nombres tolerante a erratas de una letra."""
    ta, tb = list(_tokens(a)), list(_tokens(b))
    if not ta or not tb:
        return 0.0
    emparejados, libres = 0, list(tb)
    for token in ta:
        for otro in libres:
            if _casi_igual(token, otro):
                emparejados += 1
                libres.remove(otro)
                break
    union = len(ta) + len(tb) - emparejados
    return emparejados / union if union else 0.0


def _descartados() -> Set[Tuple[int, int]]:
    return {(f["a_id"], f["b_id"]) for f in db.query("SELECT a_id, b_id FROM descartes")}


def detectar(limite: int = 50) -> List[Dict[str, Any]]:
    """Propone fusiones con su motivo. No toca nada."""
    umbral = float(CONFIG.get("umbral_duplicado") or 0.75)
    descartados = _descartados()
    personas = {p["id"]: p for p in db.query(
        "SELECT id, nombre, nombre_norm, organizacion, origen FROM personas WHERE activo=1")}
    propuestas: Dict[Tuple[int, int], Dict[str, Any]] = {}

    def sumar(a: int, b: int, motivo: str, confianza: float) -> None:
        if a == b:
            return
        par = (min(a, b), max(a, b))
        if par in descartados or (par[1], par[0]) in descartados:
            return
        actual = propuestas.setdefault(par, {"motivos": [], "confianza": 0.0})
        if motivo not in actual["motivos"]:
            actual["motivos"].append(motivo)
        actual["confianza"] = max(actual["confianza"], confianza)

    # --- 1. el mismo identificador en dos fichas --------------------------
    for tipo, etiqueta in (("telefono", "el mismo telefono aparece en las dos fichas"),
                           ("correo", "el mismo correo aparece en las dos fichas"),
                           ("extension", "las dos usan la misma extension")):
        for fila in db.query(
                """SELECT valor_norm, GROUP_CONCAT(DISTINCT persona_id) ids
                   FROM identificadores WHERE tipo=? GROUP BY valor_norm
                   HAVING COUNT(DISTINCT persona_id) > 1""", (tipo,)):
            ids = [int(x) for x in str(fila["ids"]).split(",") if x]
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    if a in personas and b in personas:
                        sumar(a, b, etiqueta, 0.95)

    # --- 2. el nombre normalizado coincide --------------------------------
    for fila in db.query(
            """SELECT nombre_norm, GROUP_CONCAT(id) ids FROM personas
               WHERE activo=1 AND nombre_norm <> '' GROUP BY nombre_norm
               HAVING COUNT(*) > 1"""):
        ids = [int(x) for x in str(fila["ids"]).split(",") if x]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sumar(a, b, "el nombre es el mismo salvo orden, acentos o titulos", 0.9)

    # --- 3. nombres muy parecidos que ademas comparten expediente ---------
    por_caso: Dict[int, List[int]] = {}
    for fila in db.query("SELECT caso_id, persona_id FROM participaciones"):
        por_caso.setdefault(fila["caso_id"], []).append(fila["persona_id"])
    for caso_id, ids in por_caso.items():
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if a not in personas or b not in personas:
                    continue
                similitud = _parecido(personas[a]["nombre"], personas[b]["nombre"])
                if similitud >= 0.6:
                    sumar(a, b, f"nombres casi iguales ({similitud:.0%}) y los dos "
                                f"estan en el mismo expediente", 0.85)

    # --- 4. nombres casi identicos aunque no compartan caso ---------------
    lista = list(personas.values())
    for i, a in enumerate(lista):
        for b in lista[i + 1:]:
            if abs(len(a["nombre"]) - len(b["nombre"])) > 12:
                continue
            similitud = _parecido(a["nombre"], b["nombre"])
            if similitud >= 0.8:
                exacto = _tokens(a["nombre"]) == _tokens(b["nombre"])
                sumar(a["id"], b["id"],
                      f"los nombres coinciden en un {similitud:.0%}" if exacto else
                      f"los nombres coinciden en un {similitud:.0%} "
                      f"(difieren en una letra)", 0.8)

    salida = []
    for (a, b), dato in propuestas.items():
        if dato["confianza"] < umbral:
            continue
        salida.append({
            "a": modelo.resumen_persona(a), "b": modelo.resumen_persona(b),
            "motivos": dato["motivos"], "confianza": round(dato["confianza"], 2),
        })
    salida.sort(key=lambda x: -x["confianza"])
    return salida[:limite]


# --------------------------------------------------------------------------
def fusionar(principal_id: int, absorbida_id: int,
             motivos: Optional[List[str]] = None, confianza: float = 0.0) -> Dict[str, Any]:
    """Une dos fichas dejando constancia de todo lo que se movio."""
    if principal_id == absorbida_id:
        raise ValueError("Son la misma ficha")
    principal = db.query_one("SELECT * FROM personas WHERE id=?", (principal_id,))
    absorbida = db.query_one("SELECT * FROM personas WHERE id=?", (absorbida_id,))
    if not principal or not absorbida:
        raise ValueError("Alguna de las fichas no existe")

    movido: Dict[str, Any] = {"identificadores": [], "interacciones": [],
                              "participaciones": [], "campos": {}}

    existentes = {(i["tipo"], modelo.normalizar(i["tipo"], i["valor"]))
                  for i in db.query(
                      "SELECT tipo, valor FROM identificadores WHERE persona_id=?",
                      (principal_id,))}
    for ident in db.query("SELECT * FROM identificadores WHERE persona_id=?", (absorbida_id,)):
        clave = (ident["tipo"], ident["valor_norm"])
        if clave in existentes:
            db.execute("DELETE FROM identificadores WHERE id=?", (ident["id"],))
            movido["identificadores"].append({"id": ident["id"], "borrado": True,
                                              "fila": {k: ident[k] for k in
                                                       ("tipo", "valor", "valor_norm",
                                                        "etiqueta", "origen")}})
            continue
        db.execute("UPDATE identificadores SET persona_id=? WHERE id=?",
                   (principal_id, ident["id"]))
        movido["identificadores"].append({"id": ident["id"], "borrado": False})

    for fila in db.query("SELECT id FROM interacciones WHERE persona_id=?", (absorbida_id,)):
        db.execute("UPDATE interacciones SET persona_id=? WHERE id=?",
                   (principal_id, fila["id"]))
        movido["interacciones"].append(fila["id"])

    for part in db.query("SELECT * FROM participaciones WHERE persona_id=?", (absorbida_id,)):
        choca = db.query_one(
            "SELECT * FROM participaciones WHERE persona_id=? AND caso_id=?",
            (principal_id, part["caso_id"]))
        if choca:
            db.execute("DELETE FROM participaciones WHERE id=?", (part["id"],))
            entrada = {"id": part["id"], "borrado": True,
                       "fila": {"caso_id": part["caso_id"], "rol": part["rol"],
                                "origen": part["origen"], "confianza": part["confianza"]}}
            # si la ficha que se queda no tenia papel en ese expediente (o lo tenia
            # con menos respaldo), hereda el de la otra en vez de perderlo
            mejor = (part["rol"] or "").strip() and (
                not (choca["rol"] or "").strip()
                or (part["confianza"] or 0) > (choca["confianza"] or 0))
            if mejor:
                entrada["rol_previo"] = {"id": choca["id"], "rol": choca["rol"],
                                         "origen": choca["origen"],
                                         "confianza": choca["confianza"]}
                db.execute(
                    "UPDATE participaciones SET rol=?, origen=?, confianza=? WHERE id=?",
                    (part["rol"], part["origen"], part["confianza"], choca["id"]))
            movido["participaciones"].append(entrada)
        else:
            db.execute("UPDATE participaciones SET persona_id=? WHERE id=?",
                       (principal_id, part["id"]))
            movido["participaciones"].append({"id": part["id"], "borrado": False})

    # los huecos de la ficha principal se rellenan con lo que traiga la otra
    cambios = {}
    for campo in ("organizacion", "rol", "lugar", "notas"):
        if not (principal.get(campo) or "").strip() and (absorbida.get(campo) or "").strip():
            cambios[campo] = absorbida[campo]
            movido["campos"][campo] = ""
    if len(absorbida["nombre"]) > len(principal["nombre"]) and not principal["nombre"][0].isdigit() \
            and principal["nombre"].startswith("("):
        cambios["nombre"] = absorbida["nombre"]
        movido["campos"]["nombre"] = principal["nombre"]
    if cambios:
        modelo.actualizar_persona(principal_id, **cambios)

    db.execute("UPDATE personas SET activo=0, fusionada_en=?, actualizado=? WHERE id=?",
               (principal_id, db.now_iso(), absorbida_id))
    fusion_id = db.execute(
        """INSERT INTO fusiones (principal_id, absorbida_id, motivos_json, confianza,
                                 movido_json, ts)
           VALUES (?,?,?,?,?,?)""",
        (principal_id, absorbida_id, json.dumps(motivos or [], ensure_ascii=False),
         confianza, json.dumps(movido, ensure_ascii=False), db.now_iso()))
    return {"ok": True, "fusion_id": fusion_id, "principal": principal_id,
            "absorbida": absorbida_id}


def deshacer(fusion_id: int) -> Dict[str, Any]:
    """Devuelve cada cosa a su ficha original."""
    fusion = db.query_one("SELECT * FROM fusiones WHERE id=? AND deshecha=0", (fusion_id,))
    if not fusion:
        raise ValueError("Esa fusion no existe o ya se deshizo")
    movido = json.loads(fusion["movido_json"] or "{}")
    absorbida_id, principal_id = fusion["absorbida_id"], fusion["principal_id"]

    for ident in movido.get("identificadores", []):
        if ident.get("borrado"):
            fila = ident["fila"]
            db.execute(
                """INSERT INTO identificadores (persona_id, tipo, valor, valor_norm,
                                                etiqueta, origen, creado)
                   VALUES (?,?,?,?,?,?,?)""",
                (absorbida_id, fila["tipo"], fila["valor"], fila["valor_norm"],
                 fila.get("etiqueta"), fila.get("origen"), db.now_iso()))
        else:
            db.execute("UPDATE identificadores SET persona_id=? WHERE id=?",
                       (absorbida_id, ident["id"]))

    for interaccion_id in movido.get("interacciones", []):
        db.execute("UPDATE interacciones SET persona_id=? WHERE id=?",
                   (absorbida_id, interaccion_id))

    for part in movido.get("participaciones", []):
        if part.get("borrado"):
            previo = part.get("rol_previo")
            if previo:
                db.execute(
                    "UPDATE participaciones SET rol=?, origen=?, confianza=? WHERE id=?",
                    (previo["rol"], previo["origen"], previo["confianza"], previo["id"]))
            fila = part["fila"]
            db.execute(
                """INSERT INTO participaciones (persona_id, caso_id, rol, origen,
                                                confianza, creado)
                   VALUES (?,?,?,?,?,?)""",
                (absorbida_id, fila["caso_id"], fila["rol"], fila["origen"],
                 fila["confianza"], db.now_iso()))
        else:
            db.execute("UPDATE participaciones SET persona_id=? WHERE id=?",
                       (absorbida_id, part["id"]))

    if movido.get("campos"):
        modelo.actualizar_persona(principal_id, **movido["campos"])

    db.execute("UPDATE personas SET activo=1, fusionada_en=NULL, actualizado=? WHERE id=?",
               (db.now_iso(), absorbida_id))
    db.execute("UPDATE fusiones SET deshecha=1 WHERE id=?", (fusion_id,))
    return {"ok": True, "restaurada": absorbida_id}


def descartar(a_id: int, b_id: int) -> Dict[str, Any]:
    """Marca un par como 'son personas distintas' para no volver a proponerlo."""
    a, b = min(a_id, b_id), max(a_id, b_id)
    db.execute("INSERT OR IGNORE INTO descartes (a_id, b_id, ts) VALUES (?,?,?)",
               (a, b, db.now_iso()))
    return {"ok": True}

"""Busqueda por cualquier hilo del que se tire.

En un despacho casi nunca se empieza por el nombre: se empieza por el telefono
que esta entrando, por el expediente que se tiene abierto o por el papel que
juega alguien. Una sola consulta cubre los cuatro caminos y cada resultado
explica **por que** aparece.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from . import db, modelo
from .config import CONFIG


def _es_telefono(consulta: str) -> bool:
    return len(re.sub(r"\D", "", consulta)) >= 6


def buscar(consulta: str, limite: int = 0) -> Dict[str, Any]:
    consulta = (consulta or "").strip()
    limite = limite or int(CONFIG.get("resultados_busqueda") or 25)
    if len(consulta) < 2:
        return {"consulta": consulta, "resultados": [], "historial": []}

    patron = f"%{modelo.sin_acentos(consulta).lower()}%"
    digitos = re.sub(r"\D", "", consulta)
    resultados: Dict[int, Dict[str, Any]] = {}

    def anotar(persona_id: int, por: str, peso: float) -> None:
        actual = resultados.get(persona_id)
        if actual is None or peso > actual["peso"]:
            resultados[persona_id] = {"peso": peso, "por": por}
        elif actual and por not in actual["por"]:
            actual["por"] += f" · {por}"

    # --- por identificador (telefono, correo, extension) ------------------
    if digitos and _es_telefono(consulta):
        for fila in db.query(
                """SELECT persona_id, tipo, valor FROM identificadores
                   WHERE valor_norm LIKE ? LIMIT 200""", (f"%{digitos[-10:]}%",)):
            etiqueta = {"telefono": "ese numero es suyo",
                        "extension": "es su extension"}.get(fila["tipo"], "coincide un dato")
            anotar(fila["persona_id"], etiqueta, 5.0)
    for fila in db.query(
            """SELECT persona_id, tipo, valor FROM identificadores
               WHERE lower(valor) LIKE ? LIMIT 200""", (patron,)):
        anotar(fila["persona_id"], "coincide su correo" if fila["tipo"] == "correo"
               else "coincide un dato de contacto", 4.0)

    # --- por nombre, organizacion, rol o lugar ---------------------------
    for fila in db.query(
            """SELECT id, nombre, organizacion, rol, lugar FROM personas
               WHERE activo=1 AND (lower(nombre) LIKE ? OR nombre_norm LIKE ?
                     OR lower(organizacion) LIKE ? OR lower(rol) LIKE ?
                     OR lower(lugar) LIKE ?) LIMIT 300""",
            (patron, patron, patron, patron, patron)):
        texto = modelo.sin_acentos(consulta).lower()
        if texto in (fila["nombre"] or "").lower() or texto in (fila["nombre_norm"] if "nombre_norm" in fila else ""):
            por, peso = "coincide el nombre", 6.0
        elif texto in (fila["rol"] or "").lower():
            por, peso = f"es su papel: {fila['rol']}", 4.5
        elif texto in (fila["organizacion"] or "").lower():
            por, peso = f"trabaja en {fila['organizacion']}", 4.0
        else:
            por, peso = "coincide su ubicacion", 3.0
        anotar(fila["id"], por, peso)

    # --- por expediente ---------------------------------------------------
    casos = db.query(
        """SELECT id, expediente, nombre FROM casos
           WHERE lower(expediente) LIKE ? OR lower(nombre) LIKE ? LIMIT 20""",
        (patron, patron))
    for caso in casos:
        for fila in db.query(
                "SELECT persona_id, rol FROM participaciones WHERE caso_id=?", (caso["id"],)):
            anotar(fila["persona_id"],
                   f"participa en {caso['expediente']} como {fila['rol'] or 'parte'}", 5.5)

    # --- armar la respuesta ----------------------------------------------
    salida: List[Dict[str, Any]] = []
    for persona_id, dato in resultados.items():
        ficha = modelo.resumen_persona(persona_id)
        if not ficha or not ficha.get("activo", 1):
            continue
        ficha["por"] = dato["por"]
        ficha["peso"] = dato["peso"] + (1.0 if ficha.get("ultimo_ts") else 0)
        salida.append(ficha)
    salida.sort(key=lambda f: (f["peso"], f.get("ultimo_ts") or ""), reverse=True)

    # --- historial de numeros sin ficha -----------------------------------
    historial: List[Dict[str, Any]] = []
    if digitos and _es_telefono(consulta):
        historial = db.query(
            """SELECT ts, titulo, detalle, referencia FROM interacciones
               WHERE persona_id IS NULL AND referencia LIKE ?
               ORDER BY ts DESC LIMIT 10""", (f"%{digitos[-10:]}|%",))

    return {"consulta": consulta, "resultados": salida[:limite],
            "historial": historial, "casos": casos}

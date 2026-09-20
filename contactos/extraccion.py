"""Alta en un paso: de un texto pegado a una ficha propuesta.

El formulario de alta es donde las plataformas actuales pierden al usuario:
treinta campos que nadie rellena. Casi siempre el dato ya existe escrito en
alguna parte —la firma de un correo, el pie de un escrito, una tarjeta— asi que
lo razonable es pegarlo y que el sistema proponga.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

RE_CORREO = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
RE_TELEFONO = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
RE_ETIQUETA_TEL = re.compile(r"\b(p|t|tel|telefono|phone|movil|mobile|cel|celular|f|fax|"
                             r"direct|office|oficina)\s*[:.]?\s*$", re.IGNORECASE)
RE_ORG = re.compile(r"\b(LLP|LLC|PLLC|P\.?A\.?|INC|CORP|COMPANY|CENTER|CENTRE|DEPARTMENT|"
                    r"ASSOCIATES|LAW\s+(?:FIRM|OFFICES?|GROUP)|ABOGADOS|DESPACHO|"
                    r"S\.?A\.?\s*DE\s*C\.?V\.?|HOSPITAL|CLINIC|INSURANCE)\b", re.IGNORECASE)
RE_PERSONA = re.compile(r"^[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.'-]+"
                        r"(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ.'-]*){1,3}"
                        r",?\s*(Esq\.?|Esquire|MD|M\.D\.|PhD|Lic\.?|Ing\.?)?$")
RE_DIRECCION = re.compile(r"\d+\s+[A-Za-zÁÉÍÓÚÑáéíóúñ].*"
                          r"(Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Boulevard|Blvd|Suite|"
                          r"Calle|Avenida|Av\.|Carrera)", re.IGNORECASE)
RE_CIUDAD = re.compile(r"^[A-ZÁÉÍÓÚÑ][\w\sÁÉÍÓÚÑáéíóúñ.'-]+,\s*[A-Za-z\s]{2,}\s*\d{4,6}")
RE_COLEGIADO = re.compile(r"(?:federal\s+)?bar\s*(?:no\.?|number|#)?\s*:?\s*(\d{3,8})", re.IGNORECASE)
RE_EXTENSION = re.compile(r"\b(?:ext|extension|x)\s*\.?\s*(\d{1,5})\b", re.IGNORECASE)
RE_ROL = re.compile(r"\b(abogad[oa]|attorney|paralegal|adjuster|ajustador[a]?|"
                    r"physician|doctor|m[eé]dic[oa]|agente|agent|gerente|manager|"
                    r"director[a]?|perito|investigator|officer|oficial)\b", re.IGNORECASE)

ROLES_LEGIBLES = {
    "attorney": "Abogado", "abogado": "Abogado", "abogada": "Abogada",
    "paralegal": "Paralegal", "adjuster": "Ajustador de seguros",
    "ajustador": "Ajustador de seguros", "ajustadora": "Ajustadora de seguros",
    "physician": "Medico", "doctor": "Medico", "medico": "Medico", "medica": "Medica",
    "perito": "Perito", "investigator": "Investigador", "officer": "Oficial",
}


def leer(texto: str) -> Dict[str, Any]:
    """Devuelve los datos reconocidos y de que linea salio cada uno."""
    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    if not lineas:
        return {"campos": {}, "identificadores": [], "evidencia": {}}

    campos: Dict[str, str] = {}
    evidencia: Dict[str, str] = {}
    identificadores: List[Dict[str, str]] = []

    def anotar(clave: str, valor: str, linea: str) -> None:
        if valor and clave not in campos:
            campos[clave] = valor.strip()
            evidencia[clave] = linea.strip()[:90]

    # --- organizacion -----------------------------------------------------
    for linea in lineas:
        if RE_ORG.search(linea) and not RE_CORREO.search(linea):
            anotar("organizacion", re.sub(r",\s*$", "", linea), linea)
            break

    # --- persona ----------------------------------------------------------
    for linea in lineas:
        if linea == campos.get("organizacion"):
            continue
        if RE_CORREO.search(linea) or RE_TELEFONO.search(linea) or RE_DIRECCION.search(linea):
            continue
        if RE_ORG.search(linea):
            continue
        if RE_PERSONA.match(linea):
            anotar("nombre", re.sub(r",?\s*(Esq\.?|Esquire)$", "", linea, flags=re.IGNORECASE), linea)
            if re.search(r"Esq\.?|Esquire", linea, re.IGNORECASE):
                anotar("rol", "Abogado", linea)
            break

    # --- rol --------------------------------------------------------------
    if "rol" not in campos:
        for linea in lineas:
            m = RE_ROL.search(linea)
            if m:
                clave = m.group(1).lower()
                anotar("rol", ROLES_LEGIBLES.get(clave, m.group(1).capitalize()), linea)
                break

    # --- telefonos --------------------------------------------------------
    for linea in lineas:
        for m in RE_TELEFONO.finditer(linea):
            antes = linea[:m.start()].strip()
            etiqueta = ""
            marca = RE_ETIQUETA_TEL.search(antes)
            if marca:
                bruto = marca.group(1).lower()
                etiqueta = ("fax" if bruto.startswith("f") else
                            "movil" if bruto.startswith(("m", "c")) else "telefono")
            identificadores.append({"tipo": "telefono", "valor": m.group(0).strip(),
                                    "etiqueta": etiqueta or "telefono", "linea": linea})
    # --- correos ----------------------------------------------------------
    for linea in lineas:
        for m in RE_CORREO.finditer(linea):
            identificadores.append({"tipo": "correo", "valor": m.group(0),
                                    "etiqueta": "correo", "linea": linea})
    # --- extension interna -------------------------------------------------
    for linea in lineas:
        m = RE_EXTENSION.search(linea)
        if m:
            identificadores.append({"tipo": "extension", "valor": m.group(1),
                                    "etiqueta": "extension", "linea": linea})
            break

    # --- direccion y colegiado --------------------------------------------
    for linea in lineas:
        if RE_DIRECCION.search(linea):
            anotar("direccion", linea, linea)
        elif RE_CIUDAD.match(linea):
            anotar("lugar", linea, linea)
        m = RE_COLEGIADO.search(linea)
        if m:
            anotar("colegiado", m.group(1), linea)

    if "lugar" not in campos and "direccion" in campos:
        campos["lugar"] = campos["direccion"]

    # sin nombre de persona pero con organizacion: la ficha es la organizacion
    if "nombre" not in campos and "organizacion" in campos:
        campos["nombre"] = campos["organizacion"]
        evidencia["nombre"] = evidencia["organizacion"]

    return {"campos": campos, "identificadores": identificadores, "evidencia": evidencia}

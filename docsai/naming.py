"""Convencion de nombres y organizacion en carpetas.

Nombre por defecto:

    {fecha}_{CATEGORIA}_{expediente}_{descriptor}[_vNN].ext
    2024-09-18_DEMANDA_3-24-cv-05148-MGL_Fry-v-United-States-of-America.pdf

Por que asi:

* la fecha ISO al principio hace que el orden alfabetico sea orden cronologico;
* la categoria en mayusculas permite filtrar de un vistazo y agrupar por tipo;
* el expediente enlaza el archivo con su caso, que es la unidad de trabajo real
  del despacho;
* el descriptor (las partes, o el titulo si no hay partes) da contexto humano;
* el sufijo de version solo aparece cuando hace falta, para no ensuciar el
  nombre en el caso normal.

Todo es configurable: la plantilla, el separador, el largo maximo y el esquema
de carpetas. Si un dato falta, su hueco se rellena con un marcador explicito
(`sin-fecha`, `sin-expediente`) en vez de dejar el nombre incompleto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import CONFIG
from .entities import Entidades, slug

PLANTILLA_POR_DEFECTO = "{fecha}_{categoria}_{expediente}_{descriptor}"
ESQUEMAS = {
    "categoria_anio": "Categoria / Anio",
    "expediente": "Expediente / Categoria",
    "anio_mes": "Anio / Mes",
    "categoria": "Solo categoria",
    "plano": "Todo en una carpeta",
}


@dataclass
class Nombre:
    nombre: str
    base: str
    extension: str
    carpeta: str
    campos: Dict[str, str]
    faltantes: List[str]

    @property
    def completo(self) -> str:
        return f"{self.carpeta}/{self.nombre}" if self.carpeta else self.nombre


def _descriptor(entidades: Entidades, titulo: str, original: str) -> str:
    """Lo que hace reconocible al documento para una persona."""
    if len(entidades.partes) >= 2:
        return slug(f"{entidades.partes[0]} v {entidades.partes[1]}", 46)
    if entidades.partes:
        return slug(entidades.partes[0], 40)
    if entidades.emisor:
        return slug(entidades.emisor, 40)
    if titulo:
        return slug(titulo, 40)
    return slug(Path(original).stem, 36)


def construir(entidades: Entidades, categoria: str, titulo: str = "",
              nombre_original: str = "documento", hash_corto: str = "") -> Nombre:
    extension = Path(nombre_original).suffix.lower() or ".dat"
    fecha = entidades.fecha or "sin-fecha"
    anio, mes = (fecha[:4], fecha[5:7]) if entidades.fecha else ("sin-anio", "00")

    faltantes: List[str] = []
    if not entidades.fecha:
        faltantes.append("fecha")
    if not entidades.expediente:
        faltantes.append("expediente")
    if not entidades.partes:
        faltantes.append("partes")

    campos = {
        "fecha": fecha,
        "anio": anio,
        "mes": mes,
        "categoria": (categoria or "SIN-CLASIFICAR").upper(),
        "expediente": slug(entidades.expediente, 30) or "sin-expediente",
        "descriptor": _descriptor(entidades, titulo, nombre_original) or "documento",
        "emisor": slug(entidades.emisor, 28) or "sin-emisor",
        "monto": (f"{entidades.monto_principal:.0f}" if entidades.monto_principal else "0"),
        "original": slug(Path(nombre_original).stem, 30),
        "hash": hash_corto[:8],
    }

    plantilla = str(CONFIG.get("plantilla_nombre") or PLANTILLA_POR_DEFECTO)
    try:
        base = plantilla.format(**campos)
    except (KeyError, IndexError):
        base = PLANTILLA_POR_DEFECTO.format(**campos)

    separador = str(CONFIG.get("separador") or "_")
    base = base.replace("_", separador) if separador != "_" else base
    base = re.sub(rf"{re.escape(separador)}{{2,}}", separador, base).strip(separador + "-")
    base = base[:int(CONFIG.get("max_nombre") or 120)].strip(separador + "-")

    return Nombre(nombre=base + extension, base=base, extension=extension,
                  carpeta=carpeta_para(campos), campos=campos, faltantes=faltantes)


def carpeta_para(campos: Dict[str, str]) -> str:
    esquema = str(CONFIG.get("esquema_carpetas") or "categoria_anio")
    categoria = campos.get("categoria", "SIN-CLASIFICAR")
    expediente = campos.get("expediente", "sin-expediente")
    anio, mes = campos.get("anio", "sin-anio"), campos.get("mes", "00")
    if esquema == "expediente":
        return f"{expediente}/{categoria}"
    if esquema == "anio_mes":
        return f"{anio}/{mes}"
    if esquema == "categoria":
        return categoria
    if esquema == "plano":
        return ""
    return f"{categoria}/{anio}"


def version_disponible(destino: Path, nombre: Nombre) -> Path:
    """Evita pisar archivos: agrega _v02, _v03… solo cuando ya existe el nombre."""
    ruta = destino / nombre.nombre
    if not ruta.exists():
        return ruta
    separador = str(CONFIG.get("separador") or "_")
    for version in range(2, 100):
        candidato = destino / f"{nombre.base}{separador}v{version:02d}{nombre.extension}"
        if not candidato.exists():
            return candidato
    return destino / f"{nombre.base}{separador}{nombre.campos.get('hash', 'x')}{nombre.extension}"


def describir_convencion() -> Dict[str, Any]:
    return {
        "plantilla": CONFIG.get("plantilla_nombre") or PLANTILLA_POR_DEFECTO,
        "separador": CONFIG.get("separador") or "_",
        "max_nombre": CONFIG.get("max_nombre") or 120,
        "esquema_carpetas": CONFIG.get("esquema_carpetas") or "categoria_anio",
        "umbral_revision": CONFIG.get("umbral_revision"),
        "conservar_original": CONFIG.get("conservar_original"),
        "max_trabajos": CONFIG.get("max_trabajos"),
        "guardar_texto": CONFIG.get("guardar_texto"),
        "esquemas": ESQUEMAS,
        "campos": ["fecha", "anio", "mes", "categoria", "expediente", "descriptor",
                   "emisor", "monto", "original", "hash"],
        "ejemplo": "2024-09-18_DEMANDA_3-24-cv-05148-MGL_Fry-v-United-States.pdf",
    }

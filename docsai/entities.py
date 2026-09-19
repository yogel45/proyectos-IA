"""Extraccion de los datos que identifican a un documento.

No basta con saber "esto es una demanda": para nombrarla y archivarla hace
falta el expediente, la fecha, las partes y el emisor. Aqui se hace con
expresiones regulares y reglas de posicion (lo que aparece arriba pesa mas),
porque son verificables y explicables: cada dato guarda de donde salio.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MESES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# --- expedientes y numeros identificadores --------------------------------
RE_CASO_FEDERAL = re.compile(r"\b\d:\d{2}-[a-z]{2}-\d{3,6}-[A-Za-z]{2,5}\b")
RE_CASO_ETIQUETA = re.compile(
    r"(?:case|civil action|docket|expediente|causa|c[aá]usa)\s*(?:no\.?|number|n[uú]m(?:ero)?\.?|#)?\s*"
    r"[:\s]\s*([A-Z0-9][A-Z0-9\-/:\.]{4,28})", re.IGNORECASE)
RE_RECLAMO = re.compile(
    r"(?:claim|reclamo|reclamaci[oó]n|file)\s*(?:no\.?|number|n[uú]m(?:ero)?\.?|#)\s*[:\s]\s*"
    r"([A-Z0-9][A-Z0-9\-/]{3,24})", re.IGNORECASE)
RE_POLIZA = re.compile(
    r"(?:policy|p[oó]liza)\s*(?:no\.?|number|n[uú]m(?:ero)?\.?|#)?\s*[:\s]\s*"
    r"([A-Z0-9][A-Z0-9\-]{4,24})", re.IGNORECASE)
RE_FACTURA = re.compile(
    r"(?:invoice|factura|bill)\s*(?:no\.?|number|n[uú]m(?:ero)?\.?|#)\s*[:\s]\s*"
    r"([A-Z0-9][A-Z0-9\-]{2,20})", re.IGNORECASE)

# --- fechas ---------------------------------------------------------------
RE_FECHA_FILED = re.compile(r"date\s+filed\s+(\d{1,2})/(\d{1,2})/(\d{2,4})", re.IGNORECASE)
RE_FECHA_NUM = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b")
RE_FECHA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_FECHA_EN = re.compile(
    r"\b(" + "|".join(MESES_EN) + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)
RE_FECHA_ES = re.compile(
    r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES_ES) + r")\s+de\s+(\d{4})\b", re.IGNORECASE)

# --- otros datos ----------------------------------------------------------
RE_MONTO = re.compile(r"\$\s?([\d]{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)")
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
RE_TELEFONO = re.compile(r"\(?\b\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b")
RE_TRIBUNAL = re.compile(r"^.*\b(court|tribunal|juzgado|corte)\b.*$", re.IGNORECASE | re.MULTILINE)
RE_DESPACHO = re.compile(
    r"^.*(?:\bLLP\b|\bLLC\b|\bPLLC\b|\bP\.A\.|&\s*ASSOCIATES|\bLAW\s+(?:FIRM|OFFICES?|GROUP)\b|"
    r"\bATTORNEYS?\s+AT\s+LAW\b|\bABOGADOS\b|\bDESPACHO\b).*$", re.IGNORECASE | re.MULTILINE)
RE_PARTE_ACTORA = re.compile(
    r"^\s*(.{3,80}?)\s*,?\s*\n?\s*(?:Plaintiffs?|Demandantes?|Petitioners?)\s*[.,;:]?\s*$",
    re.IGNORECASE | re.MULTILINE)
RE_PARTE_DEMANDADA = re.compile(
    r"^\s*(.{3,80}?)\s*,?\s*\n?\s*(?:Defendants?|Demandad[oa]s?|Respondents?)\s*[.,;:]?\s*$",
    re.IGNORECASE | re.MULTILINE)
RE_VERSUS = re.compile(r"^\s*(.{3,70}?)\s+(?:v\.?|vs\.?|contra)\s+(.{3,70}?)\s*$",
                       re.IGNORECASE | re.MULTILINE)

RUIDO = {"the", "and", "of", "for", "inc", "llc", "llp", "pa", "de", "la", "el", "los"}


@dataclass
class Entidades:
    expediente: str = ""
    reclamo: str = ""
    poliza: str = ""
    factura: str = ""
    fecha: str = ""                       # ISO, la mas representativa
    fecha_origen: str = ""                # de donde salio esa fecha
    fechas: List[str] = field(default_factory=list)
    partes: List[str] = field(default_factory=list)
    tribunal: str = ""
    emisor: str = ""
    montos: List[float] = field(default_factory=list)
    monto_principal: float = 0.0
    correos: List[str] = field(default_factory=list)
    telefonos: List[str] = field(default_factory=list)
    titulo: str = ""
    evidencia: Dict[str, str] = field(default_factory=dict)

    def como_dict(self) -> Dict[str, Any]:
        return {
            "expediente": self.expediente, "reclamo": self.reclamo,
            "poliza": self.poliza, "factura": self.factura,
            "fecha": self.fecha, "fecha_origen": self.fecha_origen,
            "fechas": self.fechas[:12], "partes": self.partes,
            "tribunal": self.tribunal, "emisor": self.emisor,
            "montos": self.montos[:10], "monto_principal": self.monto_principal,
            "correos": self.correos[:5], "telefonos": self.telefonos[:5],
            "titulo": self.titulo, "evidencia": self.evidencia,
        }


def _iso(anio: int, mes: int, dia: int) -> Optional[str]:
    try:
        if anio < 100:
            anio += 2000 if anio < 70 else 1900
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


def _limpiar_linea(texto: str) -> str:
    texto = re.sub(r"\s+", " ", texto).strip(" .,:;-")
    return texto[:90]


def fechas_del_texto(texto: str) -> List[Tuple[str, str, int]]:
    """Devuelve (fecha ISO, origen, posicion) de todo lo que parezca una fecha."""
    salida: List[Tuple[str, str, int]] = []
    for m in RE_FECHA_FILED.finditer(texto):
        iso = _iso(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if iso:
            salida.append((iso, "date filed", m.start()))
    for m in RE_FECHA_ISO.finditer(texto):
        iso = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            salida.append((iso, "formato ISO", m.start()))
    for m in RE_FECHA_NUM.finditer(texto):
        # formato de EE. UU. (mes/dia/anio), el de los documentos de la muestra
        iso = _iso(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if iso:
            salida.append((iso, "fecha numerica", m.start()))
    for m in RE_FECHA_EN.finditer(texto):
        iso = _iso(int(m.group(3)), MESES_EN[m.group(1).lower().rstrip(".")], int(m.group(2)))
        if iso:
            salida.append((iso, "fecha en ingles", m.start()))
    for m in RE_FECHA_ES.finditer(texto):
        iso = _iso(int(m.group(3)), MESES_ES[m.group(2).lower()], int(m.group(1)))
        if iso:
            salida.append((iso, "fecha en espanol", m.start()))
    return salida


# Un documento trae varias fechas (nacimiento, incidente, presentacion, firma).
# La que interesa para nombrarlo es la del documento en si, asi que se mira la
# etiqueta que la acompana en lugar de quedarse con la primera que aparece.
ETIQUETAS_FECHA: List[Tuple[re.Pattern, int, str]] = [
    (re.compile(r"date\s+filed|fecha\s+de\s+presentaci", re.I), 100, "fecha de presentacion"),
    (re.compile(r"date\s+submitted|submitted\s*(on)?|fecha\s+de\s+env[ií]o", re.I), 90, "fecha de envio"),
    (re.compile(r"date\s+of\s+service|service\s+date|fecha\s+de\s+servicio", re.I), 85, "fecha de atencion"),
    (re.compile(r"executed[^.\n]{0,40}on|dated\s+this|given\s+this|sworn[^.\n]{0,25}this|"
                r"firmado\s+el|suscrito\s+el", re.I), 82, "fecha de firma"),
    (re.compile(r"invoice\s+date|statement\s+date|fecha\s+de\s+factura|fecha\s+de\s+emisi", re.I), 80, "fecha de emision"),
    (re.compile(r"(?:^|\n)\s*(?:date|fecha)\s*:", re.I), 70, "campo fecha"),
]
NEGATIVAS_FECHA = re.compile(
    r"date\s+of\s+birth|fecha\s+de\s+nacimiento|\bdob\b|"
    r"date\s+of\s+(?:incident|loss|accident)|fecha\s+del?\s+(?:incidente|accidente|siniestro)|"
    r"collision\s+(?:of|on)|occurred\s+on|ocurrido\s+el", re.I)


def _prioridad_fecha(texto: str, posicion: int) -> Tuple[int, str]:
    """Puntua una fecha segun la etiqueta que la precede.

    Manda la etiqueta *mas cercana*: en "Date of birth: 03/22/1965  Date of
    service: 01/15/2023" cada fecha debe quedarse con la suya, no con la que
    aparezca antes en la ventana.
    """
    inicio = max(0, posicion - 80)
    contexto = texto[inicio:posicion]
    candidatos: List[Tuple[int, int, str]] = []
    for m in NEGATIVAS_FECHA.finditer(contexto):
        candidatos.append((m.end(), -50, "fecha de un hecho, no del documento"))
    for patron, peso, descripcion in ETIQUETAS_FECHA:
        for m in patron.finditer(contexto):
            candidatos.append((m.end(), peso, descripcion))
    if not candidatos:
        return 0, ""
    _, peso, descripcion = max(candidatos, key=lambda c: c[0])
    return peso, descripcion


def elegir_fecha(texto: str, metadatos: Dict[str, Any],
                 respaldo: Optional[datetime] = None) -> Tuple[str, str, List[str]]:
    """La fecha que identifica al documento, con el motivo de haberla elegido."""
    candidatas = sorted({(f, o, p) for f, o, p in fechas_del_texto(texto)},
                        key=lambda x: x[2])
    solo_fechas = sorted({f for f, _, _ in candidatas})

    puntuadas = []
    for iso, origen, posicion in candidatas:
        prioridad, descripcion = _prioridad_fecha(texto, posicion)
        if posicion < 1200:                       # el encabezado sigue contando
            prioridad += 12
        puntuadas.append((prioridad, -posicion, iso, descripcion or origen))
    puntuadas.sort(reverse=True)

    if puntuadas and puntuadas[0][0] > -50:
        _, _, iso, descripcion = puntuadas[0]
        return iso, descripcion, solo_fechas
    if candidatas:
        return candidatas[0][0], candidatas[0][1], solo_fechas

    for clave in ("creationDate", "modDate", "created"):
        bruto = str(metadatos.get(clave, ""))
        m = re.search(r"D?:?(\d{4})(\d{2})(\d{2})", bruto)
        if m:
            iso = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if iso:
                return iso, f"metadatos del archivo ({clave})", solo_fechas
    if respaldo:
        return respaldo.date().isoformat(), "fecha del archivo en disco", solo_fechas
    return "", "sin fecha detectada", solo_fechas


def _primer_grupo(patron: re.Pattern, texto: str) -> str:
    m = patron.search(texto)
    return _limpiar_linea(m.group(1)) if m else ""


def extraer_entidades(texto: str, metadatos: Optional[Dict[str, Any]] = None,
                      nombre_archivo: str = "",
                      respaldo_fecha: Optional[datetime] = None) -> Entidades:
    metadatos = metadatos or {}
    ent = Entidades()
    cabeza = texto[:2500]

    # --- expediente ------------------------------------------------------
    m = RE_CASO_FEDERAL.search(texto)
    if m:
        ent.expediente = m.group(0)
        ent.evidencia["expediente"] = "numero de caso federal en el texto"
    else:
        etiquetado = _primer_grupo(RE_CASO_ETIQUETA, texto)
        if etiquetado and not etiquetado.lower().startswith("no"):
            ent.expediente = etiquetado
            ent.evidencia["expediente"] = "etiqueta 'case/expediente no.'"
    if not ent.expediente:
        m = RE_CASO_FEDERAL.search(nombre_archivo)
        if m:
            ent.expediente = m.group(0)
            ent.evidencia["expediente"] = "numero de caso en el nombre del archivo"

    ent.reclamo = _primer_grupo(RE_RECLAMO, texto)
    ent.poliza = _primer_grupo(RE_POLIZA, texto)
    ent.factura = _primer_grupo(RE_FACTURA, texto)

    # --- fecha -----------------------------------------------------------
    ent.fecha, ent.fecha_origen, ent.fechas = elegir_fecha(texto, metadatos, respaldo_fecha)

    # --- partes ----------------------------------------------------------
    actora = _primer_grupo(RE_PARTE_ACTORA, cabeza)
    demandada = _primer_grupo(RE_PARTE_DEMANDADA, cabeza)
    if actora:
        ent.partes.append(actora)
    if demandada and demandada.lower() != actora.lower():
        ent.partes.append(demandada)
    if not ent.partes:
        m = RE_VERSUS.search(cabeza)
        if m:
            ent.partes = [_limpiar_linea(m.group(1)), _limpiar_linea(m.group(2))]
            ent.evidencia["partes"] = "linea con 'v.' / 'contra'"
    elif actora or demandada:
        ent.evidencia["partes"] = "etiquetas de demandante y demandado"

    # --- tribunal y emisor ----------------------------------------------
    m = RE_TRIBUNAL.search(cabeza)
    if m:
        ent.tribunal = _limpiar_linea(m.group(0))
    m = RE_DESPACHO.search(texto)
    if m:
        ent.emisor = _limpiar_linea(m.group(0))
        ent.evidencia["emisor"] = "linea con forma juridica del despacho"
    if not ent.emisor and metadatos.get("author"):
        ent.emisor = _limpiar_linea(str(metadatos["author"]))
        ent.evidencia["emisor"] = "autor en los metadatos"

    # --- importes y contactos -------------------------------------------
    for m in RE_MONTO.finditer(texto):
        try:
            ent.montos.append(float(m.group(1).replace(",", "")))
        except ValueError:
            continue
    ent.montos = sorted(set(ent.montos), reverse=True)
    ent.monto_principal = ent.montos[0] if ent.montos else 0.0
    ent.correos = list(dict.fromkeys(RE_EMAIL.findall(texto)))
    ent.telefonos = list(dict.fromkeys(RE_TELEFONO.findall(texto)))

    # --- titulo ----------------------------------------------------------
    ent.titulo = _titulo_probable(texto)
    return ent


VENUE = re.compile(r"\b(court|district|division|tribunal|juzgado|circuit|county)\b", re.IGNORECASE)


def _titulo_probable(texto: str) -> str:
    """La linea que mejor describe el documento.

    Premia lo que se comporta como titulo (mayusculas, arriba, corto) y castiga
    las lineas de sede judicial, que dicen donde se presento y no que es.
    """
    mejor, puntos_mejor = "", 0.0
    for i, linea in enumerate(texto.splitlines()[:45]):
        limpia = linea.strip()
        if not (4 <= len(limpia) <= 90):
            continue
        if re.search(r"page \d+ of \d+|entry number|date filed", limpia, re.IGNORECASE):
            continue
        letras = [c for c in limpia if c.isalpha()]
        if not letras:
            continue
        mayusculas = sum(1 for c in letras if c.isupper()) / len(letras)
        palabras = len(limpia.split())
        puntos = mayusculas * 2.0
        puntos += 1.0 if i < 18 else 0.0
        puntos += 0.8 if palabras <= 5 else 0.0
        puntos -= 1.6 if VENUE.search(limpia) else 0.0
        if puntos > puntos_mejor:
            mejor, puntos_mejor = _limpiar_linea(limpia), puntos
    return mejor


def slug(texto: str, maximo: int = 40, separador: str = "-") -> str:
    """Convierte cualquier texto en algo seguro para un nombre de archivo."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s-]", " ", texto)
    palabras = [p for p in texto.split() if p.lower() not in RUIDO]
    salida = separador.join(palabras) or separador.join(texto.split())
    salida = re.sub(rf"{re.escape(separador)}{{2,}}", separador, salida).strip(separador + "_")
    return salida[:maximo].strip(separador + "_")

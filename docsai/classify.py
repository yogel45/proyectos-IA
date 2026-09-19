"""Clasificacion de documentos: reglas explicables + aprendizaje por correccion.

Dos clasificadores que se complementan:

1. **Reglas ponderadas.** Cada categoria tiene frases y palabras con un peso.
   Lo que aparece en el encabezado pesa mas, porque ahi va el titulo del
   documento. Es la base: funciona desde el primer dia, sin datos previos, y
   siempre puede explicar por que decidio lo que decidio.

2. **Naive Bayes entrenado con las correcciones del usuario.** Cada vez que
   alguien corrige una categoria en la interfaz, ese documento se guarda como
   ejemplo. Cuando hay suficientes, el modelo entra a votar junto con las
   reglas, y el sistema mejora con el uso sin reentrenar nada a mano.

La decision final lleva siempre una confianza; por debajo del umbral el
documento se marca para revision humana en lugar de archivarse a ciegas.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import db

PESO_FUERTE, PESO_MEDIO, PESO_LEVE = 3.0, 1.5, 0.7
ENCABEZADO = 1500          # caracteres iniciales que cuentan como "titulo"
FACTOR_ENCABEZADO = 1.7
UMBRAL_REVISION = 0.55     # confianza minima por defecto (la ajusta la configuracion)
MIN_EJEMPLOS_NB = 6        # ejemplos necesarios para que el modelo entrenado vote


# --------------------------------------------------------------------------
# Catalogo de categorias
# --------------------------------------------------------------------------
# (codigo, nombre visible, descripcion, {termino: peso})
CATEGORIAS: List[Tuple[str, str, str, Dict[str, float]]] = [
    ("DEMANDA", "Demanda / Complaint",
     "Escrito que inicia el litigio y expone los hechos y pretensiones.",
     {"complaint": PESO_FUERTE, "demanda": PESO_FUERTE,
      "jury trial demanded": PESO_FUERTE, "plaintiff respectfully": PESO_FUERTE,
      "wherefore, plaintiff prays": PESO_FUERTE, "civil action no": PESO_MEDIO,
      "causes of action": PESO_MEDIO, "negligence per se": PESO_MEDIO,
      "plaintiff alleges": PESO_MEDIO, "prays for the following relief": PESO_MEDIO,
      "demandante": PESO_MEDIO, "peticion inicial": PESO_MEDIO}),

    ("CITACION", "Citacion / Summons",
     "Emplazamiento que notifica formalmente a la parte demandada.",
     {"summons in a civil action": PESO_FUERTE, "summons": PESO_FUERTE,
      "you are hereby summoned": PESO_FUERTE, "citacion": PESO_FUERTE,
      "emplazamiento": PESO_FUERTE, "within 21 days after service": PESO_MEDIO,
      "proof of service": PESO_MEDIO, "notificacion personal": PESO_LEVE}),

    ("MOCION", "Mocion / Motion",
     "Solicitud al tribunal para que resuelva un punto concreto.",
     {"motion to": PESO_FUERTE, "motion for": PESO_FUERTE,
      "memorandum in support": PESO_FUERTE, "mocion": PESO_FUERTE,
      "movant": PESO_MEDIO, "respectfully moves": PESO_MEDIO,
      "brief in opposition": PESO_MEDIO, "solicita al tribunal": PESO_MEDIO}),

    ("ORDEN", "Orden / Resolucion judicial",
     "Decision del tribunal: ordenes, sentencias y resoluciones.",
     {"it is so ordered": PESO_FUERTE, "ordered, adjudged": PESO_FUERTE,
      "judgment": PESO_FUERTE, "order granting": PESO_FUERTE,
      "order denying": PESO_FUERTE, "sentencia": PESO_FUERTE,
      "resolucion": PESO_MEDIO, "the court finds": PESO_MEDIO,
      "se resuelve": PESO_MEDIO, "united states magistrate judge": PESO_LEVE}),

    ("NOTIFICACION", "Notificacion / Aviso",
     "Avisos procesales y constancias de notificacion.",
     {"notice of": PESO_FUERTE, "certificate of service": PESO_FUERTE,
      "notice of appearance": PESO_FUERTE, "aviso": PESO_MEDIO,
      "notificacion": PESO_MEDIO, "hereby certify that": PESO_MEDIO,
      "was served": PESO_LEVE}),

    ("RECLAMACION", "Reclamacion administrativa",
     "Reclamo previo ante la agencia (por ejemplo, Standard Form 95).",
     {"standard form 95": PESO_FUERTE, "form 95": PESO_FUERTE,
      "claim for damage, injury, or death": PESO_FUERTE,
      "administrative claim": PESO_FUERTE, "reclamacion administrativa": PESO_FUERTE,
      "federal tort claims act": PESO_MEDIO, "amount of claim": PESO_MEDIO,
      "sf-95": PESO_MEDIO}),

    ("REPORTE-POLICIAL", "Reporte policial / accidente",
     "Parte de accidente o informe de autoridad sobre el incidente.",
     {"traffic collision report": PESO_FUERTE, "police report": PESO_FUERTE,
      "accident report": PESO_FUERTE, "incident report": PESO_FUERTE,
      "reporte policial": PESO_FUERTE, "parte de accidente": PESO_FUERTE,
      "investigating officer": PESO_MEDIO, "crash report": PESO_MEDIO,
      "citation number": PESO_LEVE}),

    ("EXPEDIENTE-MEDICO", "Expediente o factura medica",
     "Historia clinica, notas de evolucion o cobros de servicios de salud.",
     {"medical record": PESO_FUERTE, "patient name": PESO_FUERTE,
      "diagnosis": PESO_FUERTE, "expediente medico": PESO_FUERTE,
      "historia clinica": PESO_FUERTE, "chief complaint": PESO_MEDIO,
      "treatment plan": PESO_MEDIO, "icd-10": PESO_MEDIO, "cpt": PESO_LEVE,
      "physician": PESO_MEDIO, "radiology": PESO_MEDIO, "mri": PESO_LEVE}),

    ("SEGURO", "Poliza / aseguradora",
     "Polizas, cartas de aseguradoras y ajustes de siniestro.",
     {"policy number": PESO_FUERTE, "insurance company": PESO_FUERTE,
      "claims adjuster": PESO_FUERTE, "poliza": PESO_FUERTE,
      "aseguradora": PESO_FUERTE, "declaration page": PESO_MEDIO,
      "coverage limits": PESO_MEDIO, "siniestro": PESO_MEDIO,
      "adjuster": PESO_MEDIO}),

    ("FACTURA", "Factura / estado de cuenta",
     "Comprobantes de cobro y estados de cuenta.",
     {"invoice": PESO_FUERTE, "factura": PESO_FUERTE,
      "amount due": PESO_FUERTE, "statement of account": PESO_FUERTE,
      "bill to": PESO_MEDIO, "subtotal": PESO_MEDIO, "total due": PESO_MEDIO,
      "estado de cuenta": PESO_MEDIO, "payment terms": PESO_LEVE,
      "tax id": PESO_LEVE}),

    ("CONTRATO", "Contrato / acuerdo",
     "Acuerdos, convenios de transaccion y liberaciones de responsabilidad.",
     {"this agreement": PESO_FUERTE, "settlement agreement": PESO_FUERTE,
      "release of all claims": PESO_FUERTE, "contrato": PESO_FUERTE,
      "convenio": PESO_FUERTE, "in witness whereof": PESO_MEDIO,
      "the parties agree": PESO_MEDIO, "clausula": PESO_MEDIO,
      "whereas": PESO_LEVE}),

    ("DECLARACION", "Declaracion jurada / deposicion",
     "Affidavits, declaraciones juradas y transcripciones de deposicion.",
     {"affidavit": PESO_FUERTE, "sworn statement": PESO_FUERTE,
      "deposition of": PESO_FUERTE, "declaracion jurada": PESO_FUERTE,
      "being duly sworn": PESO_MEDIO, "under penalty of perjury": PESO_MEDIO,
      "transcript of proceedings": PESO_MEDIO, "testigo": PESO_LEVE}),

    ("IDENTIFICACION", "Identificacion",
     "Licencias, credenciales y documentos de identidad.",
     {"driver license": PESO_FUERTE, "driver's license": PESO_FUERTE,
      "identification card": PESO_FUERTE, "identificacion oficial": PESO_FUERTE,
      "date of birth": PESO_MEDIO, "licencia de conducir": PESO_FUERTE,
      "pasaporte": PESO_MEDIO}),

    ("CORRESPONDENCIA", "Correspondencia",
     "Cartas y correos entre las partes o con terceros.",
     {"dear ": PESO_MEDIO, "sincerely": PESO_MEDIO, "estimado": PESO_MEDIO,
      "atentamente": PESO_MEDIO, "re:": PESO_LEVE, "asunto:": PESO_LEVE,
      "enclosed please find": PESO_MEDIO, "adjunto encontrara": PESO_MEDIO,
      "from:": PESO_LEVE, "subject:": PESO_LEVE}),
]

SIN_CLASIFICAR = ("SIN-CLASIFICAR", "Sin clasificar",
                  "No se alcanzo la confianza minima: requiere revision humana.")


@dataclass
class Resultado:
    categoria: str = SIN_CLASIFICAR[0]
    nombre: str = SIN_CLASIFICAR[1]
    confianza: float = 0.0
    requiere_revision: bool = True
    motivo: str = ""
    evidencia: List[Dict[str, Any]] = field(default_factory=list)
    puntajes: Dict[str, float] = field(default_factory=dict)
    metodo: str = "reglas"
    nb_categoria: str = ""
    nb_probabilidad: float = 0.0

    def como_dict(self) -> Dict[str, Any]:
        return {
            "categoria": self.categoria, "nombre": self.nombre,
            "confianza": round(self.confianza, 3),
            "requiere_revision": self.requiere_revision, "motivo": self.motivo,
            "evidencia": self.evidencia[:12], "puntajes": {
                k: round(v, 2) for k, v in sorted(
                    self.puntajes.items(), key=lambda kv: -kv[1])[:6]},
            "metodo": self.metodo, "nb_categoria": self.nb_categoria,
            "nb_probabilidad": round(self.nb_probabilidad, 3),
        }


def catalogo() -> List[Dict[str, Any]]:
    base = [{"codigo": c, "nombre": n, "descripcion": d, "terminos": len(t)}
            for c, n, d, t in CATEGORIAS]
    base.append({"codigo": SIN_CLASIFICAR[0], "nombre": SIN_CLASIFICAR[1],
                 "descripcion": SIN_CLASIFICAR[2], "terminos": 0})
    return base


def nombre_categoria(codigo: str) -> str:
    for c, n, _, _ in CATEGORIAS:
        if c == codigo:
            return n
    return SIN_CLASIFICAR[1] if codigo == SIN_CLASIFICAR[0] else codigo


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto.lower())


# --------------------------------------------------------------------------
# 1. Reglas ponderadas
# --------------------------------------------------------------------------
def clasificar_por_reglas(texto: str, titulo: str = "",
                          nombre_archivo: str = "") -> Resultado:
    plano = _normalizar(texto)
    cabeza = _normalizar(f"{titulo} {nombre_archivo} {texto[:ENCABEZADO]}")

    puntajes: Dict[str, float] = {}
    evidencias: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for codigo, _, _, terminos in CATEGORIAS:
        total = 0.0
        for termino, peso in terminos.items():
            repeticiones = plano.count(termino)
            if not repeticiones:
                continue
            aporte = peso * (1 + 0.3 * math.log(repeticiones))
            donde = "cuerpo"
            if termino in cabeza:
                aporte *= FACTOR_ENCABEZADO
                donde = "encabezado"
            total += aporte
            evidencias[codigo].append(
                {"termino": termino, "veces": repeticiones, "donde": donde,
                 "aporte": round(aporte, 2)})
        if total:
            puntajes[codigo] = total

    if not puntajes:
        return Resultado(motivo="Ningun termino conocido aparece en el documento.",
                         puntajes={})

    orden = sorted(puntajes.items(), key=lambda kv: -kv[1])
    mejor, punta = orden[0]
    segunda = orden[1][1] if len(orden) > 1 else 0.0
    # La confianza mezcla cuanta evidencia hay y cuanto le saca a la segunda
    margen = (punta - segunda) / punta if punta else 0.0
    solidez = min(1.0, punta / 9.0)
    confianza = max(0.0, min(0.99, 0.45 * solidez + 0.55 * margen))

    evidencia = sorted(evidencias[mejor], key=lambda e: -e["aporte"])
    motivo = "Terminos decisivos: " + ", ".join(
        f"'{e['termino']}' ({e['donde']})" for e in evidencia[:3])
    if len(orden) > 1:
        motivo += f". Segunda opcion: {orden[1][0]} ({orden[1][1]:.1f} vs {punta:.1f})."
    return Resultado(categoria=mejor, nombre=nombre_categoria(mejor),
                     confianza=confianza, requiere_revision=confianza < UMBRAL_REVISION,
                     motivo=motivo, evidencia=evidencia, puntajes=puntajes)


# --------------------------------------------------------------------------
# 2. Naive Bayes entrenado con las correcciones
# --------------------------------------------------------------------------
PALABRA = re.compile(r"[a-z][a-z0-9]{2,}")
VACIAS = {"the", "and", "for", "that", "this", "with", "from", "was", "were", "are",
          "his", "her", "its", "not", "all", "any", "has", "have", "had", "she", "his",
          "que", "los", "las", "del", "por", "con", "una", "uno", "para", "como",
          "page", "www", "http", "https", "com"}


def _rasgos(texto: str, maximo: int = 400) -> Counter:
    """Bolsa de palabras acotada a los terminos mas frecuentes del documento."""
    palabras = [p for p in PALABRA.findall(_normalizar(texto)) if p not in VACIAS]
    return Counter(dict(Counter(palabras).most_common(maximo)))


class ModeloEntrenado:
    """Naive Bayes multinomial minimalista, entrenado desde la base de datos."""

    def __init__(self) -> None:
        self.prior: Dict[str, float] = {}
        self.verosimilitud: Dict[str, Dict[str, float]] = {}
        self.denominador: Dict[str, float] = {}
        self.vocabulario: int = 0
        self.ejemplos: int = 0
        self.categorias: List[str] = []

    @property
    def listo(self) -> bool:
        return self.ejemplos >= MIN_EJEMPLOS_NB and len(self.categorias) >= 2

    def entrenar(self, muestras: List[Tuple[str, str]]) -> "ModeloEntrenado":
        conteo_clase: Counter = Counter()
        conteo_termino: Dict[str, Counter] = defaultdict(Counter)
        vocabulario = set()
        for texto, categoria in muestras:
            conteo_clase[categoria] += 1
            for palabra, veces in _rasgos(texto).items():
                conteo_termino[categoria][palabra] += veces
                vocabulario.add(palabra)
        self.ejemplos = sum(conteo_clase.values())
        self.categorias = sorted(conteo_clase)
        self.vocabulario = max(1, len(vocabulario))
        for categoria in self.categorias:
            self.prior[categoria] = math.log(conteo_clase[categoria] / self.ejemplos)
            total = sum(conteo_termino[categoria].values())
            self.denominador[categoria] = total + self.vocabulario
            self.verosimilitud[categoria] = {
                palabra: math.log((veces + 1) / self.denominador[categoria])
                for palabra, veces in conteo_termino[categoria].items()}
        return self

    def predecir(self, texto: str) -> Tuple[str, float]:
        if not self.listo:
            return "", 0.0
        rasgos = _rasgos(texto)
        puntajes: Dict[str, float] = {}
        for categoria in self.categorias:
            desconocido = math.log(1 / self.denominador[categoria])
            total = self.prior[categoria]
            for palabra, veces in rasgos.items():
                total += veces * self.verosimilitud[categoria].get(palabra, desconocido)
            puntajes[categoria] = total
        mejor = max(puntajes, key=puntajes.get)
        maximo = puntajes[mejor]
        suma = sum(math.exp(v - maximo) for v in puntajes.values())   # softmax estable
        return mejor, 1.0 / suma if suma else 0.0


_MODELO: Optional[ModeloEntrenado] = None


def modelo_actual(recargar: bool = False) -> ModeloEntrenado:
    global _MODELO
    if _MODELO is None or recargar:
        filas = db.query(
            "SELECT texto, categoria FROM doc_entrenamiento ORDER BY id DESC LIMIT 800")
        _MODELO = ModeloEntrenado().entrenar([(f["texto"], f["categoria"]) for f in filas])
    return _MODELO


def registrar_correccion(texto: str, categoria: str, documento_id: int = 0) -> None:
    """Guarda un ejemplo y reentrena: el sistema aprende de cada correccion."""
    db.execute(
        "INSERT INTO doc_entrenamiento (documento_id, categoria, texto, creado) "
        "VALUES (?,?,?,?)",
        (documento_id, categoria, _normalizar(texto)[:20000], db.now_iso()))
    modelo_actual(recargar=True)


# --------------------------------------------------------------------------
# Decision combinada
# --------------------------------------------------------------------------
def clasificar(texto: str, titulo: str = "", nombre_archivo: str = "") -> Resultado:
    resultado = clasificar_por_reglas(texto, titulo, nombre_archivo)
    modelo = modelo_actual()
    if not modelo.listo:
        return resultado

    categoria_nb, probabilidad = modelo.predecir(texto)
    resultado.nb_categoria = categoria_nb
    resultado.nb_probabilidad = probabilidad
    resultado.metodo = "reglas + modelo entrenado"

    if categoria_nb == resultado.categoria:
        resultado.confianza = min(0.99, resultado.confianza + 0.18 * probabilidad)
        resultado.motivo += f" El modelo entrenado coincide ({probabilidad:.0%})."
    elif probabilidad >= 0.75 and resultado.confianza < UMBRAL_REVISION:
        # las reglas dudan y el modelo esta seguro: manda lo aprendido
        resultado.motivo = (f"Las reglas dudaban ({resultado.categoria}); el modelo "
                            f"entrenado con correcciones previas indica {categoria_nb} "
                            f"({probabilidad:.0%}).")
        resultado.categoria = categoria_nb
        resultado.nombre = nombre_categoria(categoria_nb)
        resultado.confianza = min(0.9, probabilidad)
    else:
        resultado.motivo += (f" El modelo entrenado sugeria {categoria_nb} "
                             f"({probabilidad:.0%}): se marca para revision.")
        resultado.confianza = min(resultado.confianza, UMBRAL_REVISION - 0.01)

    resultado.requiere_revision = resultado.confianza < UMBRAL_REVISION
    return resultado

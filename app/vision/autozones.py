"""Deteccion automatica de puntos criticos (zonas).

Dos formas de proponer zonas sin dibujarlas a mano:

1. **Por escena** (`suggest_from_image`): se detectan los objetos del espacio
   (sillas, escritorios, monitores, laptops, personas) y se agrupan por
   cercania. Cada grupo se convierte en un poligono y se nombra segun los
   objetos que lo dominan: un grupo de sillas + laptops es un area de trabajo,
   una mesa grande con pantalla es una sala de juntas.

2. **Por actividad** (`suggest_from_activity`): se acumula un mapa de calor con
   las trayectorias ya registradas en la base de datos. Las celdas donde la
   gente *permanece* se proponen como areas; las celdas donde la gente solo
   *pasa* (velocidad alta, poca estancia) se proponen como pasillos o accesos.

En ambos casos la salida es una lista de zonas candidatas, en el mismo formato
que usa el editor manual, para que la persona las revise antes de guardarlas.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .. import db
from .detector import BaseDetector, Detection, build_detector

GW, GH = 128, 72          # rejilla de analisis (relacion 16:9)
MIN_CELLS = 28            # area minima de una zona candidata
MAX_ZONES = 8

PALETA = ["#7d97b8", "#839a8c", "#a89578", "#8a8698", "#7d9495", "#9a8b96",
          "#72879c", "#a98a72"]

TRABAJO = {"laptop", "keyboard", "mouse", "tv", "book", "cup", "cell phone"}
ASIENTOS = {"chair", "couch", "bench"}
REUNION = {"dining table", "tv"}
PERTENENCIAS = {"backpack", "handbag", "suitcase", "bottle"}


def _poligono(mask: np.ndarray) -> List[List[float]]:
    """Contorno simplificado de una region de la rejilla, ya normalizado."""
    contornos, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return []
    cnt = max(contornos, key=cv2.contourArea)
    eps = 0.02 * cv2.arcLength(cnt, True)
    aprox = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
    if len(aprox) < 3:
        x, y, w, h = cv2.boundingRect(cnt)
        aprox = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    if len(aprox) > 10:                       # mantenerlo legible y editable
        x, y, w, h = cv2.boundingRect(cnt)
        aprox = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
    return [[round(float(px) / GW, 4), round(float(py) / GH, 4)] for px, py in aprox]


def _nombrar(clases: Dict[str, int], transito: bool, indice: int,
             aforo: Optional[int] = None) -> Tuple[str, str, int, int]:
    """Devuelve (nombre, tipo, aforo sugerido, alerta de permanencia en s)."""
    asientos = sum(n for c, n in clases.items() if c in ASIENTOS)
    trabajo = sum(n for c, n in clases.items() if c in TRABAJO)
    mesa = clases.get("dining table", 0)
    personas = clases.get("person", 0)

    def cap(valor: int) -> int:
        return int(min(20, max(2, aforo if aforo is not None else valor)))

    if transito:
        return (f"Pasillo / Acceso {indice}", "acceso", cap(6), 180)
    if mesa and (asientos >= 3 or clases.get("tv")):
        return (f"Sala de juntas {indice}", "area", cap(asientos or 6), 5400)
    if asientos or trabajo:
        return (f"Area de trabajo {indice}", "area", cap(asientos or trabajo), 3600)
    if personas:
        return (f"Zona de actividad {indice}", "area", cap(personas + 1), 900)
    return (f"Zona {indice}", "area", cap(6), 900)


def _regiones(grid: np.ndarray, umbral: float) -> List[np.ndarray]:
    """Componentes conexas de la rejilla por encima del umbral."""
    binaria = (grid >= umbral).astype(np.uint8)
    if not binaria.any():
        return []
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(binaria, 8)
    salida = []
    orden = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    for i in orden[:MAX_ZONES]:
        if stats[i, cv2.CC_STAT_AREA] < MIN_CELLS:
            continue
        salida.append((etiquetas == i))
    return salida


# --------------------------------------------------------------------------
# 1. Por escena: objetos detectados en un cuadro
# --------------------------------------------------------------------------
CLASES_ESCENA = ["person", "chair", "couch", "bench", "dining table", "tv", "laptop",
                 "keyboard", "mouse", "book", "cup", "bottle", "potted plant",
                 "backpack", "handbag", "suitcase", "refrigerator", "microwave", "sink"]


def suggest_from_frames(frames: Sequence[np.ndarray],
                        detector: Optional[BaseDetector] = None) -> Dict[str, Any]:
    """Como `suggest_from_image` pero acumulando varios cuadros de un video.

    Tomar varias muestras evita que una zona se pierda porque justo en ese
    instante no habia nadie ni nada en esa parte del encuadre.
    """
    frames = [f for f in frames if f is not None]
    if not frames:
        return {"zones": [], "detecciones": 0,
                "mensaje": "No se pudo leer ningun cuadro del archivo."}
    det = detector or build_detector(classes=CLASES_ESCENA)
    acumuladas: List[Detection] = []
    referencia = frames[0]
    alto_ref, ancho_ref = referencia.shape[:2]
    for f in frames:
        alto, ancho = f.shape[:2]
        for x in det.detect(f):
            if (alto, ancho) != (alto_ref, ancho_ref):   # normaliza a la referencia
                ex, ey = ancho_ref / ancho, alto_ref / alto
                x = Detection(x.x1 * ex, x.y1 * ey, x.x2 * ex, x.y2 * ey, x.conf, x.label)
            acumuladas.append(x)
    return _zonas_desde_detecciones(acumuladas, ancho_ref, alto_ref, det.name,
                                    len(frames))


def suggest_from_image(frame: np.ndarray,
                       detector: Optional[BaseDetector] = None) -> Dict[str, Any]:
    det = detector or build_detector(classes=CLASES_ESCENA)
    detecciones: List[Detection] = det.detect(frame)
    alto, ancho = frame.shape[:2]
    return _zonas_desde_detecciones(detecciones, ancho, alto, det.name, 1)


def _zonas_desde_detecciones(detecciones: List[Detection], ancho: int, alto: int,
                             backend: str, cuadros: int) -> Dict[str, Any]:
    if not detecciones:
        return {"zones": [], "detecciones": 0, "backend": backend,
                "mensaje": "No se detectaron objetos ni personas. Prueba con una "
                           "toma mas amplia del espacio o con otro momento del video."}

    grid = np.zeros((GH, GW), dtype=np.float32)
    puntos: List[Tuple[int, int, str]] = []
    for d in detecciones:
        x1 = int(max(0, d.x1 / ancho) * (GW - 1))
        x2 = int(min(1, d.x2 / ancho) * (GW - 1))
        y1 = int(max(0, d.y1 / alto) * (GH - 1))
        y2 = int(min(1, d.y2 / alto) * (GH - 1))
        grid[y1:y2 + 1, x1:x2 + 1] += 1.0
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        puntos.append((cx, cy, d.label))

    # dilatar para unir muebles y equipos contiguos en una sola area
    grid = cv2.dilate(grid, np.ones((7, 7), np.uint8), iterations=1)
    grid = cv2.GaussianBlur(grid, (9, 9), 0)

    zonas = []
    for i, mask in enumerate(_regiones(grid, umbral=0.35), start=1):
        clases: Dict[str, int] = {}
        for cx, cy, label in puntos:
            if mask[cy, cx]:
                clases[label] = clases.get(label, 0) + 1
        poly = _poligono(mask)
        if len(poly) < 3:
            continue
        # Con varios cuadros, el mismo mueble aparece repetido: se normaliza
        # para que el aforo sugerido sea "cuantos hay", no "cuantas veces se vio".
        normal = {c: max(1, round(n / max(1, cuadros))) for c, n in clases.items()}
        nombre, tipo, aforo, dwell = _nombrar(normal, transito=False, indice=i)
        zonas.append({
            "name": nombre, "kind": tipo, "polygon": poly,
            "color": PALETA[(i - 1) % len(PALETA)],
            "max_occupancy": aforo, "dwell_alert_s": dwell,
            "evidencia": {"detecciones": clases, "por_cuadro": normal,
                          "cuadros": cuadros},
            "motivo": ("objetos agrupados: " + ", ".join(
                f"{n}x {c}" for c, n in sorted(normal.items(), key=lambda kv: -kv[1])[:4])
                if normal else "region con actividad"),
        })
    return {"zones": zonas, "detecciones": len(detecciones), "backend": backend,
            "cuadros": cuadros,
            "mensaje": f"{len(zonas)} zona(s) propuestas a partir de "
                       f"{len(detecciones)} detecciones"
                       + (f" en {cuadros} cuadros del video." if cuadros > 1 else ".")}


# --------------------------------------------------------------------------
# 2. Por actividad: trayectorias ya guardadas en la base de datos
# --------------------------------------------------------------------------
def suggest_from_activity(session_id: Optional[int] = None) -> Dict[str, Any]:
    sql = "SELECT label, path_json, duration_s FROM tracks"
    params: List[Any] = []
    if session_id:
        sql += " WHERE session_id=?"
        params.append(session_id)
    filas = db.query(sql + " ORDER BY id DESC LIMIT 4000", params)
    if not filas:
        return {"zones": [], "mensaje": "Todavia no hay trayectorias registradas. "
                                        "Analiza un video o usa la camara unos minutos "
                                        "y vuelve a intentarlo."}

    permanencia = np.zeros((GH, GW), dtype=np.float32)
    transito = np.zeros((GH, GW), dtype=np.float32)
    clases_celda: Dict[Tuple[int, int], Dict[str, int]] = {}
    tracks_celda: Dict[Tuple[int, int], set] = {}
    puntos_totales = 0

    for indice_track, fila in enumerate(filas):
        try:
            camino = json.loads(fila["path_json"] or "[]")
        except json.JSONDecodeError:
            continue
        if not camino:
            continue
        previo = None
        for px, py in camino:
            cx = int(min(max(px, 0.0), 0.999) * (GW - 1))
            cy = int(min(max(py, 0.0), 0.999) * (GH - 1))
            permanencia[cy, cx] += 1.0
            puntos_totales += 1
            if previo is not None:
                velocidad = math.dist((cx, cy), previo)
                transito[cy, cx] += velocidad
            previo = (cx, cy)
            celda = clases_celda.setdefault((cx, cy), {})
            etiqueta = fila["label"] or "person"
            celda[etiqueta] = celda.get(etiqueta, 0) + 1
            tracks_celda.setdefault((cx, cy), set()).add(indice_track)

    if puntos_totales < 20:
        return {"zones": [], "mensaje": "Hay muy pocos datos de movimiento para "
                                        "proponer zonas con criterio."}

    permanencia = cv2.GaussianBlur(permanencia, (7, 7), 0)
    transito = cv2.GaussianBlur(transito, (7, 7), 0)
    umbral = float(np.percentile(permanencia[permanencia > 0], 60))

    zonas = []
    for i, mask in enumerate(_regiones(permanencia, umbral), start=1):
        celdas = max(1, int(mask.sum()))
        puntos = float(permanencia[mask].sum())
        clases: Dict[str, int] = {}
        distintos: set = set()
        for (cx, cy), conteo in clases_celda.items():
            if mask[cy, cx]:
                for c, n in conteo.items():
                    clases[c] = clases.get(c, 0) + n
                distintos |= tracks_celda.get((cx, cy), set())
        poly = _poligono(mask)
        if len(poly) < 3:
            continue

        # Dos senales independientes para separar permanencia de paso:
        #   densidad  = muestras por celda (quedarse concentra muestras)
        #   velocidad = celdas recorridas por muestra (pasar las dispersa)
        densidad = puntos / celdas
        velocidad = float(transito[mask].sum()) / max(puntos, 1.0)
        es_transito = densidad < 2.0 and velocidad > 1.5

        nombre, tipo, aforo, dwell = _nombrar(clases, es_transito, i,
                                              aforo=len(distintos) or 2)
        zonas.append({
            "name": nombre, "kind": tipo, "polygon": poly,
            "color": PALETA[(i - 1) % len(PALETA)],
            "max_occupancy": aforo, "dwell_alert_s": dwell,
            "evidencia": {"celdas": celdas, "muestras": int(puntos),
                          "personas_distintas": len(distintos),
                          "densidad": round(densidad, 2),
                          "velocidad": round(velocidad, 2)},
            "motivo": (f"corredor de paso: {velocidad:.1f} celdas por muestra, "
                       f"densidad {densidad:.1f}" if es_transito else
                       f"concentracion de permanencia: densidad {densidad:.1f} "
                       f"muestras por celda ({len(distintos)} personas)"),
        })
    return {"zones": zonas, "puntos": puntos_totales,
            "mensaje": f"{len(zonas)} zona(s) propuestas a partir de "
                       f"{len(filas)} trayectorias."}


def apply_zones(zonas: Sequence[Dict[str, Any]], reemplazar: bool = False) -> int:
    """Guarda las zonas propuestas (renombrando si el nombre ya existe)."""
    if reemplazar:
        db.execute("DELETE FROM zones")
    existentes = {z["name"] for z in db.query("SELECT name FROM zones")}
    guardadas = 0
    for z in zonas:
        nombre = z.get("name") or "Zona"
        base, n = nombre, 2
        while nombre in existentes:
            nombre = f"{base} ({n})"
            n += 1
        existentes.add(nombre)
        db.execute(
            """INSERT INTO zones (name, kind, polygon_json, color, max_occupancy,
                                  dwell_alert_s, enabled, created_at)
               VALUES (?,?,?,?,?,?,1,?)""",
            (nombre, z.get("kind", "area"), json.dumps(z.get("polygon", [])),
             z.get("color", "#7d97b8"), int(z.get("max_occupancy", 6)),
             int(z.get("dwell_alert_s", 300)), db.now_iso()))
        guardadas += 1
    return guardadas

"""Puntos criticos (zonas) y su logica de negocio.

Una zona es un poligono en coordenadas normalizadas (0..1), por lo que las
mismas zonas sirven para la camara en vivo y para videos de cualquier
resolucion. Cada frame se evalua:
  - que tracks estan dentro de cada zona (punto de contacto con el piso),
  - entradas y salidas (conteo direccional),
  - permanencia acumulada por track y por zona,
  - aforo instantaneo contra el maximo configurado.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .. import db
from .tracker import Track


@dataclass
class Zone:
    id: int
    name: str
    kind: str
    polygon: List[List[float]]
    color: str = "#7d97b8"
    max_occupancy: int = 6
    dwell_alert_s: int = 180
    enabled: bool = True
    _scaled: Dict[Tuple[int, int], Any] = field(default_factory=dict, repr=False)

    def scaled(self, width: int, height: int) -> np.ndarray:
        key = (width, height)
        if key not in self._scaled:
            pts = np.array([[p[0] * width, p[1] * height] for p in self.polygon],
                           dtype=np.float32)
            self._scaled = {key: pts}
        return self._scaled[key]

    def contains(self, x: float, y: float, width: int, height: int) -> bool:
        import cv2
        pts = self.scaled(width, height)
        if len(pts) < 3:
            return False
        return cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "polygon": self.polygon, "color": self.color,
            "max_occupancy": self.max_occupancy, "dwell_alert_s": self.dwell_alert_s,
            "enabled": self.enabled,
        }


def load_zones() -> List[Zone]:
    rows = db.query("SELECT * FROM zones WHERE enabled=1 ORDER BY id")
    zones = []
    for r in rows:
        try:
            poly = json.loads(r["polygon_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        zones.append(Zone(
            id=r["id"], name=r["name"], kind=r["kind"], polygon=poly,
            color=r["color"] or "#7d97b8",
            max_occupancy=int(r["max_occupancy"] or 0),
            dwell_alert_s=int(r["dwell_alert_s"] or 0),
            enabled=bool(r["enabled"]),
        ))
    return zones


def fmt_lapso(segundos: float) -> str:
    """Formatea un lapso en la unidad mas legible (s / min / h)."""
    segundos = max(0.0, float(segundos))
    if segundos < 60:
        return f"{segundos:.0f} s"
    if segundos < 3600:
        return f"{segundos/60:.1f} min"
    return f"{segundos/3600:.1f} h"


@dataclass
class ZoneEvent:
    type: str
    zone: str
    message: str
    severity: str = "info"
    track_key: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


class ZoneManager:
    """Estado por sesion: ocupacion, conteos y permanencia por zona."""

    def __init__(self, zones: Optional[List[Zone]] = None):
        self.zones: List[Zone] = zones if zones is not None else load_zones()
        self.entries: Dict[str, int] = {z.name: 0 for z in self.zones}
        self.exits: Dict[str, int] = {z.name: 0 for z in self.zones}
        self.occupancy: Dict[str, int] = {z.name: 0 for z in self.zones}
        self.peak: Dict[str, int] = {z.name: 0 for z in self.zones}
        self.dwell_total: Dict[str, float] = {z.name: 0.0 for z in self.zones}
        self.visits: Dict[str, int] = {z.name: 0 for z in self.zones}
        self.last_activity: Dict[str, float] = {z.name: 0.0 for z in self.zones}
        self._over_capacity: Dict[str, bool] = {z.name: False for z in self.zones}

    def reload(self) -> None:
        self.__init__(load_zones())

    def update(self, tracks: List[Track], now: float, width: int, height: int
               ) -> List[ZoneEvent]:
        events: List[ZoneEvent] = []
        occ = {z.name: 0 for z in self.zones}

        for tr in tracks:
            ax, ay = tr.anchor
            inside = {z.name for z in self.zones if z.contains(ax, ay, width, height)}
            entered = inside - tr.current_zones
            left = tr.current_zones - inside

            for name in entered:
                tr.zone_since[name] = now
                self.entries[name] = self.entries.get(name, 0) + 1
                self.visits[name] = self.visits.get(name, 0) + 1
                self.last_activity[name] = now
                events.append(ZoneEvent(
                    "zone_enter", name,
                    f"{tr.label} {tr.key} entro a '{name}'",
                    "info", tr.key, {"label": tr.label},
                ))
            for name in left:
                started = tr.zone_since.pop(name, now)
                dwell = max(0.0, now - started)
                tr.zones[name] = tr.zones.get(name, 0.0) + dwell
                self.dwell_total[name] = self.dwell_total.get(name, 0.0) + dwell
                self.exits[name] = self.exits.get(name, 0) + 1
                tr.zone_alerted.discard(name)
                events.append(ZoneEvent(
                    "zone_exit", name,
                    f"{tr.label} {tr.key} salio de '{name}' tras {fmt_lapso(dwell)}",
                    "info", tr.key, {"dwell_s": round(dwell, 1)},
                ))
            tr.current_zones = inside

            for name in inside:
                occ[name] = occ.get(name, 0) + 1
                self.last_activity[name] = now
                zone = self._zone(name)
                if zone and zone.dwell_alert_s > 0 and name not in tr.zone_alerted:
                    elapsed = now - tr.zone_since.get(name, now)
                    if elapsed >= zone.dwell_alert_s:
                        tr.zone_alerted.add(name)
                        sev = "critical" if zone.kind == "restringida" else "warning"
                        events.append(ZoneEvent(
                            "permanencia_excesiva", name,
                            f"Permanencia de {fmt_lapso(elapsed)} en '{name}' "
                            f"(limite {fmt_lapso(zone.dwell_alert_s)})",
                            sev, tr.key, {"dwell_s": round(elapsed, 1)},
                        ))

        # --- aforo -----------------------------------------------------------
        for zone in self.zones:
            n = occ.get(zone.name, 0)
            self.occupancy[zone.name] = n
            self.peak[zone.name] = max(self.peak.get(zone.name, 0), n)
            over = zone.max_occupancy > 0 and n > zone.max_occupancy
            if over and not self._over_capacity.get(zone.name):
                events.append(ZoneEvent(
                    "aforo_excedido", zone.name,
                    f"Aforo excedido en '{zone.name}': {n} personas "
                    f"(maximo {zone.max_occupancy})",
                    "critical", "", {"count": n, "max": zone.max_occupancy},
                ))
            self._over_capacity[zone.name] = over

        return events

    def _zone(self, name: str) -> Optional[Zone]:
        for z in self.zones:
            if z.name == name:
                return z
        return None

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            z.name: {
                "occupancy": self.occupancy.get(z.name, 0),
                "entries": self.entries.get(z.name, 0),
                "exits": self.exits.get(z.name, 0),
                "peak": self.peak.get(z.name, 0),
                "dwell_total_s": round(self.dwell_total.get(z.name, 0.0), 1),
                "visits": self.visits.get(z.name, 0),
                "max_occupancy": z.max_occupancy,
                "color": z.color,
                "kind": z.kind,
            }
            for z in self.zones
        }

    def flush_open_dwell(self, tracks: List[Track], now: float) -> None:
        """Cierra la permanencia abierta (fin de sesion / cierre de track)."""
        for tr in tracks:
            for name in list(tr.current_zones):
                started = tr.zone_since.pop(name, now)
                dwell = max(0.0, now - started)
                tr.zones[name] = tr.zones.get(name, 0.0) + dwell
                self.dwell_total[name] = self.dwell_total.get(name, 0.0) + dwell
            tr.current_zones = set()

"""Pipeline de analisis: frame -> detecciones -> tracks -> zonas -> BD.

Un `Analyzer` es el cerebro de una sesion (camara en vivo o video subido).
Por cada frame analizado:
  1. detecta objetos/personas con el backend activo,
  2. asocia detecciones a tracks anonimos persistentes,
  3. evalua zonas (entradas, salidas, permanencia, aforo),
  4. calcula indice de movimiento y metricas agregadas,
  5. escribe en SQLite: eventos al momento, fotos de estado cada N segundos y
     un resumen narrado cada minuto ("lo que paso y lo que esta pasando").
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import db
from .config import CONFIG, SNAPSHOT_DIR
from .vision.detector import BaseDetector, Detection, build_detector
from .vision.labels import describir, etiquetas, nombre
from .vision.tracker import Track, Tracker
from .vision.zones import ZoneEvent, ZoneManager, fmt_lapso

log = logging.getLogger("officevision.pipeline")

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _parse_hhmm(value: str, fallback: Tuple[int, int]) -> Tuple[int, int]:
    try:
        h, m = str(value).split(":")[:2]
        return int(h), int(m)
    except Exception:
        return fallback


def in_work_hours(dt: datetime) -> bool:
    start = _parse_hhmm(CONFIG.get("work_start"), (7, 0))
    end = _parse_hhmm(CONFIG.get("work_end"), (18, 0))
    days = set(CONFIG.get("work_days") or [0, 1, 2, 3, 4])
    if dt.weekday() not in days:
        return False
    minutes = dt.hour * 60 + dt.minute
    return start[0] * 60 + start[1] <= minutes <= end[0] * 60 + end[1]


class Analyzer:
    def __init__(self, session_id: int, session_tag: str, kind: str = "live",
                 detector: Optional[BaseDetector] = None,
                 zone_manager: Optional[ZoneManager] = None,
                 base_wall: Optional[datetime] = None):
        self.session_id = session_id
        self.kind = kind
        self.detector = detector or build_detector()
        self.zones = zone_manager or ZoneManager()
        self.tracker = Tracker(
            session_tag,
            iou_threshold=float(CONFIG.get("track_iou_match")),
            max_age=int(CONFIG.get("track_max_age")),
            min_hits=int(CONFIG.get("track_min_hits")),
        )
        # Segundo tracker, solo para objetos: permite contar objetos unicos,
        # avisar cuando aparece o desaparece uno y detectar objetos de valor
        # sin supervision. Las reglas de aforo siguen contando solo personas.
        self.obj_tracker = Tracker(
            f"{session_tag}-O",
            iou_threshold=0.35,
            max_age=int(CONFIG.get("track_max_age")) * 2,
            min_hits=int(CONFIG.get("track_min_hits")),
        )
        self.base_wall = base_wall or datetime.now()
        self.lock = threading.RLock()

        # estado temporal
        self._prev_gray: Optional[np.ndarray] = None
        self._last_snapshot = -1e9
        self._last_summary = -1e9
        self._interval_persons: List[int] = []
        self._interval_events = 0
        self._interval_alerts = 0
        self._interval_entries: Dict[str, int] = {}
        self._start_mono = time.monotonic()

        # metricas acumuladas
        self.frames_analyzed = 0
        self.peak_persons = 0
        self.unique_persons = 0
        self.total_events = 0
        self.total_alerts = 0
        self.movement_avg = 0.0
        self.class_counts: Dict[str, int] = {}
        self.object_unique: Dict[str, int] = {}     # clase -> objetos distintos vistos
        self._objects_seen: set = set()             # track_key ya anunciados
        self._objects_alone: Dict[str, float] = {}  # track_key -> t sin persona cerca
        self._objects_alerted: set = set()
        self.last_result: Dict[str, Any] = {}
        self._crowd_active = False
        self._after_hours_notified = False
        self._closed_tracks_saved = 0

    # ------------------------------------------------------------------
    # utilidades de tiempo
    # ------------------------------------------------------------------
    def _wall(self, video_ts: Optional[float]) -> datetime:
        if self.kind == "video" and video_ts is not None:
            return self.base_wall + timedelta(seconds=float(video_ts))
        return datetime.now()

    def _clock(self, video_ts: Optional[float]) -> float:
        """Reloj usado para permanencias: tiempo de video o tiempo real."""
        if self.kind == "video" and video_ts is not None:
            return float(video_ts)
        return time.monotonic()

    # ------------------------------------------------------------------
    # analisis de un frame
    # ------------------------------------------------------------------
    def process(self, frame: np.ndarray, video_ts: Optional[float] = None,
                annotate: bool = False) -> Dict[str, Any]:
        with self.lock:
            t0 = time.monotonic()
            height, width = frame.shape[:2]
            wall = self._wall(video_ts)
            wall_iso = wall.isoformat(timespec="seconds")
            now = self._clock(video_ts)

            detections: List[Detection] = self.detector.detect(frame)
            primary = CONFIG.get("primary_class", "person")
            persons = [d for d in detections if d.label == primary]
            others = [d for d in detections if d.label != primary]

            active, closed = self.tracker.update(persons, now, wall_iso, video_ts,
                                                 width, height)
            zone_events = self.zones.update(active, now, width, height,
                                            en_horario=in_work_hours(wall))

            obj_active: List[Track] = []
            obj_closed: List[Track] = []
            if CONFIG.get("track_objects") and others:
                obj_active, obj_closed = self.obj_tracker.update(
                    others, now, wall_iso, video_ts, width, height)
            elif CONFIG.get("track_objects"):
                obj_active, obj_closed = self.obj_tracker.update(
                    [], now, wall_iso, video_ts, width, height)
            movement = self._movement_index(frame)

            self.frames_analyzed += 1
            self.peak_persons = max(self.peak_persons, len(active))
            self.movement_avg += (movement - self.movement_avg) / self.frames_analyzed
            for d in detections:
                self.class_counts[d.label] = self.class_counts.get(d.label, 0) + 1

            # --- eventos de zona + reglas globales --------------------------
            events = list(zone_events)
            events.extend(self._global_rules(active, wall, now))
            events.extend(self._object_rules(obj_active, obj_closed, active, now,
                                             width, height))
            snapshot_path = ""
            if events:
                worst = max(events, key=lambda e: SEVERITY_ORDER.get(e.severity, 0))
                if (SEVERITY_ORDER.get(worst.severity, 0) >= 1
                        and CONFIG.get("store_snapshots")):
                    snapshot_path = self._store_snapshot(frame, active, wall)
            for ev in events:
                self._persist_event(ev, wall_iso, video_ts, snapshot_path)

            # --- persistencia periodica -------------------------------------
            self._interval_persons.append(len(active))
            self._maybe_snapshot(now, wall_iso, video_ts, len(active), len(others), movement)
            self._maybe_summary(now, wall_iso, video_ts)
            for tr in closed:
                self._save_track(tr)
            for tr in obj_closed:
                self._save_track(tr)

            elapsed = max(1e-6, time.monotonic() - t0)
            inventario = self._inventory(obj_active or [], others, len(active))
            result = {
                "session_id": self.session_id,
                "ts": wall_iso,
                "video_ts": round(video_ts, 2) if video_ts is not None else None,
                "width": width,
                "height": height,
                "persons": len(active),
                "objects": len(obj_active) or len(others),
                "tracks": [t.as_dict(width, height) for t in active],
                "objects_detail": ([t.as_dict(width, height) for t in obj_active]
                                   or [
                    {"key": "", "label": d.label, "conf": round(d.conf, 2),
                     "duration": 0, "zones": [],
                     "norm": [round(d.x1 / width, 4), round(d.y1 / height, 4),
                              round(d.x2 / width, 4), round(d.y2 / height, 4)]}
                    for d in others
                ]),
                "inventory": inventario,
                "descripcion": inventario["descripcion"],
                "zones": self.zones.snapshot(),
                "movement": round(movement, 3),
                "fps": round(1.0 / elapsed, 1),
                "latency_ms": round(elapsed * 1000, 1),
                "events": [
                    {"type": e.type, "zone": e.zone, "message": e.message,
                     "severity": e.severity, "track": e.track_key}
                    for e in events
                ],
                "metrics": self.metrics(),
                "detector": self.detector.name,
            }
            self.last_result = result
            if annotate:
                result["frame"] = self.annotate(frame, active, others)
            return result

    # ------------------------------------------------------------------
    def _movement_index(self, frame: np.ndarray) -> float:
        small = cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY)
        if self._prev_gray is None:
            self._prev_gray = small
            return 0.0
        diff = cv2.absdiff(small, self._prev_gray)
        self._prev_gray = small
        return float(np.count_nonzero(diff > 25)) / diff.size

    def _global_rules(self, active: List[Track], wall: datetime, now: float
                      ) -> List[ZoneEvent]:
        """Reglas que no dependen de una zona concreta."""
        out: List[ZoneEvent] = []
        crowd = int(CONFIG.get("crowd_threshold") or 0)
        if crowd and len(active) > crowd:
            if not self._crowd_active:
                self._crowd_active = True
                out.append(ZoneEvent(
                    "aglomeracion", "",
                    f"Aglomeracion detectada: {len(active)} personas simultaneas "
                    f"(umbral {crowd})", "critical", "", {"count": len(active)},
                ))
        elif len(active) <= max(0, crowd - 2):
            self._crowd_active = False

        if active and not in_work_hours(wall) and not self._after_hours_notified:
            self._after_hours_notified = True
            out.append(ZoneEvent(
                "actividad_fuera_horario", "",
                f"Actividad fuera del horario laboral ({wall.strftime('%a %H:%M')}): "
                f"{len(active)} persona(s)", "warning", "", {"count": len(active)},
            ))
        if in_work_hours(wall):
            self._after_hours_notified = False

        idle_limit = float(CONFIG.get("idle_zone_alert_s") or 0)
        if idle_limit and in_work_hours(wall):
            for zone in self.zones.zones:
                if zone.kind == "restringida":
                    continue
                last = self.zones.last_activity.get(zone.name, 0.0)
                if last == 0.0:
                    self.zones.last_activity[zone.name] = self._start_mono if self.kind == "live" else 0.0
                    continue
                if now - last > idle_limit:
                    self.zones.last_activity[zone.name] = now  # evita repetir
                    out.append(ZoneEvent(
                        "zona_inactiva", zone.name,
                        f"'{zone.name}' sin actividad por {fmt_lapso(idle_limit)} en "
                        f"horario laboral", "warning", "", {"idle_s": idle_limit},
                    ))
        return out

    # ------------------------------------------------------------------
    def _object_rules(self, obj_active: List[Track], obj_closed: List[Track],
                      persons: List[Track], now: float, width: int, height: int
                      ) -> List[ZoneEvent]:
        """Reconocimiento de objetos: altas, bajas y objetos sin supervision."""
        out: List[ZoneEvent] = []
        if not CONFIG.get("track_objects"):
            return out
        warmup = int(CONFIG.get("object_warmup_frames") or 25)
        valiosos = set(CONFIG.get("valuable_classes") or [])
        radio = float(CONFIG.get("unattended_radius") or 0.22)
        limite = float(CONFIG.get("unattended_alert_s") or 120)
        diagonal = (width ** 2 + height ** 2) ** 0.5

        for tr in obj_active:
            zona = ", ".join(sorted(self._zones_of(tr, width, height))) or "el encuadre"

            # --- objeto nuevo en escena ---------------------------------
            if tr.key not in self._objects_seen:
                self._objects_seen.add(tr.key)
                self.object_unique[tr.label] = self.object_unique.get(tr.label, 0) + 1
                if self.frames_analyzed > warmup:
                    out.append(ZoneEvent(
                        "objeto_nuevo", "",
                        f"Reconocido en escena: {nombre(tr.label)} ({tr.key}) en {zona}",
                        "info", tr.key,
                        {"clase": tr.label, "nombre": nombre(tr.label)},
                    ))

            # --- objeto de valor sin persona cerca ----------------------
            if tr.label not in valiosos:
                continue
            ox, oy = tr.centroid
            cerca = any(
                (((ox - px) ** 2 + (oy - py) ** 2) ** 0.5) / diagonal <= radio
                for px, py in (t.centroid for t in persons)
            )
            if cerca:
                self._objects_alone.pop(tr.key, None)
                self._objects_alerted.discard(tr.key)
                continue
            inicio = self._objects_alone.setdefault(tr.key, now)
            if now - inicio >= limite and tr.key not in self._objects_alerted:
                self._objects_alerted.add(tr.key)
                out.append(ZoneEvent(
                    "objeto_sin_supervision", "",
                    f"{nombre(tr.label).capitalize()} ({tr.key}) lleva "
                    f"{fmt_lapso(now - inicio)} sin nadie cerca en {zona}",
                    "warning", tr.key,
                    {"clase": tr.label, "nombre": nombre(tr.label),
                     "solo_s": round(now - inicio, 1)},
                ))

        # --- objeto retirado de la escena -------------------------------
        for tr in obj_closed:
            self._objects_alone.pop(tr.key, None)
            self._objects_alerted.discard(tr.key)
            if tr.key not in self._objects_seen or tr.duration < 10:
                continue
            severidad = "warning" if tr.label in valiosos else "info"
            out.append(ZoneEvent(
                "objeto_retirado", "",
                f"{nombre(tr.label).capitalize()} ({tr.key}) dejo de verse tras "
                f"{fmt_lapso(tr.duration)}", severidad, tr.key,
                {"clase": tr.label, "nombre": nombre(tr.label)},
            ))
        return out

    def _zones_of(self, tr: Track, width: int, height: int) -> List[str]:
        """Zonas que contienen el punto de apoyo de un track."""
        ax, ay = tr.anchor
        return [z.name for z in self.zones.zones if z.contains(ax, ay, width, height)]

    def _inventory(self, obj_tracks: List[Track], raw: List[Detection],
                   personas: int = 0) -> Dict[str, Any]:
        """Inventario de lo que se ve: nombres, cantidades y una frase legible."""
        visibles: Dict[str, int] = {}
        for tr in obj_tracks:
            visibles[tr.label] = visibles.get(tr.label, 0) + 1
        if not obj_tracks:
            for d in raw:
                visibles[d.label] = visibles.get(d.label, 0) + 1
        escena = dict(visibles)
        if personas:
            escena["person"] = personas
        claves = set(visibles) | set(self.object_unique) | {"person"}
        return {"visibles": visibles, "unicos": dict(self.object_unique),
                "etiquetas": etiquetas(claves),
                "descripcion": describir(escena)}

    # ------------------------------------------------------------------
    def _persist_event(self, ev: ZoneEvent, wall_iso: str, video_ts: Optional[float],
                       snapshot: str) -> None:
        self.total_events += 1
        self._interval_events += 1
        if ev.severity != "info":
            self.total_alerts += 1
            self._interval_alerts += 1
        if ev.type == "zone_enter":
            self._interval_entries[ev.zone] = self._interval_entries.get(ev.zone, 0) + 1
        db.insert_event(
            self.session_id, wall_iso, ev.type, ev.message, ev.severity,
            ev.track_key, ev.zone, video_ts,
            snapshot if ev.severity != "info" else "", ev.meta,
        )

    def _maybe_snapshot(self, now: float, wall_iso: str, video_ts: Optional[float],
                        persons: int, objects: int, movement: float) -> None:
        interval = float(CONFIG.get("snapshot_interval_s") or 5)
        if now - self._last_snapshot < interval:
            return
        self._last_snapshot = now
        # velocidad real de procesamiento (cuadros analizados / tiempo de reloj)
        fps = round(self.frames_analyzed / max(1e-6, time.monotonic() - self._start_mono), 2)
        db.insert_snapshot(
            self.session_id, wall_iso, video_ts, persons, objects, movement, fps,
            self.zones.snapshot(), dict(self.class_counts),
        )

    def _maybe_summary(self, now: float, wall_iso: str, video_ts: Optional[float]) -> None:
        interval = float(CONFIG.get("summary_interval_s") or 60)
        if self._last_summary < -1e8:
            self._last_summary = now
            return
        if now - self._last_summary < interval:
            return
        window = self._interval_persons or [0]
        avg = sum(window) / len(window)
        peak = max(window)
        entries = ", ".join(f"{z}: {n}" for z, n in sorted(self._interval_entries.items())) or "sin movimientos entre zonas"
        ventana = (f"{interval/60:.0f} min" if interval >= 60 else f"{interval:.0f} s")
        vistos = describir({c: n for c, n in self.object_unique.items()})
        message = (
            f"Resumen {ventana} - promedio {avg:.1f} personas "
            f"(pico {peak}); entradas por zona: {entries}; "
            f"reconocido hasta ahora: {vistos}; "
            f"{self._interval_events} eventos, {self._interval_alerts} alertas."
        )
        db.insert_event(
            self.session_id, wall_iso, "resumen", message, "info", "", "", video_ts,
            "", {"avg_persons": round(avg, 2), "peak": peak,
                 "entries": dict(self._interval_entries),
                 "events": self._interval_events, "alerts": self._interval_alerts},
        )
        self._last_summary = now
        self._interval_persons = []
        self._interval_events = 0
        self._interval_alerts = 0
        self._interval_entries = {}

    def _save_track(self, tr: Track) -> None:
        """Persiste un track cerrado; descarta los demasiado cortos (ruido)."""
        if not tr.confirmed or tr.duration < float(CONFIG.get("min_track_seconds") or 0):
            return
        self.zones.flush_open_dwell([tr], tr.last_mono)
        db.upsert_track(
            self.session_id, tr.key, tr.label, tr.first_ts,
            self._wall(tr.last_video_ts).isoformat(timespec="seconds"),
            tr.first_video_ts, tr.last_video_ts, round(tr.duration, 2), tr.frames,
            round(tr.avg_conf, 3), round(tr.distance_px, 1),
            {k: round(v, 1) for k, v in tr.zones.items()},
            list(tr.history)[::4],
        )
        self._closed_tracks_saved += 1
        self.unique_persons = max(self.unique_persons, self._closed_tracks_saved)

    # ------------------------------------------------------------------
    def metrics(self) -> Dict[str, Any]:
        confirmed = sum(1 for t in self.tracker.tracks.values() if t.confirmed)
        dwells = [t.duration for t in self.tracker.tracks.values()
                  if t.confirmed and t.duration > 0]
        return {
            "frames_analyzed": self.frames_analyzed,
            "peak_persons": self.peak_persons,
            "unique_persons": confirmed,
            "avg_dwell_s": round(sum(dwells) / len(dwells), 1) if dwells else 0.0,
            "total_events": self.total_events,
            "total_alerts": self.total_alerts,
            "movement_avg": round(self.movement_avg, 3),
            "classes": dict(self.class_counts),
            "objects_unique": dict(self.object_unique),
            "objects_total": sum(self.object_unique.values()),
            "objects_labels": etiquetas(self.object_unique.keys()),
            "objects_resumen": describir(dict(self.object_unique)),
        }

    # ------------------------------------------------------------------
    def annotate(self, frame: np.ndarray, tracks: List[Track],
                 others: Optional[List[Detection]] = None,
                 objects: Optional[List[Track]] = None) -> np.ndarray:
        """Dibuja zonas, cajas y etiquetas. Difumina rostros si esta activado."""
        out = frame.copy()
        h, w = out.shape[:2]
        overlay = out.copy()
        for zone in self.zones.zones:
            pts = zone.scaled(w, h).astype(np.int32)
            color = _hex_to_bgr(zone.color)
            cv2.fillPoly(overlay, [pts], color)
            cv2.polylines(out, [pts], True, color, 2)
            x, y = pts[0]
            occ = self.zones.occupancy.get(zone.name, 0)
            cv2.putText(out, f"{zone.name} [{occ}/{zone.max_occupancy}]",
                        (int(x) + 6, int(y) + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        color, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.18, out, 0.82, 0, out)

        if CONFIG.get("blur_faces"):
            for tr in tracks:
                x1, y1, x2, y2 = [int(v) for v in tr.bbox]
                fh = max(1, int((y2 - y1) * 0.33))
                x1c, y1c = max(0, x1), max(0, y1)
                x2c, y2c = min(w, x2), min(h, y1 + fh)
                if x2c > x1c and y2c > y1c:
                    roi = out[y1c:y2c, x1c:x2c]
                    k = max(9, (min(roi.shape[:2]) // 2) * 2 + 1)
                    out[y1c:y2c, x1c:x2c] = cv2.GaussianBlur(roi, (k, k), 0)

        for tr in tracks:
            x1, y1, x2, y2 = [int(v) for v in tr.bbox]
            # sage para seguimiento normal, ocre cuando hay alerta (BGR)
            color = (140, 164, 127) if not tr.zone_alerted else (98, 149, 176)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            tag = f"{tr.key} {tr.duration:.0f}s"
            if tr.current_zones:
                tag += " | " + ",".join(sorted(tr.current_zones))[:22]
            cv2.rectangle(out, (x1, max(0, y1 - 20)), (x1 + 8 * len(tag), y1), color, -1)
            cv2.putText(out, tag, (x1 + 3, max(12, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 22, 26), 1, cv2.LINE_AA)

        objetos = objects if objects is not None else [
            t for t in self.obj_tracker.tracks.values()
            if t.confirmed and not t.closed and t.misses == 0]
        for obj in objetos:
            x1, y1, x2, y2 = [int(v) for v in obj.bbox]
            solo = obj.key in self._objects_alerted
            color = (98, 149, 176) if solo else (150, 150, 150)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
            cv2.putText(out, f"{nombre(obj.label)} {obj.key.split('-')[-1]}",
                        (x1 + 2, max(10, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        color, 1, cv2.LINE_AA)
        for det in others or []:
            cv2.rectangle(out, (int(det.x1), int(det.y1)), (int(det.x2), int(det.y2)),
                          (140, 145, 152), 1)
            cv2.putText(out, nombre(det.label), (int(det.x1), max(10, int(det.y1) - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 145, 152), 1, cv2.LINE_AA)

        banner = (f"Personas: {len(tracks)} | Objetos: {len(objetos)} | "
                  f"Alertas: {self.total_alerts} | Modelo: {self.detector.name}")
        cv2.rectangle(out, (0, 0), (w, 26), (18, 20, 23), -1)
        cv2.putText(out, banner, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (236, 234, 233), 1, cv2.LINE_AA)
        return out

    def _store_snapshot(self, frame: np.ndarray, tracks: List[Track],
                        wall: datetime) -> str:
        try:
            name = f"s{self.session_id}_{wall.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
            path = SNAPSHOT_DIR / name
            img = self.annotate(frame, tracks)
            cv2.imwrite(str(path), img,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(CONFIG.get("jpeg_quality"))])
            return f"snapshots/{name}"
        except Exception as exc:  # pragma: no cover
            log.warning("No se pudo guardar snapshot: %s", exc)
            return ""

    # ------------------------------------------------------------------
    def finalize(self) -> Dict[str, Any]:
        with self.lock:
            now = self._clock(self.last_result.get("video_ts"))
            open_tracks = [t for t in self.tracker.tracks.values() if not t.closed]
            self.zones.flush_open_dwell(open_tracks, now)
            for tr in self.tracker.close_all():
                self._save_track(tr)
            metrics = self.metrics()
            metrics["zones"] = self.zones.snapshot()
            return metrics


def _hex_to_bgr(value: str) -> Tuple[int, int, int]:
    value = (value or "#1a73e8").lstrip("#")
    if len(value) != 6:
        value = "7d97b8"
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return (b, g, r)

"""Seguimiento multi-objeto ligero (IoU + centroides).

Se implementa aqui en lugar de usar el tracker del modelo para que el mismo
seguimiento funcione con cualquier backend (YOLO, ONNX o movimiento) y para
controlar el ciclo de vida de cada track: es lo que permite medir permanencia,
trayectoria y conteos por zona sin identificar a nadie (IDs anonimos).
"""
from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .detector import Detection


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    key: str
    label: str
    bbox: Tuple[float, float, float, float]
    conf: float
    first_ts: str
    first_mono: float
    last_mono: float
    first_video_ts: Optional[float] = None
    last_video_ts: Optional[float] = None
    hits: int = 1
    misses: int = 0
    frames: int = 1
    conf_sum: float = 0.0
    distance_px: float = 0.0
    confirmed: bool = False
    closed: bool = False
    history: deque = field(default_factory=lambda: deque(maxlen=240))
    zones: Dict[str, float] = field(default_factory=dict)       # zona -> segundos
    zone_since: Dict[str, float] = field(default_factory=dict)  # zona -> t entrada
    zone_alerted: Set[str] = field(default_factory=set)
    current_zones: Set[str] = field(default_factory=set)

    @property
    def centroid(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def anchor(self) -> Tuple[float, float]:
        x1, _, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, y2)

    @property
    def duration(self) -> float:
        return max(0.0, self.last_mono - self.first_mono)

    @property
    def avg_conf(self) -> float:
        return self.conf_sum / self.frames if self.frames else 0.0

    def as_dict(self, width: int = 1, height: int = 1) -> Dict[str, object]:
        x1, y1, x2, y2 = self.bbox
        return {
            "key": self.key,
            "label": self.label,
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "norm": [round(x1 / width, 4), round(y1 / height, 4),
                     round(x2 / width, 4), round(y2 / height, 4)],
            "conf": round(self.conf, 3),
            "duration": round(self.duration, 1),
            "zones": sorted(self.current_zones),
            "dwell": {z: round(s, 1) for z, s in self.zones.items()},
        }


class Tracker:
    """Asociacion por IoU con ventana de tolerancia (max_age)."""

    def __init__(self, session_tag: str, iou_threshold: float = 0.3,
                 max_age: int = 30, min_hits: int = 3):
        self.session_tag = session_tag
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits
        self.tracks: Dict[str, Track] = {}
        self._counter = itertools.count(1)
        self.total_created = 0

    def _new_key(self) -> str:
        n = next(self._counter)
        self.total_created += 1
        return f"{self.session_tag}-{n:04d}"

    def update(self, detections: List[Detection], now: float, wall_ts: str,
               video_ts: Optional[float], width: int, height: int
               ) -> Tuple[List[Track], List[Track]]:
        """Devuelve (tracks activos confirmados, tracks cerrados en este frame)."""
        unmatched_dets = list(range(len(detections)))
        live_keys = [k for k, t in self.tracks.items() if not t.closed]

        # --- emparejamiento greedy por IoU, solo entre misma clase -----------
        pairs = []
        for ti, key in enumerate(live_keys):
            tr = self.tracks[key]
            for di in unmatched_dets:
                det = detections[di]
                if det.label != tr.label:
                    continue
                score = iou(tr.bbox, det.bbox)
                if score >= self.iou_threshold:
                    pairs.append((score, key, di))
        pairs.sort(reverse=True)
        used_tracks: Set[str] = set()
        used_dets: Set[int] = set()
        for score, key, di in pairs:
            if key in used_tracks or di in used_dets:
                continue
            used_tracks.add(key)
            used_dets.add(di)
            self._update_track(self.tracks[key], detections[di], now, video_ts, width, height)

        # --- detecciones sin track -> nuevos tracks --------------------------
        for di, det in enumerate(detections):
            if di in used_dets:
                continue
            key = self._new_key()
            tr = Track(
                key=key, label=det.label, bbox=det.bbox, conf=det.conf,
                first_ts=wall_ts, first_mono=now, last_mono=now,
                first_video_ts=video_ts, last_video_ts=video_ts,
                conf_sum=det.conf,
            )
            cx, cy = det.anchor
            tr.history.append((round(cx / max(width, 1), 4), round(cy / max(height, 1), 4)))
            tr.confirmed = self.min_hits <= 1
            self.tracks[key] = tr

        # --- envejecimiento y cierre ----------------------------------------
        closed: List[Track] = []
        for key, tr in list(self.tracks.items()):
            if tr.closed:
                continue
            if key in used_tracks:
                continue
            tr.misses += 1
            if tr.misses > self.max_age:
                tr.closed = True
                closed.append(tr)

        active = [t for t in self.tracks.values()
                  if not t.closed and t.confirmed and t.misses == 0]
        return active, closed

    def _update_track(self, tr: Track, det: Detection, now: float,
                      video_ts: Optional[float], width: int, height: int) -> None:
        prev_cx, prev_cy = tr.anchor
        tr.bbox = det.bbox
        tr.conf = det.conf
        tr.conf_sum += det.conf
        tr.frames += 1
        tr.hits += 1
        tr.misses = 0
        tr.last_mono = now
        tr.last_video_ts = video_ts
        cx, cy = det.anchor
        tr.distance_px += ((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2) ** 0.5
        tr.history.append((round(cx / max(width, 1), 4), round(cy / max(height, 1), 4)))
        if not tr.confirmed and tr.hits >= self.min_hits:
            tr.confirmed = True

    def close_all(self) -> List[Track]:
        out = []
        for tr in self.tracks.values():
            if not tr.closed:
                tr.closed = True
                out.append(tr)
        return out

    @property
    def active_count(self) -> int:
        return sum(1 for t in self.tracks.values()
                   if not t.closed and t.confirmed and t.misses == 0)

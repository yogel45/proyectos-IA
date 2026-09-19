"""Configuracion central de OfficeVision AI.

La configuracion vive en `config.json` (se crea con valores por defecto en el
primer arranque). Todo el sistema lee de aqui: rutas, parametros del detector,
frecuencia de analisis, reglas de alerta y horario laboral.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
MODELS_DIR = BASE_DIR / "models"
SAMPLE_DIR = BASE_DIR / "sample_data"
DB_PATH = DATA_DIR / "officevision.db"
CONFIG_PATH = BASE_DIR / "config.json"

for _d in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR, SNAPSHOT_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULTS: Dict[str, Any] = {
    # ---------------- Vision por computadora ----------------
    "detector": "auto",              # auto | yolo | onnx | motion
    "model": "yolo11n.pt",           # modelo YOLO (se descarga solo la 1a vez)
    "onnx_model": "",                # ruta a un .onnx propio (opcional)
    "imgsz": 640,
    "conf_threshold": 0.35,
    "iou_threshold": 0.5,
    "device": "cpu",                 # cpu | 0 (gpu) | cuda
    "classes": ["person", "laptop", "cell phone", "chair", "backpack", "handbag", "cup", "book", "tv"],
    "primary_class": "person",

    # ---------------- Tracking ----------------
    "track_max_age": 30,             # frames sin match antes de cerrar el track
    "track_min_hits": 3,             # frames para confirmar un track
    "track_iou_match": 0.3,

    # ---------------- Frecuencia de analisis ----------------
    "live_target_fps": 6.0,          # fps analizados de la camara en vivo
    "video_target_fps": 6.0,         # fps analizados en videos subidos
    "snapshot_interval_s": 5.0,      # cada cuanto se escribe una foto de estado
    "summary_interval_s": 60.0,      # cada cuanto se escribe un resumen narrado
    "max_concurrent_jobs": 2,

    # ---------------- Reglas / puntos criticos ----------------
    "default_dwell_alert_s": 180,    # permanencia excesiva por defecto
    "default_max_occupancy": 6,      # aforo por defecto
    "idle_zone_alert_s": 900,        # zona critica sin actividad en horario laboral
    "crowd_threshold": 8,            # personas simultaneas = aglomeracion
    "min_track_seconds": 1.0,        # tracks mas cortos se descartan como ruido
    "track_objects": True,           # seguir tambien objetos, no solo personas
    "object_warmup_frames": 25,      # cuadros antes de avisar "objeto nuevo"
    "unattended_alert_s": 120,       # objeto de valor sin persona cerca
    "unattended_radius": 0.22,       # radio (proporcion de la diagonal) de "cerca"
    "valuable_classes": ["laptop", "cell phone", "backpack", "handbag", "suitcase"],

    # ---------------- Horario laboral (para contexto de alertas) --------------
    "work_start": "07:00",
    "work_end": "18:00",
    "work_days": [0, 1, 2, 3, 4, 5],  # 0=lunes ... 5=sabado
    "timezone_label": "local",

    # ---------------- Privacidad ----------------
    "blur_faces": True,              # difumina la parte superior del bbox
    "store_snapshots": True,         # guarda JPG solo en eventos criticos
    "snapshot_retention_days": 15,
    "anonymous_ids": True,           # nunca se guarda identidad biometrica

    # ---------------- Salidas ----------------
    "render_annotated_video": True,
    "jpeg_quality": 70,
}


class Config:
    """Diccionario de configuracion persistente y seguro entre hilos."""

    def __init__(self, path: Path = CONFIG_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    stored = json.loads(self._path.read_text(encoding="utf-8"))
                    if isinstance(stored, dict):
                        self._data.update(stored)
                except (json.JSONDecodeError, OSError):
                    pass
            else:
                self.save()

    def save(self) -> None:
        with self._lock:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def update(self, values: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for k, v in values.items():
                if k in DEFAULTS:
                    self._data[k] = v
        self.save()
        return self.as_dict()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def __getitem__(self, key: str) -> Any:
        return self.get(key)


CONFIG = Config()

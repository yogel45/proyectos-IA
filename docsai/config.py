"""Configuracion de DocuFlow AI.

Vive en `config_documentos.json`, separada de la del modulo de video: cada
aplicacion se configura y se despliega por su cuenta.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "documentos"
ENTRADA_DIR = DATA_DIR / "entrada"
ORGANIZADOS_DIR = DATA_DIR / "organizados"
DB_PATH = DATA_DIR / "documentos.db"
CONFIG_PATH = BASE_DIR / "config_documentos.json"

for _d in (DATA_DIR, ENTRADA_DIR, ORGANIZADOS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

DEFAULTS: Dict[str, Any] = {
    # ---------------- Nombramiento ----------------
    "plantilla_nombre": "{fecha}_{categoria}_{expediente}_{descriptor}",
    "separador": "_",
    "max_nombre": 120,
    "esquema_carpetas": "categoria_anio",  # categoria_anio | expediente | anio_mes | categoria | plano

    # ---------------- Clasificacion ----------------
    "umbral_revision": 0.55,     # confianza minima para archivar sin revisar
    "min_ejemplos_modelo": 6,    # correcciones necesarias para activar el modelo

    # ---------------- Procesamiento ----------------
    "conservar_original": True,  # copiar en vez de mover
    "max_trabajos": 3,
    "guardar_texto": True,       # guardar el texto extraido para busquedas
    "ocr_idiomas": "spa+eng",
}


class Config:
    """Diccionario persistente y seguro entre hilos."""

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
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

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


CONFIG = Config()

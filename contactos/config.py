"""Configuracion de Directorio vivo."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "contactos"
DB_PATH = DATA_DIR / "contactos.db"
CONFIG_PATH = BASE_DIR / "config_contactos.json"
SAMPLE_DIR = BASE_DIR / "sample_data"

# Fuentes externas de las que se alimenta el directorio
DOCS_DB = BASE_DIR / "data" / "documentos" / "documentos.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULTS: Dict[str, Any] = {
    # ---------------- Duplicados ----------------
    "umbral_duplicado": 0.75,        # confianza minima para proponer una fusion
    "fusion_automatica": False,      # nunca fusionar sin que alguien lo acepte

    # ---------------- Importacion ----------------
    # Un numero entra al directorio cuando hay senal de relacion sostenida:
    # llamo mas de una vez, o acumulo una conversacion larga. El resto queda
    # como historial buscable por numero, sin ensuciar el directorio.
    "llamadas_min_veces": 2,             # llamadas del mismo numero
    "llamadas_min_segundos_total": 900,  # o conversacion acumulada (15 min)
    "crear_desde_llamadas": True,
    "crear_desde_documentos": True,

    # ---------------- Presentacion ----------------
    "hitos_por_ficha": 40,
    "resultados_busqueda": 25,
}


class Config:
    def __init__(self, path: Path = CONFIG_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    guardado = json.loads(self._path.read_text(encoding="utf-8"))
                    if isinstance(guardado, dict):
                        self._data.update(guardado)
                except (json.JSONDecodeError, OSError):
                    pass
            else:
                self.save()

    def save(self) -> None:
        with self._lock:
            self._path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def update(self, valores: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            for k, v in valores.items():
                if k in DEFAULTS:
                    self._data[k] = v
        self.save()
        return self.as_dict()

    def as_dict(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)


CONFIG = Config()

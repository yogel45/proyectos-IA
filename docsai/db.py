"""Base de datos propia de DocuFlow AI (SQLite en data/documentos/documentos.db)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .config import DB_PATH

_LOCK = threading.RLock()
_CONN: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_original   TEXT NOT NULL,
    nombre_propuesto  TEXT NOT NULL,
    nombre_final      TEXT,
    ruta_origen       TEXT NOT NULL,
    ruta_archivada    TEXT,
    carpeta           TEXT,
    extension         TEXT,
    bytes             INTEGER DEFAULT 0,
    hash_sha256       TEXT,
    duplicado_de      INTEGER,
    categoria         TEXT NOT NULL,
    categoria_nombre  TEXT,
    confianza         REAL DEFAULT 0,
    metodo            TEXT,
    motivo            TEXT,
    evidencia_json    TEXT DEFAULT '[]',
    puntajes_json     TEXT DEFAULT '{}',
    entidades_json    TEXT DEFAULT '{}',
    expediente        TEXT,
    fecha_doc         TEXT,
    titulo            TEXT,
    paginas           INTEGER DEFAULT 0,
    caracteres        INTEGER DEFAULT 0,
    idioma            TEXT,
    metodo_extraccion TEXT,
    requiere_ocr      INTEGER DEFAULT 0,
    texto             TEXT,
    estado            TEXT NOT NULL DEFAULT 'procesado',
    corregido         INTEGER DEFAULT 0,
    error             TEXT,
    creado            TEXT NOT NULL,
    actualizado       TEXT
);
CREATE INDEX IF NOT EXISTS idx_doc_estado ON documentos(estado);
CREATE INDEX IF NOT EXISTS idx_doc_categoria ON documentos(categoria);
CREATE INDEX IF NOT EXISTS idx_doc_expediente ON documentos(expediente);
CREATE INDEX IF NOT EXISTS idx_doc_hash ON documentos(hash_sha256);

CREATE TABLE IF NOT EXISTS doc_entrenamiento (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id  INTEGER,
    categoria     TEXT NOT NULL,
    texto         TEXT NOT NULL,
    creado        TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONN = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
            _CONN.row_factory = sqlite3.Row
            _CONN.execute("PRAGMA journal_mode=WAL")
            _CONN.execute("PRAGMA synchronous=NORMAL")
        return _CONN


@contextmanager
def cursor():
    conn = get_conn()
    with _LOCK:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def init_db() -> None:
    conn = get_conn()
    with _LOCK:
        conn.executescript(SCHEMA)
        conn.commit()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    filas = query(sql, params)
    return filas[0] if filas else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.lastrowid or 0

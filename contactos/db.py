"""Base de datos de Directorio vivo.

El modelo separa tres cosas que las libretas de contactos mezclan:

  * **persona**: quien es, con un solo nombre;
  * **identificador**: cada telefono, correo o extension por el que se le puede
    encontrar (una persona tiene varios y cambian con el tiempo);
  * **interaccion**: lo que ha pasado con ella, que es lo que no envejece.

Y anade lo que ninguna libreta tiene: **participacion**, el papel de una persona
dentro de un expediente.
"""
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
CREATE TABLE IF NOT EXISTS personas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT NOT NULL,
    nombre_norm   TEXT NOT NULL,
    organizacion  TEXT,
    rol           TEXT,
    lugar         TEXT,
    notas         TEXT,
    origen        TEXT,                -- manual | llamadas | documentos | nomina
    interno       INTEGER DEFAULT 0,   -- personal del despacho
    activo        INTEGER DEFAULT 1,
    fusionada_en  INTEGER,
    creado        TEXT NOT NULL,
    actualizado   TEXT
);
CREATE INDEX IF NOT EXISTS idx_per_norm ON personas(nombre_norm);
CREATE INDEX IF NOT EXISTS idx_per_activo ON personas(activo);

CREATE TABLE IF NOT EXISTS identificadores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id  INTEGER NOT NULL REFERENCES personas(id),
    tipo        TEXT NOT NULL,         -- telefono | correo | extension
    valor       TEXT NOT NULL,
    valor_norm  TEXT NOT NULL,
    etiqueta    TEXT,
    origen      TEXT,
    creado      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ident_norm ON identificadores(valor_norm);
CREATE INDEX IF NOT EXISTS idx_ident_persona ON identificadores(persona_id);

CREATE TABLE IF NOT EXISTS casos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente  TEXT UNIQUE,
    nombre      TEXT,
    tribunal    TEXT,
    estado      TEXT DEFAULT 'abierto',
    monto       REAL,
    documentos  INTEGER DEFAULT 0,
    desde       TEXT,
    hasta       TEXT,
    creado      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participaciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id  INTEGER NOT NULL REFERENCES personas(id),
    caso_id     INTEGER NOT NULL REFERENCES casos(id),
    rol         TEXT,
    origen      TEXT,                  -- de donde salio el rol
    confianza   REAL DEFAULT 1.0,
    creado      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_part_unica ON participaciones(persona_id, caso_id);

CREATE TABLE IF NOT EXISTS interacciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id  INTEGER REFERENCES personas(id),
    caso_id     INTEGER REFERENCES casos(id),
    tipo        TEXT NOT NULL,         -- llamada | documento | hecho | nota
    ts          TEXT NOT NULL,
    titulo      TEXT NOT NULL,
    detalle     TEXT,
    origen      TEXT,
    referencia  TEXT,                  -- clave en la fuente, para no duplicar
    meta_json   TEXT DEFAULT '{}',
    creado      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_int_persona ON interacciones(persona_id, ts);
CREATE INDEX IF NOT EXISTS idx_int_caso ON interacciones(caso_id, ts);
CREATE UNIQUE INDEX IF NOT EXISTS idx_int_ref ON interacciones(tipo, referencia, persona_id);

CREATE TABLE IF NOT EXISTS fusiones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    principal_id  INTEGER NOT NULL,
    absorbida_id  INTEGER NOT NULL,
    motivos_json  TEXT NOT NULL DEFAULT '[]',
    confianza     REAL DEFAULT 0,
    movido_json   TEXT NOT NULL DEFAULT '{}',   -- que se movio, para deshacer
    deshecha      INTEGER DEFAULT 0,
    ts            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS descartes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    a_id      INTEGER NOT NULL,
    b_id      INTEGER NOT NULL,
    ts        TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_descarte ON descartes(a_id, b_id);

CREATE TABLE IF NOT EXISTS importaciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fuente      TEXT NOT NULL,
    detalle     TEXT,
    creados     INTEGER DEFAULT 0,
    actualizados INTEGER DEFAULT 0,
    interacciones INTEGER DEFAULT 0,
    ts          TEXT NOT NULL
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
            _CONN.execute("PRAGMA foreign_keys=ON")
        return _CONN


def cerrar() -> None:
    """Suelta la conexion; la siguiente llamada abre una nueva."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None


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


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    with cursor() as cur:
        cur.executemany(sql, [tuple(s) for s in seq])

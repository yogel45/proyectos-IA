"""Capa de persistencia (SQLite).

Se usa SQLite en modo WAL: cero infraestructura para correr la app, pero con
esquema relacional real y consultas de agregacion que alimentan el dashboard.
El acceso esta serializado con un lock porque los hilos de analisis escriben
en paralelo (camara en vivo + N videos en proceso).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .config import DB_PATH

_LOCK = threading.RLock()
_CONN: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,              -- live | video
    path        TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER REFERENCES sources(id),
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL,          -- live | video
    status          TEXT NOT NULL,          -- running | done | error | canceled
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    frames_seen     INTEGER DEFAULT 0,
    frames_analyzed INTEGER DEFAULT 0,
    duration_s      REAL DEFAULT 0,
    progress        REAL DEFAULT 0,
    detector        TEXT,
    meta_json       TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    ts              TEXT NOT NULL,          -- reloj de pared
    video_ts        REAL,                   -- segundos dentro del video
    persons         INTEGER DEFAULT 0,
    objects         INTEGER DEFAULT 0,
    movement_index  REAL DEFAULT 0,
    fps             REAL DEFAULT 0,
    zones_json      TEXT DEFAULT '{}',
    classes_json    TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_snap_session_ts ON snapshots(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);

CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    track_key       TEXT NOT NULL,          -- anonimo: P-<session>-<n>
    label           TEXT NOT NULL,
    first_ts        TEXT NOT NULL,
    last_ts         TEXT NOT NULL,
    first_video_ts  REAL,
    last_video_ts   REAL,
    duration_s      REAL DEFAULT 0,
    frames          INTEGER DEFAULT 0,
    avg_conf        REAL DEFAULT 0,
    distance_px     REAL DEFAULT 0,
    zones_json      TEXT DEFAULT '{}',      -- {zona: segundos}
    path_json       TEXT DEFAULT '[]'       -- trayectoria muestreada (normalizada)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_track_unique ON tracks(session_id, track_key);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    ts          TEXT NOT NULL,
    video_ts    REAL,
    type        TEXT NOT NULL,              -- zone_enter, zone_exit, dwell, aforo, ...
    severity    TEXT NOT NULL DEFAULT 'info', -- info | warning | critical
    track_key   TEXT,
    zone        TEXT,
    message     TEXT NOT NULL,
    snapshot    TEXT,
    meta_json   TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

CREATE TABLE IF NOT EXISTS zones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    kind            TEXT NOT NULL DEFAULT 'area',  -- area | acceso | restringida
    polygon_json    TEXT NOT NULL,          -- [[x,y], ...] normalizado 0..1
    color           TEXT DEFAULT '#7d97b8',
    max_occupancy   INTEGER DEFAULT 6,
    dwell_alert_s   INTEGER DEFAULT 180,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id      TEXT UNIQUE,
    name        TEXT NOT NULL,
    area        TEXT,
    entry_time  TEXT,
    lunch       TEXT,
    exit_time   TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id      TEXT,
    name        TEXT,
    date        TEXT NOT NULL,
    check_in    TEXT,
    check_out   TEXT,
    worked_min  REAL,
    late_min    REAL,
    early_min   REAL,
    month       TEXT
);
CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_att_unique ON attendance(emp_id, date);

CREATE TABLE IF NOT EXISTS calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT,
    date        TEXT,
    hour        INTEGER,
    direction   TEXT,
    from_num    TEXT,
    to_num      TEXT,
    extension   TEXT,
    ext_id      TEXT,
    agent       TEXT,
    result      TEXT,
    duration_s  INTEGER,
    week        TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_date ON calls(date);
CREATE INDEX IF NOT EXISTS idx_calls_hour ON calls(hour);
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
    seed_default_zones()
    migrate_zone_colors()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def query(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.lastrowid or 0


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    with cursor() as cur:
        cur.executemany(sql, [tuple(s) for s in seq])


# --------------------------------------------------------------------------
# Helpers de dominio
# --------------------------------------------------------------------------
def create_source(name: str, kind: str, path: str = "") -> int:
    return execute(
        "INSERT INTO sources (name, kind, path, created_at) VALUES (?,?,?,?)",
        (name, kind, path, now_iso()),
    )


def create_session(source_id: int, name: str, kind: str, detector: str,
                   meta: Optional[Dict[str, Any]] = None) -> int:
    return execute(
        """INSERT INTO sessions (source_id, name, kind, status, started_at, detector, meta_json)
           VALUES (?,?,?,'running',?,?,?)""",
        (source_id, name, kind, now_iso(), detector, json.dumps(meta or {}, ensure_ascii=False)),
    )


def update_session(session_id: int, **fields: Any) -> None:
    if not fields:
        return
    if "meta" in fields:
        fields["meta_json"] = json.dumps(fields.pop("meta"), ensure_ascii=False)
    cols = ", ".join(f"{k}=?" for k in fields)
    execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))


def close_session(session_id: int, status: str = "done") -> None:
    execute(
        "UPDATE sessions SET status=?, ended_at=?, progress=100 WHERE id=?",
        (status, now_iso(), session_id),
    )


def insert_snapshot(session_id: int, ts: str, video_ts: Optional[float], persons: int,
                    objects: int, movement: float, fps: float,
                    zones: Dict[str, Any], classes: Dict[str, int]) -> None:
    execute(
        """INSERT INTO snapshots (session_id, ts, video_ts, persons, objects, movement_index,
                                  fps, zones_json, classes_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, ts, video_ts, persons, objects, movement, fps,
         json.dumps(zones, ensure_ascii=False), json.dumps(classes, ensure_ascii=False)),
    )


def upsert_track(session_id: int, track_key: str, label: str, first_ts: str, last_ts: str,
                 first_video_ts: Optional[float], last_video_ts: Optional[float],
                 duration_s: float, frames: int, avg_conf: float, distance_px: float,
                 zones: Dict[str, float], path: List[List[float]]) -> None:
    execute(
        """INSERT INTO tracks (session_id, track_key, label, first_ts, last_ts, first_video_ts,
                               last_video_ts, duration_s, frames, avg_conf, distance_px,
                               zones_json, path_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(session_id, track_key) DO UPDATE SET
               last_ts=excluded.last_ts,
               last_video_ts=excluded.last_video_ts,
               duration_s=excluded.duration_s,
               frames=excluded.frames,
               avg_conf=excluded.avg_conf,
               distance_px=excluded.distance_px,
               zones_json=excluded.zones_json,
               path_json=excluded.path_json""",
        (session_id, track_key, label, first_ts, last_ts, first_video_ts, last_video_ts,
         duration_s, frames, avg_conf, distance_px,
         json.dumps(zones, ensure_ascii=False), json.dumps(path)),
    )


def insert_event(session_id: Optional[int], ts: str, type_: str, message: str,
                 severity: str = "info", track_key: str = "", zone: str = "",
                 video_ts: Optional[float] = None, snapshot: str = "",
                 meta: Optional[Dict[str, Any]] = None) -> int:
    return execute(
        """INSERT INTO events (session_id, ts, video_ts, type, severity, track_key, zone,
                               message, snapshot, meta_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (session_id, ts, video_ts, type_, severity, track_key, zone, message, snapshot,
         json.dumps(meta or {}, ensure_ascii=False)),
    )


DEFAULT_ZONES = [
    # Rejilla inicial util para una camara de oficina; editable desde la UI.
    ("Recepcion", "acceso", [[0.02, 0.45], [0.33, 0.45], [0.33, 0.97], [0.02, 0.97]], "#7d97b8", 4, 300),
    ("Area de trabajo", "area", [[0.34, 0.35], [0.74, 0.35], [0.74, 0.97], [0.34, 0.97]], "#839a8c", 10, 3600),
    ("Sala de juntas", "area", [[0.75, 0.30], [0.98, 0.30], [0.98, 0.97], [0.75, 0.97]], "#a89578", 8, 5400),
    ("Pasillo / Acceso", "acceso", [[0.02, 0.05], [0.98, 0.05], [0.98, 0.34], [0.02, 0.34]], "#8a8698", 6, 120),
]

# Colores vivos de la primera version -> equivalentes apagados. Solo se
# reemplazan los que nadie ha tocado, para no pisar elecciones del usuario.
COLOR_MIGRACION = {
    # paleta viva original
    "#38bdf8": "#7d97b8", "#22c55e": "#839a8c",
    "#f59e0b": "#a89578", "#a78bfa": "#8a8698",
    # primer ajuste de saturacion -> paleta definitiva
    "#7fa48c": "#839a8c", "#b09562": "#a89578", "#8b84a3": "#8a8698",
    "#6f9b9b": "#7d9495", "#b0736f": "#a87b77",
}


def migrate_zone_colors() -> None:
    for viejo, nuevo in COLOR_MIGRACION.items():
        execute("UPDATE zones SET color=? WHERE color=?", (nuevo, viejo))


def seed_default_zones() -> None:
    existing = query_one("SELECT COUNT(*) AS n FROM zones")
    if existing and existing["n"]:
        return
    for name, kind, poly, color, cap, dwell in DEFAULT_ZONES:
        execute(
            """INSERT OR IGNORE INTO zones (name, kind, polygon_json, color, max_occupancy,
                                            dwell_alert_s, enabled, created_at)
               VALUES (?,?,?,?,?,?,1,?)""",
            (name, kind, json.dumps(poly), color, cap, dwell, now_iso()),
        )

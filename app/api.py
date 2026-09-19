"""API REST + WebSockets de OfficeVision AI."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import business, db
from .config import CONFIG, SAMPLE_DIR, UPLOAD_DIR
from .vision import autozones
from .vision.detector import available_backends
from .vision.zones import load_zones
from .workers import JOBS, LIVE, SERVER_CAMERA

log = logging.getLogger("officevision.api")
router = APIRouter(prefix="/api")

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv"}


# ==========================================================================
# Estado del sistema
# ==========================================================================
@router.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "ts": db.now_iso()}


@router.get("/system")
def system() -> Dict[str, Any]:
    backends = available_backends()
    active = None
    for s in LIVE.active():
        active = s
        break
    counts = db.query_one(
        """SELECT (SELECT COUNT(*) FROM sessions) sesiones,
                  (SELECT COUNT(*) FROM events) eventos,
                  (SELECT COUNT(*) FROM snapshots) snapshots,
                  (SELECT COUNT(*) FROM tracks) tracks,
                  (SELECT COUNT(*) FROM zones WHERE enabled=1) zonas,
                  (SELECT COUNT(*) FROM attendance) marcajes,
                  (SELECT COUNT(*) FROM calls) llamadas""") or {}
    return {
        "backends": backends,
        "detector_config": CONFIG.get("detector"),
        "model": CONFIG.get("model"),
        "opencv": cv2.__version__,
        "live_sessions": LIVE.active(),
        "server_camera": {"running": SERVER_CAMERA.running,
                          "error": SERVER_CAMERA.error},
        "jobs_running": sum(1 for j in JOBS.jobs.values() if j.status == "running"),
        "counts": counts,
        "active": active,
    }


@router.get("/classes")
def list_classes() -> Dict[str, Any]:
    """Clases que el modelo puede reconocer y cuales estan activas."""
    from .vision.detector import COCO_CLASSES
    utiles = ["person", "laptop", "cell phone", "chair", "tv", "keyboard", "mouse",
              "backpack", "handbag", "suitcase", "cup", "bottle", "book",
              "dining table", "couch", "potted plant", "clock", "scissors",
              "umbrella", "refrigerator", "microwave", "sink", "tie"]
    return {"activas": CONFIG.get("classes"), "sugeridas": utiles,
            "todas": COCO_CLASSES, "primaria": CONFIG.get("primary_class")}


@router.get("/config")
def get_config() -> Dict[str, Any]:
    return CONFIG.as_dict()


@router.post("/config")
async def set_config(request: Request) -> Dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "Se espera un objeto JSON")
    return CONFIG.update(payload)


# ==========================================================================
# Zonas (puntos criticos)
# ==========================================================================
@router.get("/zones")
def get_zones() -> List[Dict[str, Any]]:
    return db.query("SELECT * FROM zones ORDER BY id")


@router.post("/zones")
async def create_zone(request: Request) -> Dict[str, Any]:
    data = await request.json()
    name = (data.get("name") or "").strip()
    polygon = data.get("polygon") or []
    if not name:
        raise HTTPException(400, "La zona necesita un nombre")
    if len(polygon) < 3:
        raise HTTPException(400, "El poligono necesita al menos 3 puntos")
    zone_id = db.execute(
        """INSERT INTO zones (name, kind, polygon_json, color, max_occupancy,
                              dwell_alert_s, enabled, created_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(name) DO UPDATE SET
             kind=excluded.kind, polygon_json=excluded.polygon_json,
             color=excluded.color, max_occupancy=excluded.max_occupancy,
             dwell_alert_s=excluded.dwell_alert_s, enabled=excluded.enabled""",
        (name, data.get("kind", "area"), json.dumps(polygon),
         data.get("color", "#7d97b8"),
         int(data.get("max_occupancy", CONFIG.get("default_max_occupancy"))),
         int(data.get("dwell_alert_s", CONFIG.get("default_dwell_alert_s"))),
         1 if data.get("enabled", True) else 0, db.now_iso()))
    return {"id": zone_id, "ok": True}


@router.get("/zones/suggest")
async def suggest_zones(session_id: int = 0) -> Dict[str, Any]:
    """Propone zonas a partir de las trayectorias ya analizadas."""
    return await run_in_threadpool(autozones.suggest_from_activity,
                                   session_id or None)


@router.post("/zones/suggest-image")
async def suggest_zones_image(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Propone zonas a partir de una foto del espacio o de un cuadro de video."""
    data = await file.read()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in VIDEO_EXT:
        tmp = UPLOAD_DIR / f"_zonas_{uuid.uuid4().hex[:8]}{suffix}"
        tmp.write_bytes(data)
        frames = await run_in_threadpool(_muestrear_cuadros, tmp, 6)
        tmp.unlink(missing_ok=True)
        if not frames:
            raise HTTPException(400, "No se pudo leer el video")
        return await run_in_threadpool(autozones.suggest_from_frames, frames)
    frame = await run_in_threadpool(_decode_jpeg, data)
    if frame is None:
        raise HTTPException(400, "No se pudo leer la imagen")
    return await run_in_threadpool(autozones.suggest_from_image, frame)


def _muestrear_cuadros(path: Path, n: int = 6) -> List[np.ndarray]:
    """Toma n cuadros repartidos a lo largo del video."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    salida: List[np.ndarray] = []
    if total > n:
        for i in range(1, n + 1):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * i / (n + 1)))
            ok, frame = cap.read()
            if ok:
                salida.append(frame)
    else:
        while len(salida) < n:
            ok, frame = cap.read()
            if not ok:
                break
            salida.append(frame)
    cap.release()
    return salida


@router.post("/zones/apply")
async def apply_suggested_zones(request: Request) -> Dict[str, Any]:
    data = await request.json()
    zonas = data.get("zones") or []
    if not isinstance(zonas, list) or not zonas:
        raise HTTPException(400, "No se recibieron zonas para guardar")
    n = await run_in_threadpool(autozones.apply_zones, zonas,
                                bool(data.get("replace")))
    return {"ok": True, "guardadas": n}


@router.put("/zones/{zone_id}")
async def update_zone(zone_id: int, request: Request) -> Dict[str, Any]:
    data = await request.json()
    fields, values = [], []
    mapping = {"name": "name", "kind": "kind", "color": "color",
               "max_occupancy": "max_occupancy", "dwell_alert_s": "dwell_alert_s"}
    for key, col in mapping.items():
        if key in data:
            fields.append(f"{col}=?")
            values.append(data[key])
    if "polygon" in data:
        fields.append("polygon_json=?")
        values.append(json.dumps(data["polygon"]))
    if "enabled" in data:
        fields.append("enabled=?")
        values.append(1 if data["enabled"] else 0)
    if not fields:
        return {"ok": False, "message": "sin cambios"}
    values.append(zone_id)
    db.execute(f"UPDATE zones SET {', '.join(fields)} WHERE id=?", values)
    return {"ok": True}


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int) -> Dict[str, Any]:
    db.execute("DELETE FROM zones WHERE id=?", (zone_id,))
    return {"ok": True}


# ==========================================================================
# Camara en vivo (navegador -> WebSocket)
# ==========================================================================
async def live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    client_id = uuid.uuid4().hex[:10]
    session = None
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("text") is not None:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                action = data.get("type")
                if action == "start":
                    session = await run_in_threadpool(
                        LIVE.open, client_id, data.get("name") or "Camara PC")
                    await websocket.send_json({
                        "type": "started",
                        "session_id": session.session_id,
                        "detector": session.analyzer.detector.info(),
                        "zones": [z.as_dict() for z in session.analyzer.zones.zones],
                    })
                elif action == "stop":
                    metrics = await run_in_threadpool(LIVE.close, client_id)
                    session = None
                    await websocket.send_json({"type": "stopped", "metrics": metrics})
                elif action == "reload_zones" and session:
                    await run_in_threadpool(session.analyzer.zones.reload)
                    await websocket.send_json({
                        "type": "zones",
                        "zones": [z.as_dict() for z in session.analyzer.zones.zones]})
                elif action == "ping":
                    await websocket.send_json({"type": "pong", "ts": db.now_iso()})
                continue

            payload = message.get("bytes")
            if not payload:
                continue
            if session is None:
                session = await run_in_threadpool(LIVE.open, client_id, "Camara PC")
                await websocket.send_json({
                    "type": "started", "session_id": session.session_id,
                    "detector": session.analyzer.detector.info(),
                    "zones": [z.as_dict() for z in session.analyzer.zones.zones]})
            frame = await run_in_threadpool(_decode_jpeg, payload)
            if frame is None:
                continue
            result = await run_in_threadpool(session.process, frame)
            result["type"] = "frame"
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover
        log.exception("Error en websocket en vivo: %s", exc)
    finally:
        await run_in_threadpool(LIVE.close, client_id)


def _decode_jpeg(payload: bytes) -> Optional[np.ndarray]:
    buf = np.frombuffer(payload, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return frame


# ==========================================================================
# Camara conectada al servidor / camara IP
# ==========================================================================
@router.post("/camera/start")
async def camera_start(request: Request) -> Dict[str, Any]:
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    SERVER_CAMERA.source = data.get("source", 0)
    if isinstance(SERVER_CAMERA.source, str) and SERVER_CAMERA.source.isdigit():
        SERVER_CAMERA.source = int(SERVER_CAMERA.source)
    ok = await run_in_threadpool(SERVER_CAMERA.start)
    return {"ok": ok, "error": SERVER_CAMERA.error,
            "session_id": SERVER_CAMERA.session_id}


@router.post("/camera/stop")
async def camera_stop() -> Dict[str, Any]:
    metrics = await run_in_threadpool(SERVER_CAMERA.stop)
    return {"ok": True, "metrics": metrics}


@router.get("/camera/status")
def camera_status() -> Dict[str, Any]:
    return {"running": SERVER_CAMERA.running, "error": SERVER_CAMERA.error,
            "session_id": SERVER_CAMERA.session_id,
            "last": SERVER_CAMERA.last_result.get("metrics", {})}


@router.get("/camera/stream")
def camera_stream() -> StreamingResponse:
    def generator():
        boundary = b"--frame\r\n"
        while SERVER_CAMERA.running:
            jpeg = SERVER_CAMERA.last_jpeg
            if jpeg:
                yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.12)
    return StreamingResponse(generator(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


# ==========================================================================
# Videos subidos
# ==========================================================================
@router.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in VIDEO_EXT:
        raise HTTPException(400, f"Formato no soportado: {suffix}")
    safe = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{suffix}"
    dest = UPLOAD_DIR / safe
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    job = await run_in_threadpool(JOBS.submit, dest, file.filename or safe)
    return {"ok": True, "job": job.as_dict()}


@router.get("/jobs")
def list_jobs() -> List[Dict[str, Any]]:
    return JOBS.list()


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Trabajo no encontrado")
    return job.as_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    return {"ok": JOBS.cancel(job_id)}


# ==========================================================================
# Sesiones, eventos y metricas
# ==========================================================================
@router.get("/sessions")
def list_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    rows = db.query(
        """SELECT s.*, (SELECT COUNT(*) FROM events e WHERE e.session_id=s.id) eventos,
                  (SELECT COUNT(*) FROM tracks t WHERE t.session_id=s.id) personas
           FROM sessions s ORDER BY s.id DESC LIMIT ?""", (limit,))
    for r in rows:
        try:
            r["meta"] = json.loads(r.pop("meta_json") or "{}")
        except json.JSONDecodeError:
            r["meta"] = {}
    return rows


@router.get("/sessions/{session_id}")
def session_detail(session_id: int) -> Dict[str, Any]:
    row = db.query_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if not row:
        raise HTTPException(404, "Sesion no encontrada")
    row["meta"] = json.loads(row.pop("meta_json") or "{}")
    row["tracks"] = db.query(
        "SELECT * FROM tracks WHERE session_id=? ORDER BY duration_s DESC LIMIT 200",
        (session_id,))
    row["events"] = db.query(
        "SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT 300",
        (session_id,))
    row["timeline"] = db.query(
        """SELECT ts, video_ts, persons, movement_index, zones_json
           FROM snapshots WHERE session_id=? ORDER BY id""", (session_id,))
    return row


@router.get("/events")
def list_events(limit: int = 100, severity: str = "", type: str = "",
                session_id: int = 0, since_hours: int = 0,
                q: str = "") -> List[Dict[str, Any]]:
    sql = "SELECT * FROM events WHERE 1=1"
    params: List[Any] = []
    if severity:
        sql += " AND severity=?"
        params.append(severity)
    if type:
        sql += " AND type=?"
        params.append(type)
    if session_id:
        sql += " AND session_id=?"
        params.append(session_id)
    if since_hours:
        sql += " AND ts >= ?"
        params.append((datetime.now() - timedelta(hours=since_hours)).isoformat())
    if q:
        sql += " AND (message LIKE ? OR zone LIKE ? OR track_key LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 2000)))
    return db.query(sql, params)


@router.get("/tracks")
def list_tracks(session_id: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM tracks"
    params: List[Any] = []
    if session_id:
        sql += " WHERE session_id=?"
        params.append(session_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, params)


@router.get("/metrics/live")
def metrics_live() -> Dict[str, Any]:
    sessions = []
    for s in LIVE.sessions():
        sessions.append({"session_id": s.session_id, "frames": s.frames,
                         "last": s.analyzer.last_result.get("metrics", {}),
                         "persons": s.analyzer.last_result.get("persons", 0),
                         "zones": s.analyzer.zones.snapshot()})
    if SERVER_CAMERA.running and SERVER_CAMERA.analyzer:
        sessions.append({"session_id": SERVER_CAMERA.session_id,
                         "frames": SERVER_CAMERA.analyzer.frames_analyzed,
                         "last": SERVER_CAMERA.last_result.get("metrics", {}),
                         "persons": SERVER_CAMERA.last_result.get("persons", 0),
                         "zones": SERVER_CAMERA.analyzer.zones.snapshot()})
    return {"sessions": sessions, "ts": db.now_iso()}


@router.get("/metrics/summary")
def metrics_summary(hours: int = 24) -> Dict[str, Any]:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    kpis = db.query_one(
        """SELECT COUNT(*) muestras, ROUND(AVG(persons),2) ocupacion_prom,
                  MAX(persons) pico, ROUND(AVG(movement_index),3) movimiento
           FROM snapshots WHERE ts >= ?""", (since,)) or {}
    events = db.query_one(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN severity='warning' THEN 1 ELSE 0 END) warnings,
                  SUM(CASE WHEN severity='critical' THEN 1 ELSE 0 END) criticos
           FROM events WHERE ts >= ?""", (since,)) or {}
    tracks = db.query_one(
        """SELECT COUNT(*) personas, ROUND(AVG(duration_s),1) permanencia_prom,
                  ROUND(MAX(duration_s),1) permanencia_max
           FROM tracks WHERE last_ts >= ?""", (since,)) or {}
    series = db.query(
        """SELECT substr(ts,1,16) AS minuto, ROUND(AVG(persons),2) personas,
                  MAX(persons) pico, ROUND(AVG(movement_index),3) movimiento
           FROM snapshots WHERE ts >= ? GROUP BY minuto ORDER BY minuto""", (since,))
    by_hour = db.query(
        """SELECT substr(ts,12,2) AS hora, ROUND(AVG(persons),2) personas,
                  MAX(persons) pico
           FROM snapshots WHERE ts >= ? GROUP BY hora ORDER BY hora""", (since,))
    tipos = db.query(
        """SELECT type, COUNT(*) n FROM events WHERE ts >= ?
           GROUP BY type ORDER BY n DESC""", (since,))
    zonas = _zone_rollup(since)
    objetos = db.query(
        """SELECT label AS clase, COUNT(*) AS unicos,
                  ROUND(AVG(duration_s),1) AS permanencia_prom,
                  ROUND(MAX(duration_s),1) AS permanencia_max
           FROM tracks WHERE label <> 'person' AND last_ts >= ?
           GROUP BY label ORDER BY unicos DESC""", (since,))
    recientes = db.query(
        "SELECT * FROM events WHERE ts >= ? ORDER BY id DESC LIMIT 25", (since,))
    alertas = db.query(
        """SELECT * FROM events WHERE ts >= ? AND severity <> 'info'
           ORDER BY id DESC LIMIT 25""", (since,))
    sesiones = db.query(
        """SELECT id, name, kind, status, started_at, ended_at, frames_analyzed, progress
           FROM sessions ORDER BY id DESC LIMIT 10""")
    return {"rango_horas": hours, "kpis": kpis, "eventos": events, "tracks": tracks,
            "serie": series, "por_hora": by_hour, "tipos": tipos, "zonas": zonas,
            "objetos": objetos,
            "recientes": recientes, "alertas": alertas, "sesiones": sesiones,
            "en_vivo": metrics_live()}


def _zone_rollup(since: str) -> List[Dict[str, Any]]:
    rows = db.query(
        "SELECT zones_json FROM snapshots WHERE ts >= ? ORDER BY id DESC LIMIT 2000",
        (since,))
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        try:
            data = json.loads(r["zones_json"] or "{}")
        except json.JSONDecodeError:
            continue
        for name, info in data.items():
            a = agg.setdefault(name, {"ocupacion_sum": 0.0, "muestras": 0, "pico": 0,
                                      "entradas": 0, "permanencia": 0.0,
                                      "color": info.get("color", "#7d97b8"),
                                      "max_occupancy": info.get("max_occupancy", 0)})
            a["ocupacion_sum"] += float(info.get("occupancy", 0))
            a["muestras"] += 1
            a["pico"] = max(a["pico"], int(info.get("peak", 0)))
            a["entradas"] = max(a["entradas"], int(info.get("entries", 0)))
            a["permanencia"] = max(a["permanencia"], float(info.get("dwell_total_s", 0)))
    out = []
    for name, a in agg.items():
        out.append({
            "zona": name,
            "ocupacion_prom": round(a["ocupacion_sum"] / max(1, a["muestras"]), 2),
            "pico": a["pico"], "entradas": a["entradas"],
            "permanencia_total_min": round(a["permanencia"] / 60, 1),
            "color": a["color"], "max_occupancy": a["max_occupancy"],
        })
    return sorted(out, key=lambda r: r["ocupacion_prom"], reverse=True)


# ==========================================================================
# Exportacion
# ==========================================================================
def _csv_response(rows: List[Dict[str, Any]], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/export/events.csv")
def export_events(hours: int = 168) -> StreamingResponse:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = db.query("SELECT * FROM events WHERE ts >= ? ORDER BY id", (since,))
    return _csv_response(rows, "eventos.csv")


@router.get("/export/snapshots.csv")
def export_snapshots(hours: int = 168) -> StreamingResponse:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = db.query("SELECT * FROM snapshots WHERE ts >= ? ORDER BY id", (since,))
    return _csv_response(rows, "ocupacion.csv")


@router.get("/export/tracks.csv")
def export_tracks() -> StreamingResponse:
    rows = db.query("SELECT * FROM tracks ORDER BY id")
    return _csv_response(rows, "personas.csv")


@router.get("/export/operacion.csv")
def export_operacion(day: str = "") -> StreamingResponse:
    data = business.cross_analysis(day or None)
    return _csv_response(data["table"], "operacion.csv")


# ==========================================================================
# Datos operativos (biometrico + llamadas)
# ==========================================================================
@router.get("/business/summary")
def business_summary() -> Dict[str, Any]:
    return business.business_summary()


@router.get("/business/cross")
def business_cross(day: str = "", mode: str = "auto") -> Dict[str, Any]:
    return business.cross_analysis(day or None, mode)


@router.get("/business/calls")
def business_calls(day: str = "") -> List[Dict[str, Any]]:
    return business.calls_by_hour(day or None)


@router.get("/business/attendance")
def business_attendance(day: str = "", limit: int = 200) -> Dict[str, Any]:
    day = day or business.default_day() or ""
    rows = db.query(
        """SELECT a.name AS name, e.area AS area, a.check_in AS check_in,
                  a.check_out AS check_out,
                  ROUND(a.worked_min/60.0, 2) AS horas,
                  ROUND(a.late_min, 1) AS retraso_min
           FROM attendance a LEFT JOIN employees e ON e.emp_id = a.emp_id
           WHERE a.date = ? ORDER BY a.check_in LIMIT ?""", (day, limit))
    return {"day": day, "rows": rows, "por_hora": business.attendance_by_hour(day)}


@router.post("/business/import")
async def business_import(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(400, "Se esperaba un archivo .xlsx")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{file.filename}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    name = (file.filename or "").lower()
    if "ring" in name or "call" in name:
        result = await run_in_threadpool(business.import_calls, dest)
    else:
        result = await run_in_threadpool(business.import_biometric, dest)
    return {"ok": True, "archivo": file.filename, "resultado": result}


@router.post("/business/reload-samples")
async def business_reload() -> Dict[str, Any]:
    return await run_in_threadpool(business.import_samples, True)

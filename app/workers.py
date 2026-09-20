"""Orquestacion de fuentes de video.

Tres modos de entrada, todos alimentando el mismo `Analyzer`:
  * `LiveRegistry`  -> camara de la PC via navegador (frames por WebSocket).
  * `CameraStream`  -> camara conectada al servidor o camara IP/RTSP (MJPEG).
  * `JobManager`    -> videos subidos, procesados por lotes en segundo plano.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from . import db
from .config import CONFIG, OUTPUT_DIR
from .pipeline import Analyzer
from .vision.detector import build_detector
from .vision.zones import ZoneManager

log = logging.getLogger("officevision.workers")


# ==========================================================================
# Camara en vivo desde el navegador
# ==========================================================================
class LiveSession:
    def __init__(self, name: str = "Camara PC"):
        self.source_id = db.create_source(name, "live")
        detector = build_detector()
        self.session_id = db.create_session(self.source_id, name, "live", detector.name,
                                            {"origin": "browser"})
        self.analyzer = Analyzer(self.session_id, f"P{self.session_id}", "live",
                                 detector=detector, zone_manager=ZoneManager())
        self.started = time.monotonic()
        self.frames = 0
        self.closed = False

    def process(self, frame: np.ndarray) -> Dict[str, Any]:
        self.frames += 1
        result = self.analyzer.process(frame)
        if self.frames % 20 == 0:
            db.update_session(self.session_id, frames_seen=self.frames,
                              frames_analyzed=self.analyzer.frames_analyzed,
                              duration_s=round(time.monotonic() - self.started, 1))
        return result

    def close(self) -> Dict[str, Any]:
        if self.closed:
            return {}
        self.closed = True
        metrics = self.analyzer.finalize()
        db.update_session(self.session_id, frames_seen=self.frames,
                          frames_analyzed=self.analyzer.frames_analyzed,
                          duration_s=round(time.monotonic() - self.started, 1),
                          meta={"metrics": metrics})
        db.close_session(self.session_id, "done")
        return metrics


class LiveRegistry:
    def __init__(self) -> None:
        self._sessions: Dict[str, LiveSession] = {}
        self._lock = threading.Lock()

    def open(self, client_id: str, name: str = "Camara PC") -> LiveSession:
        with self._lock:
            self.close(client_id)
            session = LiveSession(name)
            self._sessions[client_id] = session
            return session

    def get(self, client_id: str) -> Optional[LiveSession]:
        return self._sessions.get(client_id)

    def close(self, client_id: str) -> Dict[str, Any]:
        session = self._sessions.pop(client_id, None)
        if session:
            try:
                return session.close()
            except Exception as exc:  # pragma: no cover
                log.warning("Error cerrando sesion en vivo: %s", exc)
        return {}

    def sessions(self) -> List["LiveSession"]:
        return [s for s in self._sessions.values() if not s.closed]

    def active(self) -> List[Dict[str, Any]]:
        return [
            {"client": cid, "session_id": s.session_id, "frames": s.frames,
             "persons": s.analyzer.last_result.get("persons", 0)}
            for cid, s in self._sessions.items() if not s.closed
        ]


# ==========================================================================
# Camara conectada al servidor (o camara IP / RTSP)
# ==========================================================================
class CameraStream:
    """Captura continua en un hilo; expone el ultimo frame anotado en JPEG."""

    def __init__(self, source: Any = 0, name: str = "Camara servidor"):
        self.source = int(source) if str(source).isdigit() else str(source)
        self.name = name
        self.cap: Optional[cv2.VideoCapture] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.session_id: Optional[int] = None
        self.analyzer: Optional[Analyzer] = None
        self.last_jpeg: Optional[bytes] = None
        self.last_result: Dict[str, Any] = {}
        self.error = ""
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return True
            self.cap = cv2.VideoCapture(self.source)
            if not self.cap or not self.cap.isOpened():
                self.error = f"No se pudo abrir la fuente {self.source!r}"
                return False
            source_id = db.create_source(self.name, "live", str(self.source))
            detector = build_detector()
            self.session_id = db.create_session(source_id, self.name, "live",
                                                detector.name, {"origin": "server"})
            self.analyzer = Analyzer(self.session_id, f"P{self.session_id}", "live",
                                     detector=detector)
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            return True

    def _loop(self) -> None:
        target = max(0.5, float(CONFIG.get("live_target_fps") or 6))
        interval = 1.0 / target
        quality = int(CONFIG.get("jpeg_quality") or 70)
        while self.running and self.cap is not None:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.2)
                continue
            t0 = time.monotonic()
            try:
                result = self.analyzer.process(frame)
                annotated = self.analyzer.annotate(
                    frame, [t for t in self.analyzer.tracker.tracks.values()
                            if t.confirmed and not t.closed and t.misses == 0])
                ok_enc, buf = cv2.imencode(".jpg", annotated,
                                           [int(cv2.IMWRITE_JPEG_QUALITY), quality])
                if ok_enc:
                    self.last_jpeg = buf.tobytes()
                self.last_result = result
            except Exception as exc:  # pragma: no cover
                log.exception("Error en camara servidor: %s", exc)
            time.sleep(max(0.0, interval - (time.monotonic() - t0)))

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        if self.cap:
            self.cap.release()
            self.cap = None
        metrics = {}
        if self.analyzer and self.session_id:
            metrics = self.analyzer.finalize()
            db.update_session(self.session_id, meta={"metrics": metrics})
            db.close_session(self.session_id, "done")
        self.analyzer = None
        self.session_id = None
        return metrics


# ==========================================================================
# Videos subidos
# ==========================================================================
@dataclass
class VideoJob:
    id: str
    path: Path
    name: str
    session_id: int = 0
    status: str = "queued"     # queued | running | done | error | canceled
    progress: float = 0.0
    message: str = ""
    fps: float = 0.0
    frames_total: int = 0
    frames_analyzed: int = 0
    duration_s: float = 0.0
    output: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""
    cancel: bool = False

    def as_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("path", "cancel")}
        d["path"] = str(self.path)
        return d


class JobManager:
    def __init__(self) -> None:
        workers = max(1, int(CONFIG.get("max_concurrent_jobs") or 2))
        self.pool = ThreadPoolExecutor(max_workers=workers,
                                       thread_name_prefix="videojob")
        self.jobs: Dict[str, VideoJob] = {}
        self._lock = threading.Lock()

    def submit(self, path: Path, name: str) -> VideoJob:
        job = VideoJob(id=uuid.uuid4().hex[:12], path=path, name=name)
        with self._lock:
            self.jobs[job.id] = job
        self.pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Optional[VideoJob]:
        return self.jobs.get(job_id)

    def list(self) -> List[Dict[str, Any]]:
        return sorted((j.as_dict() for j in self.jobs.values()),
                      key=lambda j: j.get("started_at") or "", reverse=True)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status in ("done", "error", "canceled"):
            return False
        job.cancel = True
        return True

    # ------------------------------------------------------------------
    def _run(self, job: VideoJob) -> None:
        job.status = "running"
        job.started_at = db.now_iso()
        cap = cv2.VideoCapture(str(job.path))
        if not cap.isOpened():
            job.status = "error"
            job.message = "No se pudo abrir el video (formato no soportado)"
            job.ended_at = db.now_iso()
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0 or fps > 240:
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        target = max(0.5, float(CONFIG.get("video_target_fps") or 6))
        stride = max(1, int(round(fps / target)))
        job.fps = fps
        job.frames_total = total
        job.duration_s = round(total / fps, 1) if total else 0.0

        source_id = db.create_source(job.name, "video", str(job.path))
        detector = build_detector()
        session_id = db.create_session(
            source_id, job.name, "video", detector.name,
            {"fps": fps, "stride": stride, "frames": total,
             "resolution": f"{width}x{height}", "job": job.id},
        )
        job.session_id = session_id
        analyzer = Analyzer(session_id, f"P{session_id}", "video", detector=detector,
                            zone_manager=ZoneManager(), base_wall=datetime.now())

        writer = None
        out_path = OUTPUT_DIR / f"sesion_{session_id}_{job.id}.mp4"
        if CONFIG.get("render_annotated_video") and width and height:
            writer = _open_writer(out_path, target, width, height)

        idx = 0
        last_ui = 0.0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if job.cancel:
                    job.status = "canceled"
                    break
                if idx % stride == 0:
                    video_ts = idx / fps
                    result = analyzer.process(frame, video_ts=video_ts)
                    job.frames_analyzed = analyzer.frames_analyzed
                    if writer is not None:
                        active = [t for t in analyzer.tracker.tracks.values()
                                  if t.confirmed and not t.closed and t.misses == 0]
                        writer.write(analyzer.annotate(frame, active))
                    if total:
                        job.progress = round(min(100.0, (idx + 1) / total * 100), 1)
                    if time.monotonic() - last_ui > 1.0:
                        last_ui = time.monotonic()
                        db.update_session(session_id, frames_seen=idx + 1,
                                          frames_analyzed=analyzer.frames_analyzed,
                                          progress=job.progress,
                                          duration_s=round(video_ts, 1))
                        job.message = (f"{result['persons']} persona(s) en t="
                                       f"{video_ts:.0f}s")
                idx += 1
        except Exception as exc:  # pragma: no cover
            log.exception("Fallo procesando %s", job.path)
            job.status = "error"
            job.message = str(exc)
        finally:
            cap.release()
            if writer is not None:
                writer.release()

        metrics = analyzer.finalize()
        metrics["zones"] = analyzer.zones.snapshot()
        job.metrics = metrics
        job.ended_at = db.now_iso()
        if job.status not in ("error", "canceled"):
            job.status = "done"
            job.progress = 100.0
            job.message = (f"{metrics['unique_persons']} personas unicas, "
                           f"{metrics['total_events']} eventos")
        if writer is not None and out_path.exists():
            _transcode_h264(out_path)
            job.output = f"outputs/{out_path.name}"
        db.update_session(session_id, frames_seen=idx,
                          frames_analyzed=analyzer.frames_analyzed,
                          progress=job.progress,
                          meta={"metrics": metrics, "output": job.output,
                                "fps": fps, "stride": stride,
                                "resolution": f"{width}x{height}"})
        db.close_session(session_id, "done" if job.status == "done" else job.status)


_WORKING_CODEC: Optional[str] = None


def _open_writer(path: Path, fps: float, width: int, height: int):
    """Intenta H.264 (reproducible en el navegador) y cae a mp4v."""
    global _WORKING_CODEC
    candidates = [_WORKING_CODEC] if _WORKING_CODEC else ["avc1", "H264", "mp4v"]
    for codec in candidates:
        try:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(str(path), fourcc, max(1.0, fps), (width, height))
            if writer.isOpened():
                if _WORKING_CODEC != codec:
                    log.info("Video anotado con codec %s", codec)
                _WORKING_CODEC = codec
                return writer
            writer.release()
        except Exception:
            continue
    log.warning("No se pudo abrir VideoWriter para %s", path)
    return None


def _transcode_h264(path: Path) -> None:
    """Si hay ffmpeg, reconvierte a H.264 para que el navegador lo reproduzca."""
    import shutil as _shutil
    import subprocess

    if _WORKING_CODEC in ("avc1", "H264") or not path.exists():
        return
    ffmpeg = _shutil.which("ffmpeg")
    if not ffmpeg:
        return
    tmp = path.with_suffix(".h264.mp4")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-c:v", "libx264",
             "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(tmp)], check=True, timeout=900)
        tmp.replace(path)
        log.info("Video anotado reconvertido a H.264: %s", path.name)
    except Exception as exc:
        log.info("ffmpeg no pudo reconvertir (%s); se conserva el original", exc)
        tmp.unlink(missing_ok=True)


LIVE = LiveRegistry()
JOBS = JobManager()
SERVER_CAMERA = CameraStream()

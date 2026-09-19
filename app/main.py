"""Punto de entrada de la aplicacion web (FastAPI)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import business, db
from .api import live_socket, router
from .config import CONFIG, DATA_DIR, SNAPSHOT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("officevision")

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="OfficeVision AI",
              description="Analisis de video con IA para entornos de oficina",
              version="1.0.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")

PAGES = [
    ("/", "index.html", "Dashboard", "\u25a6"),
    ("/vivo", "vivo.html", "Camara en vivo", "\u25c9"),
    ("/videos", "videos.html", "Videos", "\u25b6"),
    ("/zonas", "zonas.html", "Puntos criticos", "\u25ce"),
    ("/operacion", "operacion.html", "Operacion", "\u260e"),
    ("/reportes", "reportes.html", "Reportes", "\u25a4"),
]


def _page(template: str, title: str):
    async def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, template,
            {"title": title, "nav": PAGES, "config": CONFIG.as_dict()})
    return handler


for path, template, title, _icon in PAGES:
    app.get(path, response_class=HTMLResponse, include_in_schema=False)(
        _page(template, title))


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await live_socket(websocket)


def _purge_snapshots() -> None:
    days = int(CONFIG.get("snapshot_retention_days") or 0)
    if days <= 0:
        return
    cutoff = time.time() - days * 86400
    removed = 0
    for f in SNAPSHOT_DIR.glob("*.jpg"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        log.info("Retencion: %s snapshots antiguos eliminados", removed)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    _purge_snapshots()
    try:
        imported = business.import_samples()
        if imported:
            log.info("Datos operativos importados: %s", imported)
    except Exception as exc:  # pragma: no cover
        log.warning("No se pudieron importar los datos de ejemplo: %s", exc)
    stale = db.query("SELECT id FROM sessions WHERE status='running'")
    for row in stale:
        db.close_session(row["id"], "canceled")
    if stale:
        log.info("Se cerraron %s sesiones que quedaron abiertas", len(stale))
    # Sondear los detectores importa torch y tarda ~1,3 s la primera vez. Se
    # hace en segundo plano al arrancar para que no lo pague quien abra la
    # primera pantalla. Lo midio la prueba de carga del Reto 7.
    def _calentar() -> None:
        try:
            from .vision.detector import available_backends
            available_backends()
            log.info("Detectores sondeados y en cache")
        except Exception as exc:                      # pragma: no cover
            log.warning("No se pudieron sondear los detectores: %s", exc)

    threading.Thread(target=_calentar, name="calentar-detectores", daemon=True).start()
    log.info("OfficeVision AI listo - detector configurado: %s", CONFIG.get("detector"))

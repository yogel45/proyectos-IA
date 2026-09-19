"""Servidor de DocuFlow AI (aplicacion independiente)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .api import router
from .config import CONFIG, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("docuflow")

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

def _version_estaticos() -> str:
    """Marca que cambia cuando cambian el CSS o el JS.

    Sin esto, tras actualizar el proyecto el navegador sigue sirviendo el CSS
    que tenia en cache y la pantalla se ve rota o antigua. Con la marca en la
    URL, un archivo nuevo es una URL nueva y se descarga solo.
    """
    marca = 0.0
    for nombre in ("app.css", "app.js"):
        ruta = BASE / "static" / nombre
        if ruta.exists():
            marca = max(marca, ruta.stat().st_mtime)
    return str(int(marca))


VERSION_ESTATICOS = _version_estaticos()


app = FastAPI(title="DocuFlow AI",
              description="Clasificacion, nombrado y archivado automatico de documentos",
              version="1.0.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

PAGES = [
    ("/", "index.html", "Bandeja", "▧"),
    ("/configuracion", "configuracion.html", "Reglas y nombres", "⚙"),
]


def _page(template: str, title: str):
    async def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, template, {"title": title, "nav": PAGES, "v": VERSION_ESTATICOS})
    return handler


for path, template, title, _icono in PAGES:
    app.get(path, response_class=HTMLResponse, include_in_schema=False)(
        _page(template, title))


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    log.info("DocuFlow AI listo - umbral de revision: %s", CONFIG.get("umbral_revision"))

"""Servidor de Directorio vivo (aplicacion independiente)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .api import router
from .config import CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("directorio")

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


app = FastAPI(title="Directorio vivo",
              description="Contactos que se arman solos con lo que ya pasa en el despacho",
              version="1.0.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

PAGES = [
    ("/", "buscar.html", "Buscar", "⌕"),
    ("/casos", "casos.html", "Expedientes", "▤"),
    ("/alta", "alta.html", "Alta rapida", "＋"),
    ("/duplicados", "duplicados.html", "Duplicados", "⧉"),
    ("/fuentes", "fuentes.html", "Fuentes", "⇵"),
]

SUBTITULOS = {
    "/": "Tira de cualquier hilo: un numero, un nombre, un expediente o un papel",
    "/casos": "Quien es quien en cada expediente",
    "/alta": "Pega una firma y la ficha se arma sola",
    "/duplicados": "Propuestas con su motivo; nada se une sin que lo aceptes",
    "/fuentes": "De donde se alimenta el directorio",
}


def _page(template: str, title: str, path: str):
    async def handler(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, template,
            {"title": title, "nav": PAGES, "v": VERSION_ESTATICOS,
             "subtitulo": SUBTITULOS.get(path, "")})
    return handler


for path, template, title, _icono in PAGES:
    app.get(path, response_class=HTMLResponse, include_in_schema=False)(
        _page(template, title, path))


@app.get("/persona/{persona_id}", response_class=HTMLResponse, include_in_schema=False)
async def pagina_persona(request: Request, persona_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "persona.html",
        {"title": "Ficha", "nav": PAGES, "v": VERSION_ESTATICOS, "persona_id": persona_id,
         "subtitulo": "Todo lo que el despacho sabe de esta persona"})


@app.get("/caso/{caso_id}", response_class=HTMLResponse, include_in_schema=False)
async def pagina_caso(request: Request, caso_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "caso.html",
        {"title": "Expediente", "nav": PAGES, "v": VERSION_ESTATICOS, "caso_id": caso_id,
         "subtitulo": "Quien es quien y que ha pasado"})


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()
    log.info("Directorio vivo listo - umbral de duplicado: %s",
             CONFIG.get("umbral_duplicado"))

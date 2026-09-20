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

# --------------------------------------------------------------------------
# Manual de la API
# --------------------------------------------------------------------------
# La pagina /docs la genera Swagger, y de fabrica viene con un ancho fijo que
# deja la pantalla a medias y sin forma de volver a la aplicacion. Se sirve
# con una barra propia arriba —nombre y boton de volver— y con el ancho
# liberado, para que no parezca otra cosa distinta del programa.
def _manual_api(titulo: str, volver: str = "/") -> HTMLResponse:
    from fastapi.openapi.docs import get_swagger_ui_html

    pagina = get_swagger_ui_html(openapi_url="/openapi.json", title=f"{titulo} · API")
    html = pagina.body.decode()
    extra = """
<style>
  body{margin:0;background:#fff;font-family:Roboto,"Segoe UI",system-ui,sans-serif}
  .volver-barra{
    position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:14px;
    padding:10px 20px;background:#fff;border-bottom:1px solid #dadce0;
  }
  .volver-barra a{
    display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 20px;
    border-radius:999px;background:#1967d2;color:#fff;font-size:14px;font-weight:500;
    text-decoration:none;
  }
  .volver-barra a:hover{background:#1a73e8}
  .volver-barra span{color:#5f6368;font-size:14px}
  /* Swagger se encoge a 1460 px de fabrica: aqui usa el ancho que haya. */
  .swagger-ui .wrapper,.swagger-ui .opblock-tag-section,
  .swagger-ui section.models,.swagger-ui .information-container{
    max-width:none !important;
  }
  .swagger-ui .wrapper{padding:0 20px}
  .swagger-ui .topbar{display:none}
  .swagger-ui .info{margin:22px 0 18px}
  @media(max-width:700px){
    .volver-barra{padding:8px 12px}
    .volver-barra span{display:none}
    .swagger-ui .wrapper{padding:0 10px}
  }
</style>
<div class="volver-barra">
  <a href="VOLVER">&#8592; Volver a la aplicacion</a>
  <span>Manual de la API &middot; TITULO</span>
</div>

<div id="sin-red" style="display:none;max-width:640px;margin:60px auto;padding:24px;
     border:1px solid #dadce0;border-radius:16px;font-family:Roboto,'Segoe UI',system-ui,sans-serif">
  <h2 style="margin:0 0 10px;font-size:20px;font-weight:500;color:#202124">
    El manual de la API necesita conexion</h2>
  <p style="margin:0 0 14px;color:#5f6368;line-height:1.55;font-size:14px">
    Esta pagina la dibuja Swagger, que se descarga de internet. El programa en si
    <b>no necesita conexion para nada</b>: puedes cerrar esta pestana y seguir
    trabajando con normalidad.</p>
  <p style="margin:0;color:#5f6368;line-height:1.55;font-size:14px">
    Si lo que querias era ver la lista de endpoints sin conexion, esta en
    <a href="/openapi.json" style="color:#1967d2">/openapi.json</a>.</p>
</div>
<script>
  // Swagger tarda; si a los 4 segundos no pinto nada, es que no llego.
  setTimeout(function () {
    var ui = document.querySelector('.swagger-ui .information-container, .swagger-ui .opblock');
    if (!ui) {
      var a = document.getElementById('sin-red');
      if (a) a.style.display = 'block';
    }
  }, 4000);
</script>
""".replace("VOLVER", volver).replace("TITULO", titulo)
    html = html.replace("<body>", "<body>" + extra, 1)
    return HTMLResponse(html)



app = FastAPI(title="OfficeVision AI",
              description="Analisis de video con IA para entornos de oficina",
              version="1.0.0",
              docs_url=None, redoc_url=None)
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
            {"title": title, "nav": PAGES, "v": VERSION_ESTATICOS,
             "config": CONFIG.as_dict()})
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


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def manual_api() -> HTMLResponse:
    return _manual_api("OfficeVision AI", "/")

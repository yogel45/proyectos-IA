"""Convierte el informe de una sesion en una pagina HTML que se lee sola.

La idea es que el resultado se pueda abrir con doble clic, enviar por correo o
imprimir sin que falte nada: las graficas van incrustadas dentro del propio
archivo, asi que no hay carpetas que acompanar ni enlaces que se rompan al
mover el archivo de sitio.

Se genera al terminar cada sesion, y tambien se puede rehacer despues sobre
una sesion ya ejecutada:

    python run_pruebas.py --html data/pruebas/20260920_011911
"""
from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Graficas que se incrustan, en el orden en que aparecen.
GRAFICAS = [
    ("carga-escalada.png", "Cuanto se espera segun el caudal"),
    ("carga-caudal.png", "Lo que se pide frente a lo que se sirve"),
    ("carga-errores.png", "Errores segun el caudal"),
    ("carga-operaciones.png", "Coste de cada operacion en el nivel mas alto"),
    ("carga-consultas-caras.png", "Coste de cada consulta cara"),
    ("carga-escrituras.png", "Coste de cada escritura"),
    ("carga-resistencia.png", "Latencia a lo largo del caudal sostenido"),
    ("carga-recursos.png", "CPU y memoria durante toda la sesion"),
]


# --------------------------------------------------------------------------
# Utilidades de formato
# --------------------------------------------------------------------------
def _e(texto: Any) -> str:
    return html.escape(str(texto), quote=True)


def _ms(v: Optional[float]) -> str:
    """Milisegundos legibles: 87 ms, 2,3 s, 1 min 20 s."""
    if v is None:
        return "—"
    if v < 1000:
        return f"{v:.0f} ms"
    if v < 60_000:
        return f"{v / 1000:.1f} s".replace(".", ",")
    m, s = divmod(int(v / 1000), 60)
    return f"{m} min {s:02d} s"


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:.2f} %".replace(".", ",")


def _num(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{v:,}".replace(",", " ")


def _estado(tasa: Optional[float]) -> str:
    """Clase CSS segun lo mal que fue: verde, ambar o rojo."""
    if tasa is None:
        return ""
    if tasa == 0:
        return "bien"
    if tasa < 5:
        return "aviso"
    return "mal"


def _incrustar(ruta: Path) -> Optional[str]:
    """Devuelve la imagen como data: URI, o None si no esta."""
    if not ruta.exists():
        return None
    datos = base64.b64encode(ruta.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{datos}"


# --------------------------------------------------------------------------
# Estilos
# --------------------------------------------------------------------------
CSS = """
:root{
  --tinta:#202124; --tinta-2:#5f6368; --papel:#fff; --papel-2:#f8f9fa;
  --linea:#dadce0; --azul:#1a73e8; --azul-claro:#e8f0fe;
  --verde:#188038; --verde-claro:#e6f4ea;
  --ambar:#e37400; --ambar-claro:#fef7e0;
  --rojo:#c5221f; --rojo-claro:#fce8e6;
  --sombra:0 1px 3px rgba(60,64,67,.15), 0 4px 8px rgba(60,64,67,.08);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;max-width:100%;overflow-x:hidden}
body{
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  color:var(--tinta); background:var(--papel-2);
  -webkit-font-smoothing:antialiased;
}
.hoja{max-width:1100px;margin:0 auto;padding:0 20px 80px}

header.principal{
  background:var(--azul); color:#fff; margin:0 -20px 28px;
  padding:36px 20px 30px;
}
header.principal .interior{max-width:1100px;margin:0 auto}
header.principal h1{margin:0 0 6px;font-size:26px;font-weight:500;line-height:1.25}
header.principal .sub{opacity:.9;font-size:14px}
header.principal .meta{
  margin-top:18px;display:flex;flex-wrap:wrap;gap:8px 20px;
  font-size:13px;opacity:.9
}

h2{
  font-size:19px;font-weight:500;margin:36px 0 14px;
  padding-bottom:8px;border-bottom:1px solid var(--linea)
}
h3{font-size:15px;font-weight:500;margin:22px 0 10px;color:var(--tinta-2)}
p{margin:0 0 12px}
.nota{color:var(--tinta-2);font-size:13.5px}

.tarjetas{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));margin-bottom:8px}
.tarjeta{
  background:var(--papel);border:1px solid var(--linea);border-radius:12px;
  padding:16px 18px;box-shadow:var(--sombra);min-width:0
}
.tarjeta .rotulo{font-size:12.5px;color:var(--tinta-2);margin-bottom:6px}
.tarjeta .cifra{font-size:26px;font-weight:500;line-height:1.15;word-break:break-word}
.tarjeta .pie{font-size:12.5px;color:var(--tinta-2);margin-top:4px}
.tarjeta.bien .cifra{color:var(--verde)}
.tarjeta.aviso .cifra{color:var(--ambar)}
.tarjeta.mal .cifra{color:var(--rojo)}

.caja{
  background:var(--papel);border:1px solid var(--linea);border-radius:12px;
  padding:18px 20px;box-shadow:var(--sombra);margin-bottom:16px;min-width:0
}
.caja.alerta{background:var(--rojo-claro);border-color:#f5c6c4}
.caja.ok{background:var(--verde-claro);border-color:#b7dfc4}
.caja.aviso{background:var(--ambar-claro);border-color:#fadf9a}
.caja h3{margin-top:0;color:inherit}

.tabla-envoltorio{overflow-x:auto;-webkit-overflow-scrolling:touch;
  border:1px solid var(--linea);border-radius:12px;background:var(--papel);
  box-shadow:var(--sombra);margin-bottom:16px}
table{border-collapse:collapse;width:100%;font-size:14px;min-width:min(100%,520px)}
th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--linea);white-space:nowrap}
th{font-weight:500;color:var(--tinta-2);font-size:12.5px;
   text-transform:uppercase;letter-spacing:.04em;background:var(--papel-2)}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--azul-claro)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
td.txt{white-space:normal;min-width:180px}

.pastilla{display:inline-block;padding:2px 9px;border-radius:999px;
  font-size:12px;font-weight:500;white-space:nowrap}
.pastilla.bien{background:var(--verde-claro);color:var(--verde)}
.pastilla.aviso{background:var(--ambar-claro);color:var(--ambar)}
.pastilla.mal{background:var(--rojo-claro);color:var(--rojo)}

figure{margin:0 0 20px}
figure img{width:100%;height:auto;display:block;border-radius:12px;
  border:1px solid var(--linea);background:var(--papel)}
figcaption{font-size:13px;color:var(--tinta-2);margin-top:8px}

code{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  background:var(--papel-2);border:1px solid var(--linea);
  border-radius:5px;padding:1px 5px}
pre{background:#202124;color:#e8eaed;border-radius:10px;padding:14px 16px;
  overflow-x:auto;font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre code{background:none;border:none;color:inherit;padding:0}

footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--linea);
  color:var(--tinta-2);font-size:13px}

@media (max-width:640px){
  header.principal{padding:26px 20px 22px}
  header.principal h1{font-size:21px}
  .tarjeta .cifra{font-size:22px}
  th,td{padding:9px 11px}
  .hoja{padding:0 14px 60px}
  header.principal{margin:0 -14px 22px}
}
@media print{
  body{background:#fff}
  .caja,.tarjeta,.tabla-envoltorio{box-shadow:none}
  header.principal{background:#fff;color:var(--tinta);
    border-bottom:3px solid var(--azul)}
  h2{page-break-after:avoid} figure,table{page-break-inside:avoid}
}
"""


# --------------------------------------------------------------------------
# Bloques
# --------------------------------------------------------------------------
def _tabla(cabeceras: List[str], filas: List[List[str]],
           numericas: Optional[set] = None) -> str:
    numericas = numericas or set()
    th = "".join(f'<th class="{"n" if i in numericas else ""}">{_e(c)}</th>'
                 for i, c in enumerate(cabeceras))
    cuerpo = []
    for fila in filas:
        tds = "".join(
            f'<td class="{"n" if i in numericas else ""}">{c}</td>'
            for i, c in enumerate(fila))
        cuerpo.append(f"<tr>{tds}</tr>")
    return (f'<div class="tabla-envoltorio"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(cuerpo)}</tbody></table></div>')


def _tarjeta(rotulo: str, cifra: str, pie: str = "", clase: str = "") -> str:
    return (f'<div class="tarjeta {clase}"><div class="rotulo">{_e(rotulo)}</div>'
            f'<div class="cifra">{cifra}</div>'
            + (f'<div class="pie">{pie}</div>' if pie else "")
            + "</div>")


def _resumen_escenario(d: Dict[str, Any]) -> List[str]:
    """Una fila de tabla con lo esencial de un escenario."""
    tasa = d.get("tasa_error_pct")
    return [
        _num(d.get("n")),
        _ms(d.get("lat_p50_ms")),
        _ms(d.get("lat_p95_ms")),
        _ms(d.get("lat_max_ms")),
        f'<span class="pastilla {_estado(tasa)}">{_pct(tasa)}</span>',
        _num(d.get("rps")),
    ]


CAB_ESCENARIO = ["Peticiones", "Mediana", "p95", "Peor", "Errores", "Servidas/s"]
NUM_ESCENARIO = {0, 1, 2, 3, 4, 5}


def _detalle_errores(d: Dict[str, Any]) -> str:
    det = d.get("detalle_errores") or {}
    if not det:
        return ""
    partes = " · ".join(f"{_e(k)}: <strong>{_num(v)}</strong>"
                        for k, v in sorted(det.items(), key=lambda x: -x[1]))
    return f'<p class="nota">Desglose: {partes}</p>'


# --------------------------------------------------------------------------
# Generacion
# --------------------------------------------------------------------------
def generar(informe: Dict[str, Any], img_dir: Path, destino: Path) -> Path:
    """Escribe el informe HTML y devuelve la ruta."""
    s: List[str] = []
    a = s.append

    sello = informe.get("sello", "")
    try:
        cuando = datetime.strptime(sello, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y a las %H:%M")
    except ValueError:
        cuando = sello
    maq = informe.get("maquina", {})
    just = informe.get("justificacion", {})
    rps_nom = informe.get("rps_nominal") or 0.0

    # ---------------- cabecera ----------------
    a(f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pruebas de carga · {_e(informe.get("sistema_probado", "el sistema"))}</title>
<style>{CSS}</style></head><body>
<header class="principal"><div class="interior">
  <h1>Pruebas de tráfico, carga y actividad automatizada</h1>
  <div class="sub">Sistema puesto a prueba: <strong>{_e(informe.get("sistema_probado", "—"))}</strong>
    · {_e(informe.get("base", ""))}</div>
  <div class="meta">
    <span>Sesión del {_e(cuando)}</span>
    <span>Duración {_ms((informe.get("duracion_total_s") or 0) * 1000)}</span>
    <span>{_e(maq.get("sistema", ""))} · {_e(maq.get("nucleos", "?"))} núcleos · {_e(maq.get("ram_gb", "?"))} GB</span>
    <span>Python {_e(maq.get("python", ""))}</span>
  </div>
</div></header>
<div class="hoja">''')

    # ---------------- veredicto ----------------
    a("<h2>De un vistazo</h2>")
    a('<div class="tarjetas">')

    sostenible = _sostenible(informe)
    esc = informe.get("escalada") or []
    limpio = [e for e in esc if (e.get("tasa_error_pct") or 0) == 0]
    techo = limpio[-1]["rps_objetivo"] if limpio else None

    a(_tarjeta("Carga real de la oficina",
               f'{rps_nom:.3f}'.replace(".", ",") + " pet./s",
               f'{_num(just.get("peticiones_hora_punta"))} peticiones en la hora punta'))
    if sostenible:
        veces = sostenible / rps_nom if rps_nom else 0
        a(_tarjeta("Aguanta de forma sostenida", f"{_num(sostenible)} pet./s",
                   f"{veces:,.0f}× la demanda real".replace(",", " "), "bien"))
    elif techo:
        veces = techo / rps_nom if rps_nom else 0
        a(_tarjeta("Último caudal sin errores", f"{_num(techo)} pet./s",
                   f"{veces:,.0f}× la demanda real".replace(",", " "), "bien"))

    tol = informe.get("tolerancia") or {}
    if tol:
        bien = tol.get("correctos", 0) == tol.get("total", 0)
        a(_tarjeta("Casos mal formados y maliciosos",
                   f'{_num(tol.get("correctos"))} de {_num(tol.get("total"))}',
                   f'{_num(tol.get("errores_500"))} errores 500',
                   "bien" if bien and not tol.get("errores_500") else "aviso"))

    integ = informe.get("integridad") or {}
    if integ:
        vivas = integ.get("fichas_de_referencia_vivas", "—")
        intacto = str(vivas).split("/")[0] == str(vivas).split("/")[-1]
        a(_tarjeta("Datos después de la paliza",
                   "Intactos" if intacto else "Revisar",
                   f"{_e(vivas)} fichas de referencia vivas",
                   "bien" if intacto else "mal"))

    rec = informe.get("recuperacion_s")
    if rec is not None and rec > 0:
        a(_tarjeta("Tarda en volver tras caerse", _ms(rec * 1000),
                   "después de 20 s de sobrecarga", "mal" if rec > 60 else "aviso"))

    imp = informe.get("importacion") or {}
    if imp.get("ejecutado"):
        c = imp.get("carga", {})
        a(_tarjeta("Con una importación pesada de fondo",
                   _ms(c.get("lat_p95_ms")),
                   f'p95 con {_num(imp.get("contactos"))} contactos importándose · '
                   f'{_pct(c.get("tasa_error_pct"))} de errores',
                   _estado(c.get("tasa_error_pct"))))
    a("</div>")

    # ---------------- de donde sale la carga ----------------
    a("<h2>De dónde sale la carga</h2>")
    a('<div class="caja"><p>La carga no se inventa: sale de los archivos reales '
      'de la oficina. La hora más cargada del historial de la centralita tuvo '
      f'<strong>{_e(just.get("pico_llamadas_hora", "—"))} llamadas</strong>, y en la '
      f'nómina hay <strong>{_e(just.get("empleados", "—"))} personas</strong>. '
      'De ahí sale el reparto de abajo, operación por operación.</p>')
    hp = just.get("hora_punta") or {}
    if hp:
        total = sum(hp.values()) or 1
        filas = [[_e(k), _num(v), f"{100 * v / total:.1f} %".replace(".", ",")]
                 for k, v in sorted(hp.items(), key=lambda x: -x[1])]
        filas.append(["<strong>Total</strong>", f"<strong>{_num(total)}</strong>",
                      "<strong>100 %</strong>"])
        a(_tabla(["Operación", "Veces en la hora punta", "Peso"], filas, {1, 2}))
    a(f'<p class="nota">Son {_num(sum(hp.values()) if hp else 0)} peticiones en '
      f'60 minutos, o sea <strong>{rps_nom:.3f}'.replace(".", ",") +
      ' peticiones por segundo</strong>. Todas las cifras de este informe son '
      'ese número multiplicado.</p></div>')

    # ---------------- arranque en frio ----------------
    frio = informe.get("arranque_frio") or []
    if frio:
        a("<h2>Lo que espera la primera persona del día</h2>")
        filas = [[_e(f["pantalla"]), _ms(f.get("primera_ms")), _ms(f.get("segunda_ms")),
                  f'<span class="pastilla {"bien" if f.get("estado") == 200 else "mal"}">'
                  f'{_e(f.get("estado"))}</span>']
                 for f in frio]
        a(_tabla(["Pantalla", "Primera vez", "Repetida", "Respuesta"], filas, {1, 2}))

    # ---------------- escalada ----------------
    if esc:
        a("<h2>Escalada: dónde deja de ir bien</h2>")
        filas = []
        for e in esc:
            tasa = e.get("tasa_error_pct")
            filas.append([
                f'<strong>{_num(e.get("rps_objetivo"))}</strong> pet./s',
                f'{_num(e.get("factor"))}×',
                _ms(e.get("lat_p50_ms")), _ms(e.get("lat_p95_ms")),
                f'<span class="pastilla {_estado(tasa)}">{_pct(tasa)}</span>',
                _num(e.get("rps")),
            ])
        a(_tabla(["Caudal ofrecido", "× la hora punta", "Mediana", "p95",
                  "Errores", "Servidas/s"], filas, {0, 1, 2, 3, 4, 5}))
        if limpio and len(limpio) < len(esc):
            rompe = esc[len(limpio)]
            a(f'<div class="caja aviso"><h3>El acantilado</h3><p>Entre '
              f'<strong>{_num(techo)}</strong> y '
              f'<strong>{_num(rompe.get("rps_objetivo"))}</strong> peticiones por '
              f'segundo el sistema pasa de {_ms(limpio[-1].get("lat_p95_ms"))} y cero '
              f'errores a {_ms(rompe.get("lat_p95_ms"))} y {_pct(rompe.get("tasa_error_pct"))} '
              f'de fallos. No se degrada poco a poco: se cae.</p></div>')

    # ---------------- caudal sostenible ----------------
    sost = informe.get("sostenible") or []
    if sost:
        a("<h2>Caudal sostenible: lo mismo, pero durante dos minutos</h2>")
        a('<div class="caja"><p>La escalada mide tramos de 20 segundos, y eso '
          '<strong>sobreestima</strong>: un sistema con un acantilado de concurrencia '
          'aguanta 20 segundos de un caudal que no aguantaría dos minutos, porque la '
          'cola no llega a acumularse. Estas medidas son de 120 segundos seguidos.</p>')
        filas = []
        for e in sost:
            tasa = e.get("tasa_error_pct")
            veces = (e.get("rps_objetivo") or 0) / rps_nom if rps_nom else 0
            filas.append([
                f'<strong>{_num(e.get("rps_objetivo"))}</strong> pet./s',
                f"{veces:,.0f}×".replace(",", " "),
                _ms(e.get("lat_p50_ms")), _ms(e.get("lat_p95_ms")),
                f'<span class="pastilla {_estado(tasa)}">{_pct(tasa)}</span>',
            ])
        a(_tabla(["Caudal sostenido", "× la hora punta", "Mediana", "p95", "Errores"],
                 filas, {0, 1, 2, 3, 4}))
        a("</div>")

    # ---------------- rafagas ----------------
    raf = informe.get("rafagas") or []
    if raf:
        a("<h2>Ráfaga: todas a la vez desde reposo</h2>")
        filas = []
        for r in raf:
            tasa = r.get("tasa_error_pct")
            filas.append([
                f'<strong>{_num(r.get("concurrencia"))}</strong> simultáneas',
                _ms(r.get("lat_p95_ms")), _ms(r.get("lat_max_ms")),
                f'<span class="pastilla {_estado(tasa)}">{_pct(tasa)}</span>',
            ])
        a(_tabla(["Ráfaga", "p95", "La peor", "Errores"], filas, {0, 1, 2, 3}))

    # ---------------- los demas escenarios ----------------
    otros = [
        ("escrituras", "Escrituras concurrentes",
         "escrituras_por_operacion",
         "Varias personas dando de alta y corrigiendo fichas a la vez."),
        ("busqueda_dura", "Sólo las consultas caras",
         "busqueda_dura_por_operacion",
         "Texto libre, páginas hondas, ordenaciones y detección de duplicados."),
        ("resistencia", "Resistencia: caudal sostenido", None,
         "El mismo caudal durante mucho más tiempo, buscando degradación lenta."),
    ]
    hay = [o for o in otros if informe.get(o[0])]
    if hay:
        a("<h2>Escenario por escenario</h2>")
    for clave, titulo, clave_ops, explicacion in hay:
        d = informe[clave]
        a(f'<div class="caja"><h3>{_e(titulo)}</h3>'
          f'<p class="nota">{_e(explicacion)} '
          f'Objetivo: {_num(d.get("rps_objetivo"))} peticiones/s durante '
          f'{_num(d.get("duracion_s"))} s.</p>')
        a(_tabla(CAB_ESCENARIO, [_resumen_escenario(d)], NUM_ESCENARIO))
        a(_detalle_errores(d))
        ops = informe.get(clave_ops) if clave_ops else None
        if ops:
            filas = [[_e(o["operacion"])] + _resumen_escenario(o) for o in ops]
            a("<h3>Por operación</h3>")
            a(_tabla(["Operación"] + CAB_ESCENARIO, filas,
                     {i + 1 for i in NUM_ESCENARIO}))
            _pista_reparto(a, ops)
        a("</div>")

    # ---------------- importacion ----------------
    if imp.get("ejecutado"):
        t = imp.get("trabajo", {})
        c = imp.get("carga", {})
        a("<h2>Trabajo pesado mientras la oficina sigue consultando</h2>")
        clase = "ok" if (c.get("tasa_error_pct") or 0) == 0 else "aviso"
        a(f'<div class="caja {clase}"><p>Con una importación de '
          f'<strong>{_num(imp.get("contactos"))} contactos</strong> corriendo en '
          f'segundo plano, la agenda respondió con <strong>{_ms(c.get("lat_p95_ms"))}'
          f'</strong> de p95 y <strong>{_pct(c.get("tasa_error_pct"))}</strong> de '
          f'errores. La importación terminó con estado '
          f'<code>{_e(t.get("status"))}</code>: {_num(t.get("created"))} creados, '
          f'{_num(t.get("updated"))} actualizados.</p></div>')

    # ---------------- tolerancia ----------------
    if tol:
        a("<h2>Tolerancia a errores y seguridad</h2>")
        a(f'<div class="caja {"ok" if not tol.get("errores_500") else "alerta"}">'
          f'<p><strong>{_num(tol.get("correctos"))} de {_num(tol.get("total"))}</strong> '
          f'respondieron con el código que debían, y hubo '
          f'<strong>{_num(tol.get("errores_500"))}</strong> errores 500. '
          'Lo que se comprueba no es que fallen, sino <em>cómo</em> fallan: un 401 o '
          'un 422 es el sistema defendiéndose; un 500 es el sistema roto.</p></div>')
        filas = []
        for c in tol.get("casos", []):
            ok = c.get("correcto")
            clase = "bien" if ok else ("mal" if c.get("quinientos") else "aviso")
            filas.append([
                f'<span class="txt">{_e(c.get("caso"))}</span>',
                f'<code>{_e(c.get("metodo"))}</code>',
                f'<code>{_e(str(c.get("url"))[:60])}</code>',
                _e(c.get("esperado")),
                f'<span class="pastilla {clase}">{_e(c.get("obtenido"))}</span>',
                _ms(c.get("ms")),
            ])
        a(_tabla(["Caso", "Método", "Ruta", "Esperado", "Obtenido", "Tardó"],
                 filas, {5}))

    cer = informe.get("cerrojo") or {}
    if cer:
        clase = "ok" if cer.get("bloquea") else "alerta"
        codigos = " → ".join(str(c) for c in cer.get("codigos", []))
        corte = cer.get("corta_despues_de")
        texto = (f'La puerta se cierra en el intento '
                 f'<strong>{_num((corte or 0) + 1)}</strong> con un HTTP 429.'
                 if cer.get("bloquea") else
                 'Ninguno de los intentos fallidos consecutivos fue rechazado.')
        a(f'<div class="caja {clase}"><h3>Cerrojo por intentos fallidos</h3>'
          f'<p>{texto}</p><pre><code>{_e(codigos)}</code></pre></div>')

    # ---------------- integridad ----------------
    if integ:
        a("<h2>Integridad de los datos después de la paliza</h2>")
        etiquetas = {
            "contactos_antes": "Contactos antes",
            "contactos_ahora": "Contactos después",
            "en_la_papelera": "En la papelera",
            "con_correo": "Con correo",
            "con_telefono": "Con teléfono",
            "fichas_de_referencia_vivas": "Fichas de referencia vivas",
            "ficha_de_referencia": "Ficha comprobada",
            "servicio_responde": "El servicio responde",
        }
        filas = [[_e(etiquetas.get(k, k)),
                  ("Sí" if v is True else "No" if v is False else _e(v))]
                 for k, v in integ.items()]
        a(_tabla(["Comprobación", "Resultado"], filas, {1}))

    # ---------------- recursos ----------------
    recursos = informe.get("recursos") or {}
    if recursos:
        a("<h2>Recursos de la máquina</h2>")
        filas = []
        for nombre, r in recursos.items():
            filas.append([
                _e(nombre),
                f'{_num(r.get("cpu_media_pct"))} %',
                f'{_num(r.get("cpu_max_pct"))} %',
                f'{_num(r.get("rss_inicial_mb"))} MB',
                f'{_num(r.get("rss_final_mb"))} MB',
                f'{_num(r.get("deriva_memoria_mb"))} MB',
                _num(r.get("hilos_max")),
                _num(r.get("conexiones_max")),
            ])
        a(_tabla(["Proceso", "CPU media", "CPU pico", "Memoria al empezar",
                  "Al terminar", "Diferencia", "Hilos (máx.)", "Conexiones (máx.)"],
                 filas, {1, 2, 3, 4, 5, 6, 7}))
        a('<p class="nota">Que la CPU no llegue al máximo durante una caída es el '
          'dato que descarta la falta de máquina y apunta a un recurso bloqueado. '
          'El crecimiento de memoria no equivale a una fuga si durante la sesión se '
          'añadieron datos: para hablar de fuga habría que medir con la misma '
          'cantidad de datos al principio y al final.</p>')

    # ---------------- graficas ----------------
    figuras = []
    for archivo, titulo in GRAFICAS:
        uri = _incrustar(img_dir / archivo)
        if uri:
            figuras.append(f'<figure><img src="{uri}" alt="{_e(titulo)}">'
                           f'<figcaption>{_e(titulo)}</figcaption></figure>')
    if figuras:
        a("<h2>Gráficas</h2>")
        a("".join(figuras))

    # ---------------- pie ----------------
    esperas = informe.get("esperas") or {}
    tocados = {k: v for k, v in esperas.items() if v}
    a("<h2>Sobre esta sesión</h2><div class=\"caja\">")
    a(f'<p>Sesión <code>{_e(sello)}</code>, {_ms((informe.get("duracion_total_s") or 0) * 1000)} '
      f'de duración. Los datos en crudo —una fila por petición— y el registro '
      f'completo están junto a este archivo.</p>')
    if informe.get("renovaciones_de_token"):
        a(f'<p class="nota">El token de acceso se renovó '
          f'{_num(informe["renovaciones_de_token"])} vez/veces durante la sesión: '
          f'dura 15 minutos y la sesión dura más.</p>')
    if tocados:
        detalle = " · ".join(f"{_e(k)} {_num(v)} s" for k, v in tocados.items())
        a(f'<p class="nota">Antes de medir, cada escenario comprueba que el servicio '
          f'esté en pie. Estos tuvieron que esperar a que se recuperase del anterior: '
          f'{detalle}. Sin esa espera, esas medidas habrían sido de la cola de la '
          f'caída previa, no del sistema.</p>')
    limp = informe.get("limpieza") or {}
    if limp:
        a(f'<p class="nota">Limpieza: se retiraron '
          f'{_num(limp.get("contactos_de_prueba_borrados"))} registros creados por la '
          f'propia prueba.</p>')
    a("</div>")

    a(f'<footer>Generado por el arnés de pruebas del Reto 7 · '
      f'{datetime.now().strftime("%d/%m/%Y %H:%M")}</footer>')
    a("</div></body></html>")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("".join(s), encoding="utf-8")
    return destino


def _sostenible(informe: Dict[str, Any]) -> Optional[float]:
    """El caudal sostenido más alto sin errores, si se midió."""
    sost = informe.get("sostenible") or []
    limpios = [e["rps_objetivo"] for e in sost
               if (e.get("tasa_error_pct") or 0) == 0]
    return max(limpios) if limpios else None


def _pista_reparto(a, ops: List[Dict[str, Any]]) -> None:
    """Dice si los errores se reparten o se concentran.

    Es la pista más útil de todo el informe para leer un porcentaje de error:
    repartido por igual entre operaciones es saturación; concentrado en una
    sola es un defecto de esa operación — o de la propia prueba.
    """
    conError = [o for o in ops if (o.get("tasa_error_pct") or 0) > 0]
    if not conError or len(ops) < 2:
        return
    tasas = [o["tasa_error_pct"] for o in ops]
    if len(conError) == 1 and len(ops) > 1:
        o = conError[0]
        a(f'<div class="caja aviso"><p><strong>Los errores se concentran en una sola '
          f'operación</strong> («{_e(o["operacion"])}», {_pct(o["tasa_error_pct"])}) '
          f'y las demás están a cero. Eso no es saturación: es un defecto de esa '
          f'operación concreta, o de la propia prueba al ejercitarla.</p></div>')
    elif max(tasas) - min(tasas) < 10:
        a(f'<p class="nota">Los errores se reparten por igual entre las operaciones '
          f'({_pct(min(tasas))} – {_pct(max(tasas))}), que es la firma de la '
          f'saturación, no de un defecto concreto.</p>')


def desde_carpeta(carpeta: Path) -> Path:
    """Rehace el HTML de una sesión ya ejecutada."""
    carpeta = Path(carpeta)
    informe = json.loads((carpeta / "informe.json").read_text(encoding="utf-8"))
    # las gráficas pueden estar en docs/img (sesión completa) o en la propia
    # carpeta de la sesión (sesión parcial)
    raiz = carpeta.parent.parent.parent
    img = carpeta / "img"
    if not img.exists():
        img = raiz / "docs" / "img"
    return generar(informe, img, carpeta / "informe.html")

"""Convierte las medidas en graficas y en un informe legible.

Las graficas usan los mismos colores apagados que las tres aplicaciones, para
que el informe y el producto se parezcan.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

FONDO = "#0b0c0e"
SUPERFICIE = "#121417"
LINEA = "#22262c"
TEXTO = "#e9eaec"
TEXTO_2 = "#9aa1ab"
ACENTO = "#7d97b8"
OK = "#839a8c"
AVISO = "#a89578"
CRITICO = "#a87b77"
PALETA = [ACENTO, "#8a8698", OK, AVISO, CRITICO, "#7d9495", "#9a8b96"]


def _lienzo(ancho=9.6, alto=4.2):
    fig, ax = plt.subplots(figsize=(ancho, alto), dpi=150)
    fig.patch.set_facecolor(FONDO)
    ax.set_facecolor(SUPERFICIE)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(LINEA)
    ax.tick_params(colors=TEXTO_2, labelsize=8.5)
    ax.grid(True, color=LINEA, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    return fig, ax


def _guardar(fig, ruta: Path, titulo: str, subtitulo: str = "") -> None:
    fig.suptitle(titulo, color=TEXTO, fontsize=12.5, x=0.012, ha="left", y=0.985,
                 fontweight="medium")
    if subtitulo:
        fig.text(0.012, 0.905, subtitulo, color=TEXTO_2, fontsize=9, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.88 if subtitulo else 0.93))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, facecolor=FONDO)
    plt.close(fig)


def grafica_escalada(resumenes: List[Dict[str, Any]], ruta: Path,
                     rps_nominal: float) -> None:
    """Latencia segun el caudal ofrecido: donde se dobla el sistema.

    El eje horizontal es lo que se *pide*, no lo que se sirve: cuando el
    sistema se satura sirve menos de lo que recibe, y dibujar lo servido haria
    que la curva se volviera sobre si misma.
    """
    x = [r["rps_objetivo"] for r in resumenes]
    fig, ax = _lienzo(9.6, 4.4)
    for clave, color, etiqueta in (
            ("lat_p50_ms", OK, "p50 · la mitad de las veces"),
            ("lat_p95_ms", AVISO, "p95 · 19 de cada 20"),
            ("lat_p99_ms", CRITICO, "p99 · la peor de cada 100")):
        ax.plot(x, [max(0.5, r[clave]) for r in resumenes], "-o", color=color,
                linewidth=2, markersize=4.5, label=etiqueta)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1, 90_000)

    ax.axhline(1000, color=TEXTO_2, linestyle="--", linewidth=1, alpha=0.55)
    ax.text(x[0] * 1.15, 1250, "1 s: el limite de lo que se siente instantaneo",
            color=TEXTO_2, fontsize=8, ha="left")
    # La demanda real cabe muy a la izquierda del grafico: si queda fuera del
    # eje se dibuja pegada al borde, pero se dice el numero de todos modos.
    dentro = rps_nominal >= min(x)
    marca_x = rps_nominal if dentro else min(x)
    ax.axvline(marca_x, color=ACENTO, linestyle=":", linewidth=1.4, alpha=0.85)
    ax.text(marca_x * 1.15, 1.6,
            f"hora punta real de la oficina\n({rps_nominal:.3f} peticiones/s"
            + ("" if dentro else ", fuera del eje") + ")",
            color=ACENTO, fontsize=8, va="bottom")

    # marcar donde deja de aguantar
    limpio = [r for r in resumenes if r["lat_p95_ms"] < 1000]
    if limpio and len(limpio) < len(resumenes):
        borde = limpio[-1]["rps_objetivo"]
        ax.axvspan(borde, x[-1] * 1.08, color=CRITICO, alpha=0.07)
        ax.text(borde * 1.08, 2200, "saturado", color=CRITICO, fontsize=8.5)
        ax.annotate(f"aguanta hasta\n{borde:.0f} peticiones/s",
                    xy=(borde, limpio[-1]["lat_p95_ms"]),
                    xytext=(borde * 0.22, 9000), color=TEXTO,
                    fontsize=8.5, ha="center",
                    arrowprops=dict(arrowstyle="->", color=TEXTO_2, lw=1))

    ax.set_xlabel("peticiones por segundo ofrecidas (escala logaritmica)",
                  color=TEXTO_2, fontsize=9)
    ax.set_ylabel("espera del usuario (ms, escala logaritmica)", color=TEXTO_2, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"{v:,.0f}".replace(",", " ") if v >= 1 else ""))
    leg = ax.legend(facecolor=SUPERFICIE, edgecolor=LINEA, labelcolor=TEXTO_2,
                    fontsize=8.5, loc="upper left")
    leg.get_frame().set_linewidth(0.8)
    _guardar(fig, ruta, "Cuanto se espera segun el caudal",
             "La mezcla de trabajo de una hora punta real, multiplicada hasta que el sistema se dobla")


def grafica_caudal(resumenes: List[Dict[str, Any]], ruta: Path) -> None:
    """Lo que se pidio frente a lo que el sistema consiguio servir.

    Mientras la linea sigue a la diagonal, el sistema va sobrado. Donde se
    separa, esta saturado: por mucho que se le pida, no sirve mas.
    """
    objetivo = [r["rps_objetivo"] for r in resumenes]
    real = [r["rps"] for r in resumenes]
    fig, ax = _lienzo(9.6, 4.0)
    tope = max(objetivo) * 1.05
    ax.plot([0, tope], [0, tope], "--", color=TEXTO_2, linewidth=1, alpha=0.6,
            label="ideal: sirve todo lo que se le pide")
    ax.plot(objetivo, real, "-o", color=ACENTO, linewidth=2, markersize=5,
            label="conseguido")
    mejor = max(real)
    ax.axhline(mejor, color=AVISO, linestyle=":", linewidth=1.2)
    ax.text(tope * 0.02, mejor * 1.04, f"techo medido: {mejor:.0f} peticiones/s",
            color=AVISO, fontsize=8.5)
    ax.set_xlabel("peticiones por segundo ofrecidas", color=TEXTO_2, fontsize=9)
    ax.set_ylabel("peticiones por segundo servidas", color=TEXTO_2, fontsize=9)
    leg = ax.legend(facecolor=SUPERFICIE, edgecolor=LINEA, labelcolor=TEXTO_2, fontsize=8.5,
                    loc="upper left")
    leg.get_frame().set_linewidth(0.8)
    _guardar(fig, ruta, "Donde se satura",
             "Cuando la curva se separa de la diagonal, el sistema ya no da mas de si")


def grafica_errores(resumenes: List[Dict[str, Any]], ruta: Path) -> None:
    x = [f"{r['rps_objetivo']:.0f}\npedidas" for r in resumenes]
    y = [r["tasa_error_pct"] for r in resumenes]
    fig, ax = _lienzo(9.6, 3.4)
    colores = [OK if v == 0 else (AVISO if v < 1 else CRITICO) for v in y]
    ax.bar(x, y, color=colores, width=0.62)
    for i, v in enumerate(y):
        ax.text(i, v, f" {v:.2f} %" if v else " 0", color=TEXTO_2, fontsize=8,
                ha="center", va="bottom")
    ax.set_ylabel("peticiones fallidas (%)", color=TEXTO_2, fontsize=9)
    ax.set_ylim(0, max(1.0, max(y) * 1.35))
    _guardar(fig, ruta, "Errores segun el caudal",
             "Una peticion cuenta como fallida si devuelve 5xx, se corta o pasa de 30 s")


def grafica_recursos(csv_monitor: Path, ruta: Path, marcas: List[Dict[str, Any]]) -> None:
    """CPU y memoria de los tres servidores durante toda la sesion."""
    series: Dict[str, Dict[str, List[float]]] = {}
    with open(csv_monitor, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            d = series.setdefault(fila["proceso"], {"t": [], "cpu": [], "rss": []})
            d["t"].append(float(fila["t_s"]))
            d["cpu"].append(float(fila["cpu_pct"]))
            d["rss"].append(float(fila["rss_mb"]))
    if not series:
        return
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.6, 6.0), dpi=150, sharex=True)
    fig.patch.set_facecolor(FONDO)
    for ax in (ax1, ax2):
        ax.set_facecolor(SUPERFICIE)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            ax.spines[lado].set_color(LINEA)
        ax.tick_params(colors=TEXTO_2, labelsize=8.5)
        ax.grid(True, color=LINEA, linewidth=0.7, alpha=0.9)
        ax.set_axisbelow(True)
    for i, (nombre, d) in enumerate(sorted(series.items())):
        ax1.plot(d["t"], d["cpu"], color=PALETA[i], linewidth=1.5, label=nombre)
        ax2.plot(d["t"], d["rss"], color=PALETA[i], linewidth=1.5, label=nombre)
    for m in marcas:
        for ax in (ax1, ax2):
            ax.axvline(m["t"], color=TEXTO_2, linestyle=":", linewidth=1, alpha=0.5)
        ax1.text(m["t"], ax1.get_ylim()[1] * 0.97, " " + m["etiqueta"], rotation=90,
                 color=TEXTO_2, fontsize=7, va="top")
    ax1.set_ylabel("CPU (%)", color=TEXTO_2, fontsize=9)
    ax2.set_ylabel("memoria residente (MB)", color=TEXTO_2, fontsize=9)
    ax2.set_xlabel("segundos desde el inicio de la sesion de pruebas",
                   color=TEXTO_2, fontsize=9)
    leg = ax1.legend(facecolor=SUPERFICIE, edgecolor=LINEA, labelcolor=TEXTO_2,
                     fontsize=8.5, ncol=3)
    leg.get_frame().set_linewidth(0.8)
    fig.suptitle("Que hacian los servidores mientras tanto", color=TEXTO,
                 fontsize=12.5, x=0.012, ha="left", y=0.985, fontweight="medium")
    fig.text(0.012, 0.935, "Muestreado una vez por segundo con psutil, incluyendo procesos hijos",
             color=TEXTO_2, fontsize=9, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, facecolor=FONDO)
    plt.close(fig)


def grafica_resistencia(csv_muestras: Path, ruta: Path, ventana: int = 20) -> None:
    """Latencia a lo largo del tiempo: si sube y no baja, algo se degrada."""
    t: List[float] = []
    lat: List[float] = []
    with open(csv_muestras, encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            t.append(float(fila["t_rel_s"]))
            lat.append(float(fila["latencia_ms"]))
    if not t:
        return
    orden = sorted(range(len(t)), key=lambda i: t[i])
    t = [t[i] for i in orden]
    lat = [lat[i] for i in orden]
    # p95 movil
    p95_t, p95_v, p50_v = [], [], []
    for i in range(0, len(lat) - ventana, max(1, ventana // 2)):
        trozo = sorted(lat[i:i + ventana])
        p95_t.append(t[i + ventana // 2])
        p95_v.append(trozo[int(len(trozo) * 0.95)])
        p50_v.append(trozo[len(trozo) // 2])
    fig, ax = _lienzo(9.6, 3.8)
    ax.scatter(t, lat, s=3, color=ACENTO, alpha=0.22, linewidths=0)
    ax.plot(p95_t, p95_v, color=AVISO, linewidth=1.8, label=f"p95 movil ({ventana} peticiones)")
    ax.plot(p95_t, p50_v, color=OK, linewidth=1.8, label="p50 movil")
    ax.set_xlabel("segundos de prueba", color=TEXTO_2, fontsize=9)
    ax.set_ylabel("espera (ms)", color=TEXTO_2, fontsize=9)
    leg = ax.legend(facecolor=SUPERFICIE, edgecolor=LINEA, labelcolor=TEXTO_2, fontsize=8.5)
    leg.get_frame().set_linewidth(0.8)
    _guardar(fig, ruta, "Prueba de resistencia",
             "Cada punto es una peticion. Si la linea sube con el tiempo, el sistema se degrada")


def grafica_operaciones(por_operacion: List[Dict[str, Any]], ruta: Path,
                        titulo: str) -> None:
    """Que operacion cuesta mas: senala donde optimizar."""
    datos = sorted(por_operacion, key=lambda d: d["lat_p95_ms"])
    nombres = [d["operacion"] for d in datos]
    p50 = [d["lat_p50_ms"] for d in datos]
    p95 = [d["lat_p95_ms"] for d in datos]
    fig, ax = _lienzo(9.6, max(3.2, 0.42 * len(nombres) + 1.4))
    y = range(len(nombres))
    ax.barh([i + 0.19 for i in y], p95, height=0.36, color=AVISO, label="p95")
    ax.barh([i - 0.19 for i in y], p50, height=0.36, color=ACENTO, label="p50")
    ax.set_yticks(list(y))
    ax.set_yticklabels(nombres, fontsize=8.5)
    for i, v in enumerate(p95):
        ax.text(v, i + 0.19, f" {v:.0f}", color=TEXTO_2, fontsize=7.5, va="center")
    ax.set_xlabel("milisegundos", color=TEXTO_2, fontsize=9)
    leg = ax.legend(facecolor=SUPERFICIE, edgecolor=LINEA, labelcolor=TEXTO_2, fontsize=8.5)
    leg.get_frame().set_linewidth(0.8)
    _guardar(fig, ruta, titulo, "Ordenadas de la mas rapida a la mas lenta")


def tabla_markdown(filas: List[Dict[str, Any]], columnas: List[tuple]) -> str:
    cab = "| " + " | ".join(c[1] for c in columnas) + " |"
    sep = "|" + "|".join("---" for _ in columnas) + "|"
    cuerpo = []
    for f in filas:
        cuerpo.append("| " + " | ".join(
            str(c[2](f) if len(c) > 2 else f.get(c[0], "")) for c in columnas) + " |")
    return "\n".join([cab, sep, *cuerpo])

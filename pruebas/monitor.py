"""Vigila los servidores mientras se les da carga.

Sin esto, una prueba de carga solo dice "tardo X". Con esto se puede decir
*por que*: si el cuello es CPU, si la memoria crece y no vuelve (fuga), o si
la base de datos empieza a bloquear.
"""
from __future__ import annotations

import csv
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil


@dataclass
class Punto:
    t: float
    cpu_pct: float
    rss_mb: float
    hilos: int
    conexiones: int
    cpu_sistema_pct: float
    ram_sistema_pct: float


@dataclass
class Vigilancia:
    proceso: str
    puntos: List[Punto] = field(default_factory=list)

    def resumen(self) -> Dict[str, Any]:
        if not self.puntos:
            return {"proceso": self.proceso, "n": 0}
        cpu = [p.cpu_pct for p in self.puntos]
        rss = [p.rss_mb for p in self.puntos]
        # pendiente de la memoria: mide si crece y no vuelve
        n = len(rss)
        deriva = round(rss[-1] - rss[0], 1)
        return {
            "proceso": self.proceso,
            "muestras": n,
            "cpu_media_pct": round(sum(cpu) / n, 1),
            "cpu_max_pct": round(max(cpu), 1),
            "rss_inicial_mb": round(rss[0], 1),
            "rss_max_mb": round(max(rss), 1),
            "rss_final_mb": round(rss[-1], 1),
            "deriva_memoria_mb": deriva,
            "hilos_max": max(p.hilos for p in self.puntos),
            "conexiones_max": max(p.conexiones for p in self.puntos),
        }


class Monitor(threading.Thread):
    """Muestrea uno o varios procesos a intervalo fijo, en segundo plano."""

    def __init__(self, pids: Dict[str, int], intervalo: float = 1.0):
        super().__init__(daemon=True)
        self.intervalo = intervalo
        self._parar = threading.Event()
        self.vigilancias: Dict[str, Vigilancia] = {}
        self._procesos: Dict[str, psutil.Process] = {}
        for nombre, pid in pids.items():
            try:
                p = psutil.Process(pid)
                p.cpu_percent(None)          # primera lectura, se descarta
                self._procesos[nombre] = p
                self.vigilancias[nombre] = Vigilancia(nombre)
            except psutil.NoSuchProcess:
                pass
        # psutil.cpu_percent() mide *desde la llamada anterior sobre el mismo
        # objeto*. Si en cada muestra se vuelven a crear los objetos de los
        # procesos hijos, todas las lecturas son "la primera" y salen 0 %. Por
        # eso los hijos se guardan y se reutilizan.
        self._hijos: Dict[int, psutil.Process] = {}
        psutil.cpu_percent(None)
        self.t0 = time.perf_counter()

    def run(self) -> None:
        while not self._parar.wait(self.intervalo):
            t = time.perf_counter() - self.t0
            cpu_sis = psutil.cpu_percent(None)
            ram_sis = psutil.virtual_memory().percent
            for nombre, proc in list(self._procesos.items()):
                try:
                    with proc.oneshot():
                        # incluye los hijos: uvicorn --reload y los trabajadores
                        cpu = proc.cpu_percent(None)
                        rss = proc.memory_info().rss / 1e6
                        hilos = proc.num_threads()
                        vivos = set()
                        for hijo in proc.children(recursive=True):
                            vivos.add(hijo.pid)
                            guardado = self._hijos.get(hijo.pid)
                            if guardado is None:
                                guardado = hijo
                                guardado.cpu_percent(None)   # arranca el contador
                                self._hijos[hijo.pid] = guardado
                            try:
                                cpu += guardado.cpu_percent(None)
                                rss += guardado.memory_info().rss / 1e6
                                hilos += guardado.num_threads()
                            except psutil.Error:
                                self._hijos.pop(hijo.pid, None)
                        for muerto in set(self._hijos) - vivos:
                            self._hijos.pop(muerto, None)
                    try:
                        conexiones = len(proc.net_connections(kind="tcp"))
                    except (psutil.AccessDenied, psutil.Error):
                        conexiones = 0
                    self.vigilancias[nombre].puntos.append(
                        Punto(t, cpu, rss, hilos, conexiones, cpu_sis, ram_sis))
                except psutil.NoSuchProcess:
                    self._procesos.pop(nombre, None)

    def detener(self) -> Dict[str, Any]:
        self._parar.set()
        self.join(timeout=3)
        return {n: v.resumen() for n, v in self.vigilancias.items()}

    def guardar(self, ruta: Path) -> None:
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["proceso", "t_s", "cpu_pct", "rss_mb", "hilos",
                        "conexiones", "cpu_sistema_pct", "ram_sistema_pct"])
            for nombre, v in self.vigilancias.items():
                for p in v.puntos:
                    w.writerow([nombre, round(p.t, 2), round(p.cpu_pct, 1),
                                round(p.rss_mb, 1), p.hilos, p.conexiones,
                                round(p.cpu_sistema_pct, 1), round(p.ram_sistema_pct, 1)])


def pid_por_puerto(puerto: int) -> Optional[int]:
    """Encuentra el proceso que esta escuchando en un puerto."""
    for c in psutil.net_connections(kind="tcp"):
        if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == puerto:
            return c.pid
    return None

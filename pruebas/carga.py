"""Motor de carga: lanza peticiones concurrentes y mide lo que tarda cada una.

No usa ninguna herramienta externa (ni Locust ni JMeter): asyncio + httpx bastan
para el tamano de esta solucion y hacen la prueba reproducible con las mismas
dependencias que ya instala el proyecto.

Dos decisiones que cambian lo que se mide:

* **Llegadas de Poisson, no un bucle cerrado.** Un bucle cerrado ("N usuarios
  que piden, esperan la respuesta y vuelven a pedir") esconde la saturacion:
  si el servidor se frena, el generador tambien, y las latencias salen bonitas.
  Aqui las peticiones se programan a una tasa fija; si el servidor no da
  abasto, la cola crece y se ve.
* **Se mide la espera del usuario, no solo la del servidor.** El reloj arranca
  cuando la peticion *debia* salir, no cuando sale. Esa diferencia es el
  "coordinated omission" y es justo lo que se siente cuando un sistema empieza
  a ir mal.
"""
from __future__ import annotations

import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx


# --------------------------------------------------------------------------
# Definicion de lo que se pide
# --------------------------------------------------------------------------
@dataclass
class Peticion:
    """Una llamada al sistema, con su nombre de negocio."""
    nombre: str                     # "buscar contacto", "subir documento"...
    metodo: str
    url: str
    peso: float = 1.0               # cuanto sale respecto a las demas
    json_body: Optional[Any] = None
    datos: Optional[Callable[[], Dict[str, Any]]] = None   # cuerpo dinamico
    archivos: Optional[Callable[[], Dict[str, Any]]] = None
    esperado: Sequence[int] = (200, 201, 204)
    timeout: float = 30.0


@dataclass
class Muestra:
    """Lo que paso con una peticion."""
    nombre: str
    t_programado: float
    t_inicio: float
    t_fin: float
    estado: int
    bytes_recibidos: int = 0
    error: str = ""

    @property
    def latencia(self) -> float:
        """Lo que espero el usuario, desde que la peticion debia salir."""
        return self.t_fin - self.t_programado

    @property
    def servicio(self) -> float:
        """Lo que tardo el servidor una vez le llego la peticion."""
        return self.t_fin - self.t_inicio

    @property
    def espera_cola(self) -> float:
        return self.t_inicio - self.t_programado

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.estado < 400


@dataclass
class Resultado:
    escenario: str
    inicio: float
    fin: float
    muestras: List[Muestra] = field(default_factory=list)
    notas: Dict[str, Any] = field(default_factory=dict)

    # ---- agregados ----
    def resumen(self) -> Dict[str, Any]:
        return {"escenario": self.escenario, **self._stats(self.muestras),
                "duracion_s": round(self.fin - self.inicio, 2), **self.notas}

    def por_operacion(self) -> List[Dict[str, Any]]:
        nombres = sorted({m.nombre for m in self.muestras})
        return [{"operacion": n,
                 **self._stats([m for m in self.muestras if m.nombre == n])}
                for n in nombres]

    @staticmethod
    def _stats(muestras: List[Muestra]) -> Dict[str, Any]:
        if not muestras:
            return {"n": 0}
        lat = sorted(m.latencia for m in muestras)
        srv = sorted(m.servicio for m in muestras)
        fallidas = [m for m in muestras if not m.ok]
        duracion = max(m.t_fin for m in muestras) - min(m.t_programado for m in muestras)

        def pct(valores: List[float], p: float) -> float:
            if not valores:
                return 0.0
            k = min(len(valores) - 1, int(round(p / 100 * (len(valores) - 1))))
            return round(valores[k] * 1000, 1)

        errores: Dict[str, int] = {}
        for m in fallidas:
            clave = m.error or f"HTTP {m.estado}"
            errores[clave] = errores.get(clave, 0) + 1
        return {
            "n": len(muestras),
            "ok": len(muestras) - len(fallidas),
            "errores": len(fallidas),
            "tasa_error_pct": round(100 * len(fallidas) / len(muestras), 2),
            "rps": round(len(muestras) / duracion, 2) if duracion > 0 else 0,
            "lat_p50_ms": pct(lat, 50), "lat_p95_ms": pct(lat, 95),
            "lat_p99_ms": pct(lat, 99), "lat_max_ms": pct(lat, 100),
            "srv_p50_ms": pct(srv, 50), "srv_p95_ms": pct(srv, 95),
            "media_ms": round(statistics.fmean(lat) * 1000, 1),
            "detalle_errores": errores,
        }


# --------------------------------------------------------------------------
# Generador
# --------------------------------------------------------------------------
class Generador:
    """Programa peticiones a una tasa fija y las lanza sin esperarse a si mismo."""

    def __init__(self, base: str, peticiones: Sequence[Peticion], *,
                 semilla: int = 20260919, max_conexiones: int = 200):
        self.base = base.rstrip("/")
        self.peticiones = list(peticiones)
        self.total_peso = sum(p.peso for p in self.peticiones) or 1.0
        self.rnd = random.Random(semilla)
        self.max_conexiones = max_conexiones

    def _elegir(self) -> Peticion:
        objetivo = self.rnd.random() * self.total_peso
        acumulado = 0.0
        for p in self.peticiones:
            acumulado += p.peso
            if objetivo <= acumulado:
                return p
        return self.peticiones[-1]

    async def _una(self, cliente: httpx.AsyncClient, pet: Peticion,
                   t_programado: float, muestras: List[Muestra]) -> None:
        espera = t_programado - time.perf_counter()
        if espera > 0:
            await asyncio.sleep(espera)
        t0 = time.perf_counter()
        try:
            kwargs: Dict[str, Any] = {"timeout": pet.timeout}
            if pet.datos is not None:
                kwargs["json"] = pet.datos()
            elif pet.json_body is not None:
                kwargs["json"] = pet.json_body
            if pet.archivos is not None:
                kwargs["files"] = pet.archivos()
                kwargs.pop("json", None)
            url = pet.url if pet.url.startswith("http") else self.base + pet.url
            r = await cliente.request(pet.metodo, url, **kwargs)
            cuerpo = r.content
            muestras.append(Muestra(pet.nombre, t_programado, t0, time.perf_counter(),
                                    r.status_code, len(cuerpo),
                                    "" if r.status_code in pet.esperado
                                    else f"HTTP {r.status_code}"))
        except httpx.TimeoutException:
            muestras.append(Muestra(pet.nombre, t_programado, t0, time.perf_counter(),
                                    0, 0, "timeout"))
        except Exception as exc:                                   # red, cierre...
            muestras.append(Muestra(pet.nombre, t_programado, t0, time.perf_counter(),
                                    0, 0, type(exc).__name__))

    async def correr(self, *, rps: float, segundos: float,
                     escenario: str = "carga", poisson: bool = True) -> Resultado:
        """Lanza `rps` peticiones por segundo durante `segundos`."""
        limites = httpx.Limits(max_connections=self.max_conexiones,
                               max_keepalive_connections=self.max_conexiones)
        muestras: List[Muestra] = []
        inicio = time.perf_counter()
        tareas = []
        async with httpx.AsyncClient(limits=limites, follow_redirects=True) as cliente:
            t = inicio
            fin_previsto = inicio + segundos
            while t < fin_previsto:
                # intervalo exponencial => llegadas de Poisson, como el trafico real
                hueco = self.rnd.expovariate(rps) if poisson else 1.0 / rps
                t += hueco
                if t >= fin_previsto:
                    break
                tareas.append(asyncio.create_task(
                    self._una(cliente, self._elegir(), t, muestras)))
                # no dejar que la lista de tareas crezca sin control
                if len(tareas) > 20000:
                    await asyncio.gather(*tareas)
                    tareas = []
            if tareas:
                await asyncio.gather(*tareas)
        return Resultado(escenario, inicio, time.perf_counter(), muestras)

    async def rafaga(self, cuantas: int, *, escenario: str = "pico",
                     pet: Optional[Peticion] = None) -> Resultado:
        """Todas a la vez, desde reposo: el peor caso de concurrencia."""
        limites = httpx.Limits(max_connections=max(self.max_conexiones, cuantas),
                               max_keepalive_connections=cuantas)
        muestras: List[Muestra] = []
        inicio = time.perf_counter()
        async with httpx.AsyncClient(limits=limites, follow_redirects=True) as cliente:
            t = time.perf_counter()
            await asyncio.gather(*[
                self._una(cliente, pet or self._elegir(), t, muestras)
                for _ in range(cuantas)])
        return Resultado(escenario, inicio, time.perf_counter(), muestras,
                         {"concurrencia": cuantas})


def guardar_muestras(resultado: Resultado, ruta) -> None:
    """Una fila por peticion, para poder rehacer cualquier calculo."""
    import csv
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["escenario", "operacion", "t_rel_s", "latencia_ms",
                    "servicio_ms", "espera_cola_ms", "estado", "bytes", "error"])
        for m in sorted(resultado.muestras, key=lambda x: x.t_programado):
            w.writerow([resultado.escenario, m.nombre,
                        round(m.t_programado - resultado.inicio, 3),
                        round(m.latencia * 1000, 2), round(m.servicio * 1000, 2),
                        round(m.espera_cola * 1000, 2), m.estado,
                        m.bytes_recibidos, m.error])


def guardar_json(datos: Any, ruta) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Generador repartido en varios procesos
# --------------------------------------------------------------------------
# Un solo proceso de Python tiene un techo propio: por encima de ~200
# peticiones/s el bucle de eventos y el pool de conexiones del cliente se
# saturan antes que el servidor. Cuando eso pasa, lo que se mide es la
# herramienta, no el sistema. Se detecta mirando la CPU de los servidores: si
# estan al 11 % y las latencias se disparan, el cuello esta en el generador.
#
# La solucion es repartir la carga entre varios procesos del sistema
# operativo, uno por nucleo, y juntar despues las muestras.
def _trabajador(args):
    """Corre una parte de la carga en su propio proceso. Devuelve filas planas."""
    (peticiones_serializadas, rps, segundos, semilla, escenario) = args
    peticiones = [Peticion(**p) for p in peticiones_serializadas]
    gen = Generador("", peticiones, semilla=semilla)
    resultado = asyncio.run(gen.correr(rps=rps, segundos=segundos, escenario=escenario))
    return [(m.nombre, m.t_programado, m.t_inicio, m.t_fin, m.estado,
             m.bytes_recibidos, m.error) for m in resultado.muestras], \
           resultado.inicio, resultado.fin


def correr_repartido(peticiones: Sequence[Peticion], *, rps: float, segundos: float,
                     procesos: int, escenario: str = "carga") -> Resultado:
    """Reparte `rps` entre `procesos` generadores independientes."""
    import multiprocessing as mp

    planas = [{"nombre": p.nombre, "metodo": p.metodo, "url": p.url, "peso": p.peso,
               "esperado": tuple(p.esperado), "timeout": p.timeout}
              for p in peticiones if p.datos is None and p.archivos is None]
    tareas = [(planas, rps / procesos, segundos, 20260919 + i, escenario)
              for i in range(procesos)]
    with mp.get_context("spawn").Pool(procesos) as pool:
        partes = pool.map(_trabajador, tareas)

    muestras: List[Muestra] = []
    inicios, fines = [], []
    for filas, ini, fin in partes:
        inicios.append(ini)
        fines.append(fin)
        for nombre, tp, ti, tf, estado, bytes_, error in filas:
            muestras.append(Muestra(nombre, tp, ti, tf, estado, bytes_, error))
    return Resultado(escenario, min(inicios), max(fines), muestras,
                     {"procesos_generadores": procesos})

"""Arranca las tres aplicaciones, les aplica los escenarios y guarda todo."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import escenarios as esc
from .carga import (Generador, Peticion, Resultado, correr_repartido,
                    guardar_json, guardar_muestras)
from .monitor import Monitor, pid_por_puerto

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "pruebas"
SALIDA.mkdir(parents=True, exist_ok=True)

SERVIDORES = [
    ("video", "app.main:app", 8000),
    ("documentos", "docsai.main:app", 8100),
    ("contactos", "contactos.main:app", 8200),
]


# --------------------------------------------------------------------------
# Ciclo de vida de los servidores
# --------------------------------------------------------------------------
@dataclass
class Servidor:
    nombre: str
    puerto: int
    proceso: Optional[subprocess.Popen] = None
    externo: bool = False          # ya estaba corriendo, no lo apagamos

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.puerto}"


def _responde(puerto: int, timeout: float = 1.0) -> bool:
    try:
        r = httpx.get(f"http://127.0.0.1:{puerto}/", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


def arrancar(log_dir: Path, solo: Optional[List[str]] = None) -> List[Servidor]:
    """Levanta lo que no este levantado. Devuelve la lista con su estado."""
    log_dir.mkdir(parents=True, exist_ok=True)
    servidores: List[Servidor] = []
    for nombre, app, puerto in SERVIDORES:
        if solo and nombre not in solo:
            continue
        if _responde(puerto):
            print(f"  [ya corria]  {nombre:<11} puerto {puerto}")
            servidores.append(Servidor(nombre, puerto, None, externo=True))
            continue
        salida = open(log_dir / f"{nombre}.log", "w")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1",
             "--port", str(puerto), "--log-level", "warning"],
            cwd=str(RAIZ), stdout=salida, stderr=subprocess.STDOUT,
            start_new_session=True)
        servidores.append(Servidor(nombre, puerto, proc))
        print(f"  [arrancado]  {nombre:<11} puerto {puerto}  pid {proc.pid}")
    return servidores


def esperar_listos(servidores: List[Servidor], segundos: float = 45,
                   arranques: Optional[Dict[str, float]] = None) -> bool:
    """Espera a que respondan y, de paso, mide cuanto tardo cada una en hacerlo."""
    limite = time.time() + segundos
    t0 = time.time()
    pendientes = {s.nombre: s for s in servidores}
    while pendientes and time.time() < limite:
        for nombre, s in list(pendientes.items()):
            if _responde(s.puerto, timeout=2):
                if arranques is not None and not s.externo:
                    arranques[nombre] = round(time.time() - t0, 2)
                pendientes.pop(nombre)
        if pendientes:
            time.sleep(0.25)
    if pendientes:
        print(f"  [AVISO] no respondieron: {', '.join(pendientes)}")
        return False
    print("  todas las aplicaciones responden\n")
    return True


def detener(servidores: List[Servidor]) -> None:
    for s in servidores:
        if s.proceso and not s.externo:
            try:
                os.killpg(os.getpgid(s.proceso.pid), signal.SIGTERM)
                s.proceso.wait(timeout=10)
            except Exception:
                try:
                    s.proceso.kill()
                except Exception:
                    pass


def pids(servidores: List[Servidor]) -> Dict[str, int]:
    salida: Dict[str, int] = {}
    for s in servidores:
        pid = s.proceso.pid if s.proceso else pid_por_puerto(s.puerto)
        if pid:
            salida[s.nombre] = pid
    return salida


# --------------------------------------------------------------------------
# Arranque en frio y calentamiento
# --------------------------------------------------------------------------
PRIMERAS_LLAMADAS = [
    ("video · estado del sistema", f"{esc.VIDEO}/api/system"),
    ("video · panel en vivo", f"{esc.VIDEO}/api/metrics/live"),
    ("video · resumen", f"{esc.VIDEO}/api/metrics/summary"),
    ("documentos · metricas", f"{esc.DOCS}/api/metricas"),
    ("documentos · bandeja", f"{esc.DOCS}/api/documentos?limite=40"),
    ("contactos · metricas", f"{esc.CONTACTOS}/api/metricas"),
    ("contactos · buscar", f"{esc.CONTACTOS}/api/buscar?q=fry"),
    ("contactos · duplicados", f"{esc.CONTACTOS}/api/duplicados"),
]


def fijar_referencias() -> Dict[str, Any]:
    """Averigua contra que datos se va a medir, en vez de suponerlos.

    Devuelve una ficha y un expediente que existan de verdad. Si el sistema
    esta vacio lo dice en voz alta: medir busquedas contra una base sin datos
    no mide nada, y los 404 que salen no son fallos del sistema sino de la
    prueba.
    """
    persona_id = caso_id = 0
    total_personas = total_casos = 0
    with httpx.Client(timeout=30) as c:
        try:
            m = c.get(f"{esc.CONTACTOS}/api/metricas").json().get("resumen", {})
            total_personas = m.get("personas") or 0
            total_casos = m.get("casos") or 0
            # se elige la ficha con mas historia y el expediente con mas
            # partes: medir contra un registro vacio no dice nada del coste
            # real de abrir una ficha.
            recientes = c.get(f"{esc.CONTACTOS}/api/recientes?limite=25").json()
            if recientes:
                persona_id = max(recientes, key=lambda f: f.get("hitos") or 0)["id"]
            else:
                fichas = c.get(f"{esc.CONTACTOS}/api/personas?limite=1").json()
                persona_id = fichas[0]["id"] if fichas else 0
            casos = c.get(f"{esc.CONTACTOS}/api/casos?limite=50").json()
            if casos:
                caso_id = max(casos, key=lambda x: x.get("partes") or 0)["id"]
        except Exception as exc:
            print(f"    [aviso] no se pudo consultar el directorio: {exc}")

    listo = bool(persona_id and caso_id)
    if listo:
        print(f"    midiendo contra datos reales: {total_personas} fichas, "
              f"{total_casos} expedientes")
        print(f"    se usara la ficha con mas historia (#{persona_id}) y el "
              f"expediente con mas partes (#{caso_id})")
    else:
        print("    [AVISO] el directorio esta vacio. Las busquedas no mediran nada util.")
        print("            Para medir en condiciones, primero:  "
              "python scripts/contactos_demo.py --limpio")
    return {"persona_id": persona_id or 1, "caso_id": caso_id or 1,
            "con_datos": listo, "personas": total_personas, "casos": total_casos}


def arranque_en_frio() -> List[Dict[str, Any]]:
    """Lo que espera la primera persona del dia, pantalla por pantalla.

    Se mide antes de calentar nada: es la unica medida honesta del arranque en
    frio, y suele ser la peor experiencia real de un sistema poco cargado.
    """
    filas = []
    with httpx.Client(timeout=60) as c:
        for nombre, url in PRIMERAS_LLAMADAS:
            t0 = time.perf_counter()
            try:
                r = c.get(url)
                estado = r.status_code
            except Exception as exc:
                estado = 0
            ms = round((time.perf_counter() - t0) * 1000, 1)
            # segunda llamada: ya con todo en memoria
            t1 = time.perf_counter()
            try:
                c.get(url)
            except Exception:
                pass
            ms2 = round((time.perf_counter() - t1) * 1000, 1)
            filas.append({"pantalla": nombre, "primera_ms": ms, "segunda_ms": ms2,
                          "estado": estado})
            print(f"    {nombre:<30} {ms:>8.0f} ms   (repetida: {ms2:.0f} ms)")
    return filas


async def calentar(segundos: float = 5, refs: Optional[Dict[str, Any]] = None) -> None:
    """Trafico suave antes de medir, para que la escalada mida regimen estable."""
    refs = refs or {"persona_id": 26, "caso_id": 1}
    gen = Generador("", esc.con_consultas(
        esc.mezcla_oficina(refs["persona_id"], refs["caso_id"])))
    await gen.correr(rps=10, segundos=segundos, escenario="calentamiento")


# --------------------------------------------------------------------------
# Escenarios
# --------------------------------------------------------------------------
# Por encima de este caudal, un solo proceso generador deja de ser fiable y
# hay que repartir la carga. El numero salio de esta misma maquina: a 326 rps
# con un proceso, los servidores estaban al 11 % de CPU y las latencias se
# habian disparado — o sea, el que se ahogaba era el medidor.
TECHO_UN_PROCESO = 150.0


async def escalada(niveles: List[float], segundos: float,
                   procesos: int = 4,
                   refs: Optional[Dict[str, Any]] = None) -> List[Resultado]:
    """La misma mezcla de oficina a caudales crecientes, hasta que se note."""
    refs = refs or {"persona_id": 26, "caso_id": 1}
    peticiones = esc.con_consultas(
        esc.mezcla_oficina(refs["persona_id"], refs["caso_id"]))
    gen = Generador("", peticiones)
    salida: List[Resultado] = []
    for factor in niveles:
        rps = esc.RPS_NOMINAL * factor
        etiqueta = f"oficina x{factor:g}"
        reparte = rps > TECHO_UN_PROCESO
        marca = f" ({procesos} generadores)" if reparte else ""
        print(f"    {etiqueta:<16} {rps:7.1f} peticiones/s durante {segundos:g}s{marca} … ",
              end="", flush=True)
        if reparte:
            r = await asyncio.to_thread(
                correr_repartido, peticiones, rps=rps, segundos=segundos,
                procesos=procesos, escenario=etiqueta)
        else:
            r = await gen.correr(rps=rps, segundos=segundos, escenario=etiqueta)
        r.notas = {"factor": factor, "rps_objetivo": round(rps, 2),
                   "generadores": procesos if reparte else 1}
        s = r.resumen()
        print(f"p95 {s['lat_p95_ms']:>7.0f} ms · errores {s['tasa_error_pct']:>5.2f} % "
              f"· {s['rps']:.1f} rps reales")
        salida.append(r)
        await asyncio.sleep(3)      # dejar que el sistema vuelva a reposo
    return salida


async def rafagas(tamanos: List[int]) -> List[Resultado]:
    """Todas de golpe desde reposo: lo que pasa cuando entra una avalancha."""
    pet = Peticion("buscar contacto", "GET", f"{esc.CONTACTOS}/api/buscar?q=fry")
    gen = Generador("", [pet])
    salida = []
    for n in tamanos:
        print(f"    rafaga de {n:>4} simultaneas … ", end="", flush=True)
        r = await gen.rafaga(n, escenario=f"rafaga {n}", pet=pet)
        s = r.resumen()
        print(f"p95 {s['lat_p95_ms']:>7.0f} ms · max {s['lat_max_ms']:>7.0f} ms "
              f"· errores {s['tasa_error_pct']:>5.2f} %")
        salida.append(r)
        await asyncio.sleep(2)
    return salida


async def resistencia(rps: float, segundos: float,
                      refs: Optional[Dict[str, Any]] = None) -> Resultado:
    """Caudal sostenido: busca degradacion y fugas de memoria."""
    refs = refs or {"persona_id": 26, "caso_id": 1}
    peticiones = esc.con_consultas(
        esc.mezcla_oficina(refs["persona_id"], refs["caso_id"]))
    gen = Generador("", peticiones)
    print(f"    {segundos:g}s seguidos a {rps:.0f} peticiones/s … ", end="", flush=True)
    r = await gen.correr(rps=rps, segundos=segundos, escenario="resistencia")
    r.notas = {"rps_objetivo": rps}
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")
    return r


async def escrituras(rps: float, segundos: float,
                     refs: Optional[Dict[str, Any]] = None) -> Resultado:
    """Varias personas escribiendo a la vez en la misma base."""
    refs = refs or {"persona_id": 26}
    gen = Generador("", esc.mezcla_escrituras(refs["persona_id"]))
    print(f"    {segundos:g}s de escrituras concurrentes a {rps:.0f}/s … ",
          end="", flush=True)
    r = await gen.correr(rps=rps, segundos=segundos, escenario="escrituras")
    r.notas = {"rps_objetivo": rps}
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")
    return r


def tolerancia_errores(refs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Peticiones mal formadas, inexistentes o maliciosas, una a una."""
    refs = refs or {"persona_id": 26}
    filas: List[Dict[str, Any]] = []
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        for caso in esc.casos_borde(refs["persona_id"]):
            t0 = time.perf_counter()
            try:
                kw: Dict[str, Any] = {}
                if "json" in caso:
                    kw["json"] = caso["json"]
                if "crudo" in caso:
                    kw["content"] = caso["crudo"]
                    kw["headers"] = {"Content-Type": "application/json"}
                if "archivo" in caso:
                    nombre, datos, tipo = caso["archivo"]
                    campo = "file" if "/api/videos/" in caso["url"] else "files"
                    kw["files"] = {campo: (nombre, datos, tipo)}
                r = c.request(caso["metodo"], caso["url"], **kw)
                estado, cuerpo = r.status_code, r.text[:240]
            except Exception as exc:
                estado, cuerpo = 0, f"{type(exc).__name__}: {exc}"
            ms = round((time.perf_counter() - t0) * 1000, 1)
            correcto = estado in caso["esperado"]
            filas.append({"caso": caso["nombre"], "metodo": caso["metodo"],
                          "url": caso["url"].split("127.0.0.1:")[-1],
                          "esperado": "/".join(str(e) for e in caso["esperado"]),
                          "obtenido": estado, "ms": ms,
                          "correcto": correcto,
                          "quinientos": 500 <= estado < 600,
                          "respuesta": cuerpo.replace("\n", " ")[:160]})
            marca = "ok " if correcto else ("500" if 500 <= estado < 600 else "!! ")
            print(f"    [{marca}] {caso['nombre']:<46} -> {estado}")
    bien = sum(1 for f in filas if f["correcto"])
    quinientos = sum(1 for f in filas if f["quinientos"])
    return {"casos": filas, "total": len(filas), "correctos": bien,
            "errores_500": quinientos,
            "pct_correcto": round(100 * bien / max(1, len(filas)), 1)}


def integridad(base: str, refs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Comprueba que la base de datos sigue coherente despues de la paliza.

    Se compara contra lo que habia *antes* de empezar, no contra valores
    escritos a mano: asi la comprobacion vale igual con datos reales que con
    datos de ejemplo.
    """
    refs = refs or {}
    with httpx.Client(timeout=30) as c:
        m = c.get(f"{base}/api/metricas").json()["resumen"]
        ficha, caso = {}, {}
        if refs.get("persona_id"):
            r = c.get(f"{base}/api/personas/{refs['persona_id']}")
            ficha = r.json() if r.status_code == 200 else {}
        if refs.get("caso_id"):
            r = c.get(f"{base}/api/casos/{refs['caso_id']}")
            caso = r.json() if r.status_code == 200 else {}
    return {"personas": m.get("personas"), "casos": m.get("casos"),
            "hitos": m.get("hitos"),
            "medido_con_datos": bool(refs.get("con_datos")),
            "ficha_de_referencia": ficha.get("nombre") or "(no habia datos)",
            "ficha_sigue_ahi": bool(ficha.get("nombre")),
            "expediente_de_referencia": caso.get("expediente") or "(no habia datos)",
            "partes_del_expediente": len(caso.get("partes", []))}


def limpiar_datos_de_prueba() -> Dict[str, int]:
    """Borra lo que la propia prueba escribio.

    Una prueba de carga que deja basura en la base obliga a rehacer los datos
    de demostracion cada vez. Todo lo que escriben los escenarios lleva una
    marca ("Prueba de carga", "Carga Prueba"), asi que se puede quitar sin
    tocar nada real.
    """
    from contactos import db
    db.init_db()
    ids = [f["id"] for f in db.query(
        "SELECT id FROM personas WHERE organizacion='Prueba de carga' "
        "OR nombre LIKE 'Carga Prueba %' OR nombre LIKE 'Juan Perez'")]
    notas = db.execute(
        "DELETE FROM interacciones WHERE titulo LIKE 'Nota de prueba de carga%' "
        "OR detalle LIKE '%prueba de carga%'")
    for pid in ids:
        db.execute("DELETE FROM interacciones WHERE persona_id=?", (pid,))
        db.execute("DELETE FROM identificadores WHERE persona_id=?", (pid,))
        db.execute("DELETE FROM participaciones WHERE persona_id=?", (pid,))
        db.execute("DELETE FROM personas WHERE id=?", (pid,))
    db.cerrar()
    return {"fichas_borradas": len(ids), "notas_borradas": notas or 0}


async def video_en_proceso(video: Path, segundos_lectura: float = 40) -> Dict[str, Any]:
    """Sube un video y mide si el sistema sigue respondiendo mientras lo analiza.

    Es la prueba mas parecida a la realidad de la aplicacion de video: el
    trabajo pesado corre en segundo plano y alguien esta mirando el panel.
    """
    if not video.exists():
        return {"ejecutado": False, "motivo": f"no existe {video}"}
    with httpx.Client(timeout=120) as c:
        with open(video, "rb") as f:
            r = c.post(f"{esc.VIDEO}/api/videos/upload",
                       files={"file": (video.name, f, "video/mp4")})
        if r.status_code >= 400:
            return {"ejecutado": False, "motivo": f"HTTP {r.status_code}: {r.text[:200]}"}
        job = r.json().get("job", {})
        job_id = job.get("id") or job.get("job_id")

    print(f"    trabajo de video #{job_id} en marcha; midiendo el panel mientras tanto … ",
          end="", flush=True)
    pet = [Peticion("panel en vivo", "GET", f"{esc.VIDEO}/api/metrics/live", peso=3),
           Peticion("estado del trabajo", "GET", f"{esc.VIDEO}/api/jobs/{job_id}", peso=1),
           Peticion("buscar contacto", "GET", f"{esc.CONTACTOS}/api/buscar?q=fry", peso=2)]
    gen = Generador("", pet)
    r = await gen.correr(rps=5, segundos=segundos_lectura, escenario="video en proceso")
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")

    with httpx.Client(timeout=30) as c:
        estado = c.get(f"{esc.VIDEO}/api/jobs/{job_id}").json()
    return {"ejecutado": True, "job_id": job_id, "carga": s,
            "resultado": r,
            "trabajo": {k: estado.get(k) for k in
                        ("status", "progress", "frames", "fps", "message",
                         "processed", "duration")} }

"""Aplica los escenarios a ContactHub y guarda todo lo que sale.

Este modulo es el que decide *el orden* de la sesion: primero lo que solo se
puede medir una vez (el arranque en frio), luego la escalada, y al final las
pruebas que ensucian datos. Cada funcion imprime una linea por medida para
que el registro de la sesion se pueda leer sin abrir ningun JSON.
"""
from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from . import contacthub as ch
from . import escenarios as esc
from .carga import Generador, Peticion, Resultado, correr_repartido
from .monitor import pid_por_puerto

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "pruebas"
SALIDA.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Ciclo de vida del servidor
# --------------------------------------------------------------------------
def arrancar(log_dir: Path, pista: Optional[str] = None) -> Dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    proc, motivo = ch.arrancar(log_dir / "contacthub.log", pista)
    print(f"  ContactHub en {ch.BASE}: {motivo}")
    if proc is None and not ch.responde():
        return {"proceso": None, "motivo": motivo, "listo": False}
    tardo = ch.esperar(60)
    if tardo < 0:
        print("  [AVISO] ContactHub no contesta en /health")
        return {"proceso": proc, "motivo": motivo, "listo": False}
    if proc is not None:
        print(f"  tardo {tardo:.1f}s en contestar · pid {proc.pid}")
    return {"proceso": proc, "motivo": motivo, "listo": True,
            "arranque_s": tardo if proc is not None else None,
            "nuestro": proc is not None}


def detener(estado: Dict[str, Any]) -> None:
    proc = estado.get("proceso")
    if not proc:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def pids(estado: Dict[str, Any]) -> Dict[str, int]:
    proc = estado.get("proceso")
    pid = proc.pid if proc else pid_por_puerto(ch.PUERTO)
    return {"contacthub": pid} if pid else {}


# --------------------------------------------------------------------------
# Arranque en frio
# --------------------------------------------------------------------------
def primeras_llamadas(sesion) -> List[Dict[str, Any]]:
    cab = sesion.cabeceras()
    return [
        ("estado del servicio", f"{ch.BASE}/health", {}),
        ("quien soy", f"{ch.API}/auth/me", cab),
        ("resumen de la libreta", f"{ch.API}/stats", cab),
        ("primera pantalla de contactos", f"{ch.API}/contacts?limit=50&sort=name", cab),
        ("etiquetas del menu", f"{ch.API}/labels", cab),
        ("buscar un apellido", f"{ch.API}/contacts?q=Torres&limit=25", cab),
        ("posibles duplicados", f"{ch.API}/contacts/duplicates", cab),
        ("mi perfil", f"{ch.API}/me/profile", cab),
    ]


def arranque_en_frio(sesion) -> List[Dict[str, Any]]:
    """Lo que espera la primera persona del dia, pantalla por pantalla.

    Se mide antes de calentar nada. La segunda llamada va al lado para ver
    cuanto de la primera era arranque y cuanto es el coste real de la
    pantalla.
    """
    filas = []
    with httpx.Client(timeout=90) as c:
        for nombre, url, cab in primeras_llamadas(sesion):
            t0 = time.perf_counter()
            try:
                estado = c.get(url, headers=cab).status_code
            except Exception:
                estado = 0
            ms = round((time.perf_counter() - t0) * 1000, 1)
            t1 = time.perf_counter()
            try:
                c.get(url, headers=cab)
            except Exception:
                pass
            ms2 = round((time.perf_counter() - t1) * 1000, 1)
            filas.append({"pantalla": nombre, "primera_ms": ms,
                          "segunda_ms": ms2, "estado": estado})
            print(f"    {nombre:<32} {ms:>8.0f} ms   (repetida: {ms2:.0f} ms)"
                  + ("" if estado == 200 else f"   [HTTP {estado}]"))
    return filas


async def calentar(sesion, inv: Dict[str, Any], segundos: float = 6) -> None:
    gen = Generador("", esc.mezcla_oficina(inv), cabeceras=sesion.cabeceras())
    await gen.correr(rps=10, segundos=segundos, escenario="calentamiento")


# --------------------------------------------------------------------------
# Escenarios de carga
# --------------------------------------------------------------------------
# Por encima de este caudal un solo proceso generador deja de ser fiable: el
# bucle de eventos y el pool de conexiones se saturan antes que el servidor, y
# entonces lo que se mide es el medidor. Se detecta mirando la CPU del
# servidor: si esta al 11 % y las latencias se disparan, el cuello es nuestro.
TECHO_UN_PROCESO = 150.0


# Cuando un nivel devuelve mas de la mitad de las peticiones en error y la
# espera se cuenta en decenas de segundos, el sistema ya no esta lento: esta
# caido. Subir mas solo alarga la sesion — cada nivel por encima de la rodilla
# tarda minutos en drenar — y no anade informacion: ya se sabe que no aguanta.
UMBRAL_CAIDA_PCT = 50.0
UMBRAL_CAIDA_MS = 20_000


async def escalada(niveles: List[float], segundos: float, sesion,
                   inv: Dict[str, Any], procesos: int = 4) -> List[Resultado]:
    """La misma mezcla de oficina a caudales crecientes, hasta que se note."""
    peticiones = esc.mezcla_oficina(inv)
    salida: List[Resultado] = []
    for rps in niveles:
        etiqueta = f"oficina {rps:g}rps"
        reparte = rps > TECHO_UN_PROCESO
        marca = f" ({procesos} generadores)" if reparte else ""
        print(f"    {rps:>6.1f} peticiones/s  (x{esc.multiplo(rps):>5.0f} la hora punta) "
              f"durante {segundos:g}s{marca} … ", end="", flush=True)
        cab = sesion.cabeceras()
        gen = Generador("", peticiones, cabeceras=cab)
        if reparte:
            r = await asyncio.to_thread(
                correr_repartido, peticiones, rps=rps, segundos=segundos,
                procesos=procesos, escenario=etiqueta, cabeceras=cab)
        else:
            r = await gen.correr(rps=rps, segundos=segundos, escenario=etiqueta)
        r.notas = {"rps_objetivo": rps, "factor": round(esc.multiplo(rps), 1),
                   "generadores": procesos if reparte else 1}
        s = r.resumen()
        print(f"p95 {s['lat_p95_ms']:>7.0f} ms · errores {s['tasa_error_pct']:>5.2f} % "
              f"· {s['rps']:.1f} rps reales")
        salida.append(r)
        if (s["tasa_error_pct"] >= UMBRAL_CAIDA_PCT
                and s["lat_p95_ms"] >= UMBRAL_CAIDA_MS):
            print(f"\n    El sistema se cayo a {rps:g} peticiones/s "
                  f"({s['tasa_error_pct']:.1f} % de errores, p95 de "
                  f"{s['lat_p95_ms'] / 1000:.0f} s). No se sube mas: por encima")
            print("    de la rodilla cada nivel tarda minutos en drenar y no anade nada.")
            restantes = [n for n in niveles if n > rps]
            if restantes:
                print(f"    Niveles no ejecutados: "
                      + ", ".join(f"{n:g}" for n in restantes))
            r.notas["recuperacion_s"] = await esperar_a_que_se_recupere()
            break
        await asyncio.sleep(3)      # dejar que el sistema vuelva a reposo
    return salida


async def en_pie(etiqueta: str = "", segundos: float = 420) -> float:
    """Se asegura de que el servicio esta en pie ANTES de medir nada.

    No basta con esperar despues de la escalada: cualquier escenario que
    sature deja cola, y el siguiente mediria esa cola. Paso de verdad — las
    consultas caras saturan ya a 12 peticiones/s, y la prueba de resistencia
    que venia detras habria medido su resaca, no la resistencia.

    Si el servicio responde, esto no cuesta nada: una peticion a /health.
    """
    try:
        if httpx.get(f"{ch.BASE}/health", timeout=3).status_code == 200:
            return 0.0
    except Exception:
        pass
    print(f"    [{etiqueta}] el servicio viene tocado del escenario anterior; "
          f"esperando a que vuelva … ", end="", flush=True)
    return await esperar_a_que_se_recupere(segundos)


async def esperar_a_que_se_recupere(segundos: float = 420) -> float:
    """Espera a que /health vuelva a contestar antes de seguir midiendo.

    Despues de una caida quedan peticiones en cola dentro del servidor. Medir
    el siguiente escenario encima de esa cola mezclaria las dos cosas: la
    primera version de esto esperaba dos minutos, no bastaban, y las rafagas
    salieron con un 100 % de errores que no eran suyos.

    El tiempo que devuelve es en si mismo una medida: cuanto tarda el
    servicio en volver en pie despues de 20 segundos de sobrecarga.
    """
    print("    esperando a que el servicio se recupere … ", end="", flush=True)
    t0 = time.perf_counter()
    limite = t0 + segundos
    while time.perf_counter() < limite:
        try:
            r = httpx.get(f"{ch.BASE}/health", timeout=3)
            if r.status_code == 200:
                tardo = time.perf_counter() - t0
                print(f"listo en {tardo:.0f}s")
                return round(tardo, 1)
        except Exception:
            pass
        await asyncio.sleep(2)
    print("sigue sin contestar")
    return -1.0


async def rafagas(tamanos: List[int], sesion, inv: Dict[str, Any]) -> List[Resultado]:
    """Todas de golpe desde reposo: lo que pasa cuando entra una avalancha."""
    texto = (inv.get("textos") or ["Torres"])[0]
    pet = Peticion("buscar por texto", "GET",
                   f"{ch.API}/contacts?q={esc._cita(texto)}&limit=25", timeout=60)
    salida = []
    for n in tamanos:
        gen = Generador("", [pet], cabeceras=sesion.cabeceras(), max_conexiones=n)
        print(f"    rafaga de {n:>4} simultaneas … ", end="", flush=True)
        r = await gen.rafaga(n, escenario=f"rafaga {n}", pet=pet)
        s = r.resumen()
        print(f"p95 {s['lat_p95_ms']:>7.0f} ms · max {s['lat_max_ms']:>7.0f} ms "
              f"· errores {s['tasa_error_pct']:>5.2f} %")
        salida.append(r)
        if s["tasa_error_pct"] >= UMBRAL_CAIDA_PCT:
            restantes = [t for t in tamanos if t > n]
            print(f"\n    Con {n} simultaneas ya falla mas de la mitad. No se sube mas"
                  + (f" (quedaban {', '.join(str(t) for t in restantes)})." if restantes else "."))
            await esperar_a_que_se_recupere()
            break
        await asyncio.sleep(2)
    return salida


async def resistencia(rps: float, segundos: float, sesion,
                      inv: Dict[str, Any]) -> Resultado:
    """Caudal sostenido: busca degradacion lenta y fugas de memoria."""
    gen = Generador("", esc.mezcla_oficina(inv), cabeceras=sesion.cabeceras())
    print(f"    {segundos:g}s seguidos a {rps:.0f} peticiones/s … ", end="", flush=True)
    r = await gen.correr(rps=rps, segundos=segundos, escenario="resistencia")
    r.notas = {"rps_objetivo": rps}
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")
    return r


async def escrituras(rps: float, segundos: float, sesion,
                     inv: Dict[str, Any]) -> Resultado:
    """Varias personas dando de alta y corrigiendo a la vez."""
    gen = Generador("", esc.mezcla_escrituras(inv), cabeceras=sesion.cabeceras())
    print(f"    {segundos:g}s de escrituras concurrentes a {rps:.0f}/s … ",
          end="", flush=True)
    r = await gen.correr(rps=rps, segundos=segundos, escenario="escrituras")
    r.notas = {"rps_objetivo": rps}
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")
    return r


async def busqueda_dura(rps: float, segundos: float, sesion,
                        inv: Dict[str, Any]) -> Resultado:
    """Solo las consultas caras, para ver cual es la que se rompe primero."""
    gen = Generador("", esc.mezcla_busqueda_dura(inv), cabeceras=sesion.cabeceras())
    print(f"    {segundos:g}s de consultas caras a {rps:.0f}/s … ", end="", flush=True)
    r = await gen.correr(rps=rps, segundos=segundos, escenario="busqueda dura")
    r.notas = {"rps_objetivo": rps}
    s = r.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")
    return r


async def importacion_en_curso(sesion, inv: Dict[str, Any], cuantos: int = 3000,
                               segundos_lectura: float = 40) -> Dict[str, Any]:
    """Una importacion grande mientras la oficina sigue buscando.

    Es el trabajo mas pesado que hace ContactHub: parsea el CSV, normaliza
    telefonos y correos, busca duplicados y escribe miles de filas — todo en
    segundo plano, dentro del mismo proceso. La pregunta que responde este
    escenario es si la libreta se queda inservible mientras tanto.
    """
    datos = ch.csv_de_siembra(cuantos, desde=900000)   # rango propio: se borra despues
    with httpx.Client(timeout=180) as c:
        r = c.post(f"{ch.API}/imports/google-csv", headers=sesion.cabeceras(),
                   files={"file": ("importacion_grande.csv", datos, "text/csv")},
                   data={"on_conflict": "fill_missing"})
    if r.status_code != 202:
        return {"ejecutado": False,
                "motivo": f"la importacion respondio HTTP {r.status_code}: {r.text[:200]}"}
    job = r.json().get("id")
    print(f"    importacion de {cuantos} contactos en marcha (#{str(job)[:8]}); "
          f"midiendo la libreta mientras tanto … ", end="", flush=True)

    gen = Generador("", esc.mezcla_oficina(inv), cabeceras=sesion.cabeceras())
    res = await gen.correr(rps=10, segundos=segundos_lectura,
                           escenario="importacion en curso")
    s = res.resumen()
    print(f"p95 {s['lat_p95_ms']:.0f} ms · errores {s['tasa_error_pct']:.2f} %")

    estado: Dict[str, Any] = {}
    with httpx.Client(timeout=60) as c:
        limite = time.time() + 180
        while time.time() < limite:
            j = c.get(f"{ch.API}/imports/{job}", headers=sesion.cabeceras())
            if j.status_code == 200:
                estado = j.json()
                if estado.get("status") in ("completed", "failed"):
                    break
            time.sleep(1)
    return {"ejecutado": True, "job_id": str(job), "contactos": cuantos,
            "carga": s, "resultado": res,
            "trabajo": {k: estado.get(k) for k in
                        ("status", "total", "created", "updated", "unchanged",
                         "deleted", "error_message")}}


# --------------------------------------------------------------------------
# Tolerancia a errores
# --------------------------------------------------------------------------
def tolerancia_errores(inv: Dict[str, Any], sesion) -> Dict[str, Any]:
    filas: List[Dict[str, Any]] = []
    with httpx.Client(timeout=60, follow_redirects=False) as c:
        for caso in esc.casos_borde(inv, sesion):
            t0 = time.perf_counter()
            try:
                kw: Dict[str, Any] = {"headers": dict(caso.get("cabeceras") or {})}
                if "json" in caso:
                    kw["json"] = caso["json"]
                if "crudo" in caso:
                    kw["content"] = caso["crudo"]
                if "archivo" in caso:
                    nombre, datos, tipo = caso["archivo"]
                    kw["files"] = {"file": (nombre, datos, tipo)}
                    kw.pop("json", None)
                r = c.request(caso["metodo"], caso["url"], **kw)
                estado, cuerpo = r.status_code, r.text[:240]
            except Exception as exc:
                estado, cuerpo = 0, f"{type(exc).__name__}: {exc}"
            ms = round((time.perf_counter() - t0) * 1000, 1)
            correcto = estado in caso["esperado"]
            filas.append({"caso": caso["nombre"], "metodo": caso["metodo"],
                          "url": caso["url"].replace(ch.BASE, "")[:120],
                          "esperado": "/".join(str(e) for e in caso["esperado"]),
                          "obtenido": estado, "ms": ms, "correcto": correcto,
                          "quinientos": 500 <= estado < 600,
                          "respuesta": cuerpo.replace("\n", " ")[:160]})
            marca = "ok " if correcto else ("500" if 500 <= estado < 600 else "!! ")
            print(f"    [{marca}] {caso['nombre']:<48} -> {estado}")
    bien = sum(1 for f in filas if f["correcto"])
    return {"casos": filas, "total": len(filas), "correctos": bien,
            "errores_500": sum(1 for f in filas if f["quinientos"]),
            "pct_correcto": round(100 * bien / max(1, len(filas)), 1)}


def cerrojo() -> Dict[str, Any]:
    r = esc.cerrojo_de_intentos()
    if r["bloquea"]:
        print(f"    [ok ] la puerta se cierra al intento "
              f"{r['corta_despues_de'] + 1} (HTTP 429)")
    else:
        print(f"    [!! ] 7 intentos fallidos seguidos y ninguno fue rechazado: "
              f"{r['codigos']}")
    return r


# --------------------------------------------------------------------------
# Integridad
# --------------------------------------------------------------------------
def integridad(sesion, inv: Dict[str, Any]) -> Dict[str, Any]:
    """Comprueba que la libreta sigue coherente despues de la paliza.

    Se compara contra el inventario tomado *antes* de empezar, no contra
    numeros escritos a mano: asi la comprobacion vale con cualquier libreta.
    """
    ids = inv.get("ids") or []
    con = {}
    with httpx.Client(timeout=60) as c:
        cab = sesion.cabeceras()
        s = c.get(f"{ch.API}/stats", headers=cab)
        stats = s.json() if s.status_code == 200 else {}
        vivos = 0
        for i in ids[:25]:
            if c.get(f"{ch.API}/contacts/{i}", headers=cab).status_code == 200:
                vivos += 1
        if ids:
            r = c.get(f"{ch.API}/contacts/{ids[0]}", headers=cab)
            con = r.json() if r.status_code == 200 else {}
        salud = c.get(f"{ch.BASE}/health").status_code
    return {"contactos_antes": inv.get("total"),
            "contactos_ahora": stats.get("total"),
            "en_la_papelera": stats.get("in_trash"),
            "con_correo": stats.get("with_email"),
            "con_telefono": stats.get("with_phone"),
            "fichas_de_referencia_vivas": f"{vivos}/{len(ids[:25])}",
            "ficha_de_referencia": con.get("display_name") or "(sin datos)",
            "servicio_responde": salud == 200}


def limpiar(sesion) -> Dict[str, int]:
    return ch.limpiar(sesion)

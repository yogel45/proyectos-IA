#!/usr/bin/env python3
"""Pruebas de trafico, carga y tolerancia a errores de las tres aplicaciones.

    python run_pruebas.py                 # sesion completa (~9 minutos)
    python run_pruebas.py --rapido        # version corta (~2 minutos)
    python run_pruebas.py --solo errores  # solo la bateria de casos borde
    python run_pruebas.py --check         # comprobar el entorno y salir

Arranca las aplicaciones que no esten corriendo, les aplica los escenarios,
vigila CPU y memoria de cada servidor, y deja en data/pruebas/ los datos en
crudo (una fila por peticion), el resumen en JSON y las graficas.

No hace falta ninguna herramienta externa: se usa httpx (ya instalado con
FastAPI) y psutil. El detalle del escenario y su justificacion esta en
docs/RETO7_PRUEBAS.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

REQUERIDOS = [("httpx", "httpx"), ("psutil", "psutil"), ("matplotlib", "matplotlib")]


def check_env() -> bool:
    ok = True
    print("== Dependencias de las pruebas ==")
    for modulo, paquete in REQUERIDOS:
        try:
            __import__(modulo)
            print(f"  [ok]    {paquete}")
        except ImportError:
            ok = False
            print(f"  [FALTA] {paquete}  ->  pip install {paquete}")
    try:
        import psutil
        print(f"\n== Maquina ==\n  {platform.system()} {platform.release()} · "
              f"Python {platform.python_version()}")
        print(f"  {psutil.cpu_count(logical=True)} nucleos logicos · "
              f"{psutil.virtual_memory().total / 1e9:.1f} GB de RAM")
    except ImportError:
        pass
    return ok


def _titulo(texto: str) -> None:
    print(f"\n{texto}\n{'─' * len(texto)}")


async def sesion(args) -> int:
    from pruebas import escenarios as esc
    from pruebas import orquesta as orq
    from pruebas import reporte as rep
    from pruebas.carga import guardar_json, guardar_muestras
    from pruebas.monitor import Monitor

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = orq.SALIDA / sello
    salida.mkdir(parents=True, exist_ok=True)
    img = RAIZ / "docs" / "img"
    marcas: List[Dict[str, Any]] = []
    informe: Dict[str, Any] = {"sello": sello, "maquina": _maquina(),
                               "rps_nominal": round(esc.RPS_NOMINAL, 3),
                               "justificacion": {
                                   "pico_llamadas_hora": esc.PICO_LLAMADAS_HORA,
                                   "mediana_llamadas_hora": esc.MEDIANA_LLAMADAS_HORA,
                                   "empleados": esc.EMPLEADOS,
                                   "paneles_abiertos": esc.PANELES_ABIERTOS}}

    _titulo("Arrancando las aplicaciones")
    arranques: Dict[str, float] = {}
    servidores = orq.arrancar(salida / "logs")
    if not orq.esperar_listos(servidores, arranques=arranques):
        orq.detener(servidores)
        return 1
    if arranques:
        informe["arranque_s"] = arranques
        print("  tiempo hasta responder: " +
              " · ".join(f"{k} {v:.1f}s" for k, v in arranques.items()) + "\n")

    monitor = Monitor(orq.pids(servidores), intervalo=1.0)
    monitor.start()
    t0 = time.perf_counter()

    def marca(etiqueta: str) -> None:
        marcas.append({"t": round(time.perf_counter() - t0, 1), "etiqueta": etiqueta})

    try:
        solo = set(args.solo or [])

        # ---------------- 0. Arranque en frio ----------------
        _titulo("0. Arranque en frio: lo que espera la primera persona del dia")
        marca("frio")
        informe["arranque_frio"] = orq.arranque_en_frio()
        print("\n    calentando antes de medir en regimen estable …")
        await orq.calentar(3 if args.rapido else 6)

        # ---------------- 1. Escalada ----------------
        if not solo or "escalada" in solo:
            _titulo("1. Escalada: la hora pico real, multiplicada")
            print(f"    carga nominal medida = {esc.RPS_NOMINAL:.2f} peticiones/s "
                  f"({esc.PICO_LLAMADAS_HORA} llamadas en la hora pico real, "
                  f"{esc.PANELES_ABIERTOS} paneles abiertos)\n")
            marca("escalada")
            niveles = ([1, 10, 50] if args.rapido else
                       [1, 5, 10, 25, 50, 100, 150, 200, 245, 300])
            segundos = 6 if args.rapido else 20
            resultados = await orq.escalada(niveles, segundos)
            resumenes = []
            for r in resultados:
                guardar_muestras(r, salida / f"muestras_{r.escenario.replace(' ', '_')}.csv")
                resumenes.append({**r.resumen(), "factor": r.notas["factor"]})
            informe["escalada"] = resumenes
            rep.grafica_escalada(resumenes, img / "carga-escalada.png", esc.RPS_NOMINAL)
            rep.grafica_errores(resumenes, img / "carga-errores.png")
            rep.grafica_caudal(resumenes, img / "carga-caudal.png")
            peor = resultados[-1]
            rep.grafica_operaciones(peor.por_operacion(), img / "carga-operaciones.png",
                                    f"Coste de cada operacion bajo {peor.escenario}")
            informe["por_operacion_maxima"] = peor.por_operacion()

        # ---------------- 2. Rafagas ----------------
        if not solo or "rafaga" in solo:
            _titulo("2. Rafaga: todas a la vez desde reposo")
            marca("rafagas")
            tam = [50, 200] if args.rapido else [10, 50, 100, 250, 500]
            resultados = await orq.rafagas(tam)
            informe["rafagas"] = [{**r.resumen(), "concurrencia": r.notas["concurrencia"]}
                                  for r in resultados]
            for r in resultados:
                guardar_muestras(r, salida / f"muestras_{r.escenario.replace(' ', '_')}.csv")

        # ---------------- 3. Escrituras ----------------
        if not solo or "escrituras" in solo:
            _titulo("3. Escrituras concurrentes sobre la misma base")
            marca("escrituras")
            r = await orq.escrituras(rps=30 if args.rapido else 60,
                                     segundos=8 if args.rapido else 25)
            guardar_muestras(r, salida / "muestras_escrituras.csv")
            informe["escrituras"] = r.resumen()
            informe["escrituras_por_operacion"] = r.por_operacion()
            rep.grafica_operaciones(r.por_operacion(), img / "carga-escrituras.png",
                                    "Coste de cada escritura con 60 peticiones/s")

        # ---------------- 4. Resistencia ----------------
        if not solo or "resistencia" in solo:
            _titulo("4. Resistencia: caudal sostenido")
            marca("resistencia")
            r = await orq.resistencia(rps=50, segundos=20 if args.rapido else 120)
            guardar_muestras(r, salida / "muestras_resistencia.csv")
            informe["resistencia"] = r.resumen()
            rep.grafica_resistencia(salida / "muestras_resistencia.csv",
                                    img / "carga-resistencia.png")

        # ---------------- 5. Video en proceso ----------------
        if (not solo or "video" in solo) and not args.sin_video:
            _titulo("5. Trabajo de video pesado mientras se consulta")
            marca("video")
            video = _buscar_video()
            resultado = await orq.video_en_proceso(
                video, segundos_lectura=15 if args.rapido else 40)
            if resultado.get("ejecutado"):
                guardar_muestras(resultado.pop("resultado"),
                                 salida / "muestras_video.csv")
                informe["video"] = resultado
                print(f"    trabajo: {resultado['trabajo']}")
            else:
                resultado.pop("resultado", None)
                informe["video"] = resultado
                print(f"    [omitido] {resultado.get('motivo')}")

        # ---------------- 6. Tolerancia a errores ----------------
        if not solo or "errores" in solo:
            _titulo("6. Tolerancia a errores: peticiones mal formadas")
            marca("errores")
            informe["tolerancia"] = orq.tolerancia_errores()
            t = informe["tolerancia"]
            print(f"\n    {t['correctos']}/{t['total']} respondieron como debian "
                  f"· {t['errores_500']} errores 500")

        # ---------------- 7. Integridad ----------------
        _titulo("7. Integridad de los datos despues de la paliza")
        marca("integridad")
        informe["integridad"] = orq.integridad(esc.CONTACTOS)
        for k, v in informe["integridad"].items():
            print(f"    {k:<22} {v}")

    finally:
        recursos = monitor.detener()
        monitor.guardar(salida / "recursos.csv")
        informe["recursos"] = recursos
        informe["marcas"] = marcas
        informe["duracion_total_s"] = round(time.perf_counter() - t0, 1)
        guardar_json(informe, salida / "informe.json")
        try:
            rep.grafica_recursos(salida / "recursos.csv", img / "carga-recursos.png", marcas)
        except Exception as exc:
            print(f"  [aviso] no se pudo dibujar la grafica de recursos: {exc}")
        orq.detener(servidores)
        try:
            informe["limpieza"] = orq.limpiar_datos_de_prueba()
            print(f"\n  Limpieza: {informe['limpieza']['fichas_borradas']} fichas y "
                  f"{informe['limpieza']['notas_borradas']} notas de prueba retiradas")
        except Exception as exc:
            print(f"  [aviso] no se pudo limpiar lo que escribio la prueba: {exc}")
        guardar_json(informe, salida / "informe.json")

    _titulo("Resultado")
    for nombre, r in recursos.items():
        print(f"    {nombre:<11} CPU media {r.get('cpu_media_pct', 0):>5.1f} % · "
              f"pico {r.get('cpu_max_pct', 0):>5.1f} % · memoria "
              f"{r.get('rss_inicial_mb', 0):.0f} → {r.get('rss_final_mb', 0):.0f} MB "
              f"(deriva {r.get('deriva_memoria_mb', 0):+.1f} MB)")
    print(f"\n    Datos en crudo y resumen : {salida}")
    print(f"    Graficas                 : {img}/carga-*.png")
    print(f"    Duracion total           : {informe['duracion_total_s']:.0f} s")

    # copia estable de los CSV para la documentacion
    destino = RAIZ / "docs" / "resultados"
    destino.mkdir(parents=True, exist_ok=True)
    for origen, nombre in ((salida / "recursos.csv", "carga-recursos.csv"),
                           (salida / "muestras_resistencia.csv", "carga-resistencia.csv"),
                           (salida / "informe.json", "carga-informe.json")):
        if origen.exists():
            destino.joinpath(nombre).write_bytes(origen.read_bytes())
    return 0


def _maquina() -> Dict[str, Any]:
    import psutil
    return {"sistema": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "nucleos": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1)}


def _buscar_video() -> Path:
    for patron in ("data/uploads/*.mp4", "sample_data/*.mp4", "*.mp4"):
        for ruta in sorted(RAIZ.glob(patron)):
            return ruta
    return RAIZ / "sample_data" / "demo.mp4"


def main() -> int:
    parser = argparse.ArgumentParser(description="Pruebas de carga del proyecto")
    parser.add_argument("--rapido", action="store_true",
                        help="version corta, para comprobar que todo funciona")
    parser.add_argument("--solo", nargs="*",
                        choices=["escalada", "rafaga", "escrituras", "resistencia",
                                 "video", "errores"],
                        help="ejecutar solo algunos escenarios")
    parser.add_argument("--sin-video", action="store_true",
                        help="omitir la prueba de video (es la mas lenta)")
    parser.add_argument("--check", action="store_true", help="solo diagnostico")
    args = parser.parse_args()

    if args.check:
        return 0 if check_env() else 1
    if not check_env():
        print("\nInstala lo que falta con:  pip install -r requirements.txt")
        return 1
    return asyncio.run(sesion(args))


if __name__ == "__main__":
    raise SystemExit(main())

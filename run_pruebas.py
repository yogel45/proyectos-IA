#!/usr/bin/env python3
"""Reto 7 — Pruebas de trafico, carga y actividad automatizada sobre ContactHub.

    python run_pruebas.py                  # sesion completa (~10 minutos)
    python run_pruebas.py --rapido         # version corta (~2 minutos)
    python run_pruebas.py --solo errores   # solo la bateria de casos borde
    python run_pruebas.py --check          # comprobar el entorno y salir
    python run_pruebas.py --ruta C:\\ruta\\a\\ContactHub

Arranca ContactHub si no estaba corriendo, abre sesion con una cuenta de
pruebas, siembra la libreta con contactos sacados de los archivos reales de
la oficina, le aplica los escenarios, vigila CPU y memoria del servidor, y
deja en data/pruebas/<fecha>/ los datos en crudo (una fila por peticion), el
resumen en JSON, el registro completo de la sesion y las graficas.

No hace falta ninguna herramienta externa: se usa httpx (que ya instala
FastAPI), psutil y matplotlib. El detalle del escenario y su justificacion
esta en docs/RETO7_PRUEBAS.md.
"""
from __future__ import annotations

import argparse
import asyncio
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

REQUERIDOS = [("httpx", "httpx"), ("psutil", "psutil"),
              ("matplotlib", "matplotlib"), ("openpyxl", "openpyxl")]


def check_env(pista: str = "") -> bool:
    ok = True
    print("== Dependencias de las pruebas ==")
    for modulo, paquete in REQUERIDOS:
        try:
            __import__(modulo)
            print(f"  [ok]    {paquete}")
        except ImportError:
            ok = False
            print(f"  [FALTA] {paquete}  ->  pip install {paquete}")

    from pruebas import contacthub as ch
    print("\n== ContactHub ==")
    if ch.responde():
        print(f"  [ok]    ya esta respondiendo en {ch.BASE}")
    else:
        carpeta = ch.localizar(pista or None)
        if carpeta:
            print(f"  [ok]    carpeta encontrada: {carpeta}")
            print(f"          se arrancara sola en el puerto {ch.PUERTO}")
        else:
            ok = False
            print("  [FALTA] no encuentro ContactHub y no responde en "
                  f"{ch.BASE}")
            print("          arrancalo con su iniciar.bat, o indica la carpeta:")
            print("          python run_pruebas.py --ruta <carpeta de ContactHub>")
    try:
        import psutil
        print(f"\n== Maquina ==\n  {platform.system()} {platform.release()} · "
              f"Python {platform.python_version()}")
        print(f"  {psutil.cpu_count(logical=True)} nucleos logicos · "
              f"{psutil.virtual_memory().total / 1e9:.1f} GB de RAM")
    except ImportError:
        pass
    return ok


class _Registro:
    """Duplica todo lo que sale por pantalla a un archivo.

    El reto pide entregar registros, y el mas util es la transcripcion
    completa de la sesion: dice que se ejecuto, en que orden y con que
    resultado, sin tener que fiarse del resumen.
    """

    def __init__(self, destino: Path):
        destino.parent.mkdir(parents=True, exist_ok=True)
        self._archivo = open(destino, "w", encoding="utf-8")
        self._pantalla = sys.stdout

    def write(self, texto: str) -> int:
        self._pantalla.write(texto)
        self._archivo.write(texto)
        return len(texto)

    def flush(self) -> None:
        self._pantalla.flush()
        self._archivo.flush()

    def cerrar(self) -> None:
        sys.stdout = self._pantalla
        self._archivo.close()


def _titulo(texto: str) -> None:
    print(f"\n{texto}\n{'─' * len(texto)}")


async def sesion(args) -> int:
    from pruebas import contacthub as ch
    from pruebas import escenarios as esc
    from pruebas import orquesta as orq
    from pruebas import reporte as rep
    from pruebas.carga import guardar_json, guardar_muestras
    from pruebas.monitor import Monitor

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = orq.SALIDA / sello
    salida.mkdir(parents=True, exist_ok=True)
    # una sesion parcial dibuja en su propia carpeta, no sobre las del repositorio
    completa = not (args.rapido or args.solo or args.sin_importacion)
    img = (RAIZ / "docs" / "img") if completa else (salida / "img")
    img.mkdir(parents=True, exist_ok=True)

    marcas: List[Dict[str, Any]] = []
    informe: Dict[str, Any] = {
        "sello": sello, "sistema_probado": "ContactHub", "base": ch.BASE,
        "maquina": _maquina(),
        "rps_nominal": round(esc.RPS_NOMINAL, 4),
        "justificacion": {"pico_llamadas_hora": esc.PICO_LLAMADAS_HORA,
                          "mediana_llamadas_hora": esc.MEDIANA_LLAMADAS_HORA,
                          "empleados": esc.EMPLEADOS,
                          "pantallas_abiertas": esc.PANTALLAS_ABIERTAS,
                          "hora_punta": esc.HORA_PUNTA,
                          "peticiones_hora_punta": sum(esc.HORA_PUNTA.values())}}

    registro = _Registro(salida / "registro.txt")
    sys.stdout = registro
    print(f"Sesion de pruebas {sello} — sistema probado: ContactHub ({ch.BASE})")
    print(f"Maquina: {informe['maquina']}")
    print(f"Carga nominal derivada de los datos reales de la oficina: "
          f"{esc.RPS_NOMINAL:.3f} peticiones/s "
          f"({sum(esc.HORA_PUNTA.values())} peticiones en la hora punta)")

    _titulo("Arrancando ContactHub")
    estado = orq.arrancar(salida / "logs", args.ruta)
    if not estado["listo"]:
        print("\n  No se pudo llegar a ContactHub. Arrancalo con su iniciar.bat")
        print("  y vuelve a lanzar esto, o indica donde esta:")
        print("      python run_pruebas.py --ruta <carpeta de ContactHub>")
        registro.cerrar()
        return 1
    informe["servidor"] = {k: v for k, v in estado.items() if k != "proceso"}

    _titulo("Abriendo sesion")
    acceso = ch.Sesion()
    apertura = acceso.abrir()
    if not apertura.get("ok"):
        print(f"  [ERROR] {apertura.get('motivo')}")
        registro.cerrar()
        orq.detener(estado)
        return 1
    print(f"  cuenta {acceso.usuario} "
          f"({'creada ahora' if apertura['cuenta_nueva'] else 'ya existia'}) · "
          f"token valido {apertura['vida_token_s']}s")
    informe["acceso"] = apertura

    _titulo("Sembrando la libreta")
    objetivo = 300 if args.rapido else args.contactos
    siembra = ch.sembrar(acceso, objetivo=objetivo)
    informe["siembra"] = siembra
    if siembra.get("sembrado"):
        print(f"  {siembra['pedidos']} contactos importados en "
              f"{siembra['segundos']}s ({siembra['contactos_por_segundo']}/s) "
              f"· la libreta tiene ahora {siembra['total']}")
        print(f"  trabajo de importacion: {siembra['trabajo']}")
    else:
        print(f"  {siembra.get('motivo')}")

    inv = ch.inventario(acceso)
    informe["inventario"] = {k: v for k, v in inv.items() if k != "ids"}
    informe["inventario"]["fichas_de_referencia"] = len(inv["ids"])
    print(f"  se medira contra {inv['total']} contactos · "
          f"{len(inv['ids'])} fichas y {len(inv['textos'])} apellidos distintos "
          f"para repartir las consultas")
    if not inv["con_datos"] and not args.igual:
        print("\n  La libreta esta practicamente vacia: medir busquedas asi no")
        print("  mide nada. Revisa la siembra, o lanza --igual para medir igualmente.")
        registro.cerrar()
        orq.detener(estado)
        return 2

    monitor = Monitor(orq.pids(estado), intervalo=1.0)
    monitor.start()
    t0 = time.perf_counter()

    def marca(etiqueta: str) -> None:
        marcas.append({"t": round(time.perf_counter() - t0, 1), "etiqueta": etiqueta})

    recursos: Dict[str, Any] = {}
    try:
        solo = set(args.solo or [])

        _titulo("1. Arranque en frio: lo que espera la primera persona del dia")
        marca("frio")
        informe["arranque_frio"] = orq.arranque_en_frio(acceso)
        print("\n    calentando antes de medir en regimen estable …")
        await orq.calentar(acceso, inv, 3 if args.rapido else 6)

        if not solo or "rafaga" in solo:
            _titulo("2. Rafaga: todas a la vez desde reposo")
            informe.setdefault("esperas", {})["rafagas"] = await orq.en_pie("rafagas")
            marca("rafagas")
            tam = [20, 50] if args.rapido else [10, 20, 30, 40, 50, 60, 80]
            resultados = await orq.rafagas(tam, acceso, inv)
            informe["rafagas"] = [{**r.resumen(), "concurrencia": r.notas["concurrencia"]}
                                  for r in resultados]
            for r in resultados:
                guardar_muestras(r, salida / f"muestras_{r.escenario.replace(' ', '_')}.csv")

        if not solo or "escrituras" in solo:
            _titulo("3. Escrituras concurrentes sobre la misma libreta")
            informe.setdefault("esperas", {})["escrituras"] = await orq.en_pie("escrituras")
            marca("escrituras")
            r = await orq.escrituras(rps=10 if args.rapido else 25,
                                     segundos=8 if args.rapido else 25,
                                     sesion=acceso, inv=inv)
            guardar_muestras(r, salida / "muestras_escrituras.csv")
            informe["escrituras"] = r.resumen()
            informe["escrituras_por_operacion"] = r.por_operacion()
            rep.grafica_operaciones(r.por_operacion(), img / "carga-escrituras.png",
                                    "Coste de cada escritura con 25 peticiones/s")

        if not solo or "dura" in solo:
            _titulo("4. Solo las consultas caras")
            informe.setdefault("esperas", {})["consultas caras"] = await orq.en_pie("consultas caras")
            marca("busqueda dura")
            r = await orq.busqueda_dura(rps=5 if args.rapido else 12,
                                        segundos=8 if args.rapido else 25,
                                        sesion=acceso, inv=inv)
            guardar_muestras(r, salida / "muestras_busqueda_dura.csv")
            informe["busqueda_dura"] = r.resumen()
            informe["busqueda_dura_por_operacion"] = r.por_operacion()
            rep.grafica_operaciones(r.por_operacion(), img / "carga-consultas-caras.png",
                                    "Coste de cada consulta cara con 12 peticiones/s")

        if not solo or "resistencia" in solo:
            _titulo("5. Resistencia: caudal sostenido")
            informe.setdefault("esperas", {})["resistencia"] = await orq.en_pie("resistencia")
            marca("resistencia")
            r = await orq.resistencia(rps=20, segundos=20 if args.rapido else 120,
                                      sesion=acceso, inv=inv)
            guardar_muestras(r, salida / "muestras_resistencia.csv")
            informe["resistencia"] = r.resumen()
            rep.grafica_resistencia(salida / "muestras_resistencia.csv",
                                    img / "carga-resistencia.png")

        if (not solo or "importacion" in solo) and not args.sin_importacion:
            _titulo("6. Importacion grande mientras la oficina sigue buscando")
            informe.setdefault("esperas", {})["importacion"] = await orq.en_pie("importacion")
            marca("importacion")
            resultado = await orq.importacion_en_curso(
                acceso, inv, cuantos=800 if args.rapido else 3000,
                segundos_lectura=15 if args.rapido else 40)
            if resultado.get("ejecutado"):
                guardar_muestras(resultado.pop("resultado"),
                                 salida / "muestras_importacion.csv")
                informe["importacion"] = resultado
                print(f"    trabajo: {resultado['trabajo']}")
            else:
                resultado.pop("resultado", None)
                informe["importacion"] = resultado
                print(f"    [omitido] {resultado.get('motivo')}")

        if not solo or "errores" in solo:
            _titulo("7. Tolerancia a errores: peticiones mal formadas o sin permiso")
            informe.setdefault("esperas", {})["errores"] = await orq.en_pie("errores")
            marca("errores")
            informe["tolerancia"] = orq.tolerancia_errores(inv, acceso)
            t = informe["tolerancia"]
            print(f"\n    {t['correctos']}/{t['total']} respondieron como debian "
                  f"· {t['errores_500']} errores 500")
            print("\n    Cerrojo de la puerta (intentos fallidos seguidos):")
            informe["cerrojo"] = orq.cerrojo()

        _titulo("8. Integridad de la libreta despues de la paliza")
        informe.setdefault("esperas", {})["integridad"] = await orq.en_pie("integridad")
        marca("integridad")
        informe["integridad"] = orq.integridad(acceso, inv)
        for k, v in informe["integridad"].items():
            print(f"    {k:<32} {v}")

        # La escalada va la ULTIMA a proposito. Tumba el servicio, y despues
        # de tumbarlo tarda minutos en volver: medir cualquier otra cosa
        # encima de esa cola no mediria el sistema, mediria la caida
        # anterior. Se comprobo por las malas — en una corrida previa las
        # rafagas salieron con un 100 % de errores que no eran suyos.
        if not solo or "escalada" in solo:
            _titulo("9. Escalada: la hora punta real, multiplicada, hasta que se cae")
            print(f"    la hora punta real de esta oficina son "
                  f"{sum(esc.HORA_PUNTA.values())} peticiones en 60 minutos "
                  f"= {esc.RPS_NOMINAL:.3f} peticiones/s\n")
            informe.setdefault("esperas", {})["escalada"] = await orq.en_pie("escalada")
            marca("escalada")
            niveles = ([1, 20, 60] if args.rapido else
                       [1, 5, 10, 20, 25, 30, 33, 36, 40, 50, 65])
            segundos = 6 if args.rapido else 20
            resultados = await orq.escalada(niveles, segundos, acceso, inv)
            resumenes = []
            for r in resultados:
                guardar_muestras(r, salida / f"muestras_{r.escenario.replace(' ', '_')}.csv")
                resumenes.append({**r.resumen(), "factor": r.notas["factor"],
                                  "rps_objetivo": r.notas["rps_objetivo"],
                                  "recuperacion_s": r.notas.get("recuperacion_s")})
            informe["escalada"] = resumenes
            informe["recuperacion_s"] = resumenes[-1].get("recuperacion_s")
            rep.grafica_escalada(resumenes, img / "carga-escalada.png", esc.RPS_NOMINAL)
            rep.grafica_errores(resumenes, img / "carga-errores.png")
            rep.grafica_caudal(resumenes, img / "carga-caudal.png")
            peor = resultados[-1]
            rep.grafica_operaciones(peor.por_operacion(), img / "carga-operaciones.png",
                                    f"Coste de cada operacion bajo {peor.escenario}")
            informe["por_operacion_maxima"] = peor.por_operacion()


    finally:
        recursos = monitor.detener()
        monitor.guardar(salida / "recursos.csv")
        informe["recursos"] = recursos
        informe["marcas"] = marcas
        informe["renovaciones_de_token"] = acceso.renovaciones
        informe["duracion_total_s"] = round(time.perf_counter() - t0, 1)
        guardar_json(informe, salida / "informe.json")
        try:
            rep.grafica_recursos(salida / "recursos.csv", img / "carga-recursos.png", marcas)
        except Exception as exc:
            print(f"  [aviso] no se pudo dibujar la grafica de recursos: {exc}")
        try:
            informe["limpieza"] = orq.limpiar(acceso)
            print(f"\n  Limpieza: "
                  f"{informe['limpieza']['contactos_de_prueba_borrados']} "
                  f"contactos creados por la prueba retirados")
        except Exception as exc:
            print(f"  [aviso] no se pudo limpiar lo que escribio la prueba: {exc}")
        guardar_json(informe, salida / "informe.json")
        orq.detener(estado)

    _titulo("Resultado")
    for nombre, r in recursos.items():
        print(f"    {nombre:<12} CPU media {r.get('cpu_media_pct', 0):>5.1f} % · "
              f"pico {r.get('cpu_max_pct', 0):>6.1f} % · memoria "
              f"{r.get('rss_inicial_mb', 0):.0f} → {r.get('rss_final_mb', 0):.0f} MB "
              f"(deriva {r.get('deriva_memoria_mb', 0):+.1f} MB)")
    print(f"\n    Datos en crudo y resumen : {salida}")
    print(f"    Graficas                 : {img / 'carga-*.png'}")
    print(f"    Duracion total           : {informe['duracion_total_s']:.0f} s")

    # Copia estable para la documentacion. Solo una sesion COMPLETA la
    # actualiza: una corrida corta o parcial dejaria las graficas y los
    # registros del repositorio contando otra cosa distinta de las tablas.
    if not completa:
        print("\n  (sesion parcial: no se tocan las graficas ni los registros de docs/)")
        registro.cerrar()
        return 0

    destino = RAIZ / "docs" / "resultados"
    destino.mkdir(parents=True, exist_ok=True)
    copias = [(salida / "recursos.csv", "carga-recursos.csv"),
              (salida / "muestras_resistencia.csv", "carga-resistencia.csv"),
              (salida / "muestras_escrituras.csv", "carga-escrituras.csv"),
              (salida / "informe.json", "carga-informe.json"),
              (salida / "registro.txt", "carga-registro.txt"),
              (salida / "logs" / "contacthub.log", "carga-log-contacthub.txt")]
    # el nivel mas alto que se llego a ejecutar, se llame como se llame
    ultimo = informe.get("escalada") or []
    if ultimo:
        cimo = salida / ("muestras_oficina_"
                         + f"{ultimo[-1]['rps_objetivo']:g}rps".replace(" ", "_")
                         + ".csv")
        if cimo.exists():
            copias.append((cimo, "carga-peticiones-nivel-maximo.csv"))
    for origen, nombre in copias:
        if origen.exists():
            destino.joinpath(nombre).write_bytes(origen.read_bytes())
    registro.cerrar()
    return 0


def _maquina() -> Dict[str, Any]:
    import psutil
    return {"sistema": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
            "nucleos": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / 1e9, 1)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reto 7 — pruebas de carga y tolerancia sobre ContactHub")
    parser.add_argument("--ruta", default="",
                        help="carpeta de ContactHub (si no responde ya)")
    parser.add_argument("--contactos", type=int, default=2000,
                        help="tamano de la libreta con la que se mide")
    parser.add_argument("--rapido", action="store_true",
                        help="version corta, para comprobar que todo funciona")
    parser.add_argument("--solo", nargs="*",
                        choices=["escalada", "rafaga", "escrituras", "dura",
                                 "resistencia", "importacion", "errores"],
                        help="ejecutar solo algunos escenarios")
    parser.add_argument("--sin-importacion", action="store_true",
                        help="omitir la importacion grande (es la mas lenta)")
    parser.add_argument("--igual", action="store_true",
                        help="medir aunque la libreta este vacia")
    parser.add_argument("--check", action="store_true", help="solo diagnostico")
    args = parser.parse_args()

    if args.check:
        return 0 if check_env(args.ruta) else 1
    if not check_env(args.ruta):
        print("\nInstala lo que falta con:  pip install -r requirements.txt")
        return 1
    return asyncio.run(sesion(args))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Arranque de Directorio vivo (contactos del despacho).

    python run_contactos.py              # http://127.0.0.1:8200
    python run_contactos.py --port 9200  # otro puerto
    python run_contactos.py --check      # diagnostico del entorno y salir
    python run_contactos.py --importar   # cargar las fuentes y salir

Es una aplicacion independiente de las otras dos (`run.py` de video y
`run_documentos.py` de documentos): base de datos, configuracion e interfaz
propias. Las tres pueden correr a la vez. Si DocuFlow AI ya clasifico
documentos, este modulo los lee para saber quien es quien en cada expediente.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser

REQUERIDOS = [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("jinja2", "jinja2"),
              ("multipart", "python-multipart")]


def check_env() -> bool:
    ok = True
    print("== Dependencias ==")
    for modulo, paquete in REQUERIDOS:
        try:
            __import__(modulo)
            print(f"  [ok]    {paquete}")
        except ImportError:
            ok = False
            print(f"  [FALTA] {paquete}  ->  pip install {paquete}")

    try:
        from contactos.config import CONFIG, DB_PATH, DOCS_DB, SAMPLE_DIR
        from contactos.fuentes import ruta_llamadas, ruta_nomina
        print("\n== Fuentes ==")
        for etiqueta, ruta in (("Nomina del despacho", ruta_nomina()),
                               ("Llamadas (RingCentral)", ruta_llamadas()),
                               ("Documentos de DocuFlow AI", DOCS_DB)):
            listo = bool(ruta) and ruta.exists()
            print(f"  [{'ok' if listo else 'no':^4}] {etiqueta}: "
                  f"{ruta if ruta else SAMPLE_DIR}")
        print("\n== Configuracion ==")
        print(f"  Base de datos        : {DB_PATH}")
        print(f"  Ficha desde llamadas : {CONFIG.get('llamadas_min_veces')} llamadas "
              f"o {int(CONFIG.get('llamadas_min_segundos_total') or 0) // 60} min de conversacion")
        print(f"  Umbral de duplicado  : {CONFIG.get('umbral_duplicado')}")
    except Exception as exc:
        print(f"  [aviso] no se pudo leer la configuracion: {exc}")
    return ok


def importar() -> int:
    from contactos import db, fuentes
    db.init_db()
    print("Importando fuentes disponibles…\n")
    for r in fuentes.importar_todo():
        print(f"  {r['fuente']:<12} {r['creados']:>5} fichas nuevas  "
              f"{r['actualizados']:>5} completadas  {r['interacciones']:>6} hitos   {r['detalle']}")
    resumen = db.query_one(
        "SELECT (SELECT COUNT(*) FROM personas WHERE activo=1) p, "
        "(SELECT COUNT(*) FROM casos) c, (SELECT COUNT(*) FROM interacciones) i")
    print(f"\n  Total: {resumen['p']} fichas, {resumen['c']} expedientes, {resumen['i']} hitos")
    return 0


def _puerto_libre(host: str, puerto: int) -> int:
    for candidato in range(puerto, puerto + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", candidato)) != 0:
                return candidato
    return puerto


def main() -> int:
    parser = argparse.ArgumentParser(description="Directorio vivo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--reload", action="store_true", help="recarga en caliente")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="solo diagnostico")
    parser.add_argument("--importar", action="store_true",
                        help="cargar nomina, llamadas y documentos, y salir")
    args = parser.parse_args()

    if args.check:
        return 0 if check_env() else 1
    if not check_env():
        print("\nInstala lo que falta con:  pip install -r requirements.txt")
        return 1
    if args.importar:
        return importar()

    import uvicorn

    puerto = _puerto_libre(args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{puerto}"
    print(f"\n  Directorio vivo  ->  {url}\n  (Ctrl+C para detener)\n")

    if not args.no_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()

    uvicorn.run("contactos.main:app", host=args.host, port=puerto, reload=args.reload,
                log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Arranque de DocuFlow AI (clasificacion y nombrado de documentos).

    python run_documentos.py              # http://127.0.0.1:8100
    python run_documentos.py --port 9100  # otro puerto
    python run_documentos.py --check      # diagnostico del entorno y salir

Es una aplicacion independiente del modulo de video (`run.py`): base de datos,
configuracion e interfaz propias. Las dos pueden correr a la vez.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser

REQUERIDOS = [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("jinja2", "jinja2"),
              ("multipart", "python-multipart"), ("pymupdf", "pymupdf"),
              ("docx", "python-docx")]


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

    print("\n== Lectura de documentos ==")
    print("  [ok]    PDF con texto, DOCX, correos .eml, texto plano")
    try:
        from docsai.extract import _tesseract_disponible
        if _tesseract_disponible():
            print("  [ok]    OCR disponible (Tesseract): tambien PDFs escaneados e imagenes")
        else:
            print("  [no]    OCR no disponible: los PDF escaneados iran a revision")
            print("          (opcional: instala Tesseract y 'pip install pytesseract pillow')")
    except Exception as exc:
        print(f"  [aviso] no se pudo comprobar el OCR: {exc}")

    try:
        from docsai.classify import catalogo
        from docsai.config import CONFIG, ORGANIZADOS_DIR
        print(f"\n== Configuracion ==")
        print(f"  Categorias definidas : {len(catalogo())}")
        print(f"  Umbral de revision   : {CONFIG.get('umbral_revision')}")
        print(f"  Plantilla de nombre  : {CONFIG.get('plantilla_nombre')}")
        print(f"  Archivo organizado en: {ORGANIZADOS_DIR}")
    except Exception as exc:
        print(f"  [aviso] no se pudo leer la configuracion: {exc}")
    return ok


def _puerto_libre(host: str, puerto: int) -> int:
    for candidato in range(puerto, puerto + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", candidato)) != 0:
                return candidato
    return puerto


def main() -> int:
    parser = argparse.ArgumentParser(description="DocuFlow AI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--reload", action="store_true", help="recarga en caliente")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="solo diagnostico")
    args = parser.parse_args()

    if args.check:
        return 0 if check_env() else 1
    if not check_env():
        print("\nInstala lo que falta con:  pip install -r requirements.txt")
        return 1

    import uvicorn

    puerto = _puerto_libre(args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{puerto}"
    print(f"\n  DocuFlow AI  ->  {url}\n  (Ctrl+C para detener)\n")

    if not args.no_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()

    uvicorn.run("docsai.main:app", host=args.host, port=puerto, reload=args.reload,
                log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

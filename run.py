#!/usr/bin/env python3
"""Arranque de OfficeVision AI.

    python run.py                 # http://127.0.0.1:8000
    python run.py --port 9000     # otro puerto
    python run.py --host 0.0.0.0  # accesible en la red local
    python run.py --check         # diagnostico del entorno y salir
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser

REQUIRED = [("cv2", "opencv-python-headless"), ("fastapi", "fastapi"),
            ("uvicorn", "uvicorn"), ("numpy", "numpy"), ("openpyxl", "openpyxl"),
            ("jinja2", "jinja2"), ("multipart", "python-multipart")]


def check_env() -> bool:
    ok = True
    print("== Dependencias ==")
    for module, package in REQUIRED:
        try:
            __import__(module)
            print(f"  [ok]    {package}")
        except ImportError:
            ok = False
            print(f"  [FALTA] {package}  ->  pip install {package}")
    print("\n== Backend de vision ==")
    try:
        from app.vision.detector import available_backends, build_detector
        backends = available_backends()
        for name, avail in backends.items():
            print(f"  {'[ok]   ' if avail else '[no]   '} {name}")
        det = build_detector()
        print(f"  Detector activo: {det.name} - {det.description}")
    except Exception as exc:
        print(f"  [aviso] no se pudo inicializar el detector: {exc}")
    return ok


def _free_port(host: str, port: int) -> int:
    for candidate in range(port, port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", candidate)) != 0:
                return candidate
    return port


def main() -> int:
    parser = argparse.ArgumentParser(description="OfficeVision AI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
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

    port = _free_port(args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{port}"
    print(f"\n  OfficeVision AI  ->  {url}\n  (Ctrl+C para detener)\n")

    if not args.no_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(url)), daemon=True).start()

    uvicorn.run("app.main:app", host=args.host, port=port, reload=args.reload,
                log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())

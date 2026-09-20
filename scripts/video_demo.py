#!/usr/bin/env python3
"""Genera un video sintetico de oficina para probar el pipeline sin camara.

    python scripts/video_demo.py --salida data/uploads/demo_oficina.mp4 --segundos 40

El video simula siluetas moviendose entre zonas. Sirve para validar el flujo
completo (tracking, zonas, eventos, base de datos) usando el backend `motion`;
para probar el modelo YOLO usa una grabacion real de personas.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np

W, H = 960, 540


def fondo() -> np.ndarray:
    img = np.full((H, W, 3), 32, dtype=np.uint8)
    img[:, :] = (46, 38, 32)
    cv2.rectangle(img, (0, 0), (W, 150), (62, 52, 44), -1)          # pasillo
    cv2.rectangle(img, (30, 300), (300, 520), (74, 64, 54), -1)     # recepcion
    cv2.rectangle(img, (340, 250), (700, 520), (70, 60, 50), -1)    # area de trabajo
    cv2.rectangle(img, (730, 220), (930, 520), (80, 70, 58), -1)    # sala de juntas
    for x in range(360, 700, 110):                                   # escritorios
        cv2.rectangle(img, (x, 320), (x + 80, 380), (110, 96, 78), -1)
    cv2.putText(img, "OFICINA - DEMO SINTETICA", (24, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    return img


def silueta(img: np.ndarray, x: int, y: int, escala: float, color) -> None:
    h = int(90 * escala)
    w = max(10, int(h * 0.38))
    cv2.ellipse(img, (x, y - h), (w // 2, int(h * 0.42)), 0, 0, 360, color, -1)
    cv2.circle(img, (x, y - h - int(h * 0.42)), max(5, int(w * 0.42)), color, -1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="data/uploads/demo_oficina.mp4")
    ap.add_argument("--segundos", type=int, default=40)
    ap.add_argument("--fps", type=int, default=20)
    args = ap.parse_args()

    out = Path(args.salida)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    for codec in ("mp4v", "avc1"):
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*codec), args.fps, (W, H))
        if writer.isOpened():
            break
    if writer is None or not writer.isOpened():
        print("No se pudo crear el video")
        return 1

    base = fondo()
    total = args.segundos * args.fps
    personas = [
        {"x0": 80, "y0": 470, "x1": 640, "y1": 350, "fase": 0.0, "color": (210, 215, 225)},
        {"x0": 900, "y0": 500, "x1": 380, "y1": 470, "fase": 0.35, "color": (190, 200, 215)},
        {"x0": 500, "y0": 120, "x1": 820, "y1": 460, "fase": 0.7, "color": (200, 190, 200)},
        {"x0": 200, "y0": 330, "x1": 260, "y1": 500, "fase": 0.15, "color": (185, 195, 205)},
    ]
    for i in range(total):
        frame = base.copy()
        ruido = np.random.randint(-4, 5, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
        t = i / total
        for p in personas:
            fase = (t + p["fase"]) % 1.0
            onda = (math.sin(fase * 2 * math.pi) + 1) / 2
            x = int(p["x0"] + (p["x1"] - p["x0"]) * onda)
            y = int(p["y0"] + (p["y1"] - p["y0"]) * onda)
            escala = 0.75 + 0.45 * (y / H)
            silueta(frame, x, y, escala, p["color"])
        writer.write(frame)
    writer.release()
    print(f"Video generado: {out} ({args.segundos}s, {args.fps} fps, {W}x{H})")
    print("Sugerencia: como las siluetas son sinteticas, analizalo con el detector "
          "'motion' (config.json -> \"detector\": \"motion\"). Para probar YOLO usa "
          "una grabacion real de personas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

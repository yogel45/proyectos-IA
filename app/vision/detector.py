"""Detectores de objetos con degradacion automatica.

Cadena de backends (se elige el primero disponible):
  1. `yolo`   -> Ultralytics YOLO11/YOLOv8 (.pt). Mejor precision, CPU o GPU.
  2. `onnx`   -> El mismo YOLO exportado a ONNX, ejecutado con cv2.dnn
                 (sin PyTorch, util en maquinas ligeras).
  3. `motion` -> Sustraccion de fondo MOG2 + contornos. Sin modelos ni
                 descargas: garantiza que la app SIEMPRE corre.

Todos devuelven la misma estructura `Detection`, asi el resto del pipeline
(tracking, zonas, metricas) es independiente del modelo.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import CONFIG, MODELS_DIR

log = logging.getLogger("officevision.detector")

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    label: str = "person"
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def centroid(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def anchor(self) -> Tuple[float, float]:
        """Punto de contacto con el piso: mejor referencia para zonas."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


class BaseDetector:
    name = "base"
    description = ""

    def detect(self, frame: np.ndarray) -> List[Detection]:  # pragma: no cover
        raise NotImplementedError

    def info(self) -> Dict[str, Any]:
        return {"backend": self.name, "description": self.description}


# --------------------------------------------------------------------------
# 1. Ultralytics YOLO
# --------------------------------------------------------------------------
_YOLO_CACHE: Dict[str, Any] = {}
_YOLO_LOCK = threading.Lock()


def _load_yolo(weights: str):
    """Carga (y cachea) los pesos YOLO. Se descargan solos la primera vez."""
    with _YOLO_LOCK:
        if weights in _YOLO_CACHE:
            return _YOLO_CACHE[weights]
        from ultralytics import YOLO  # import perezoso: dependencia opcional

        local = MODELS_DIR / Path(weights).name
        target = str(local) if local.exists() else weights
        model = YOLO(target)
        # Ultralytics descarga el .pt al directorio actual: lo movemos a models/
        try:
            if not local.exists():
                for cand in (Path(getattr(model, "ckpt_path", "") or ""), Path(Path(weights).name)):
                    if cand.exists() and cand.is_file():
                        local.write_bytes(cand.read_bytes())
                        if cand.resolve() != local.resolve():
                            cand.unlink(missing_ok=True)
                        break
        except Exception:  # la cache es un extra, nunca debe romper el arranque
            pass
        _YOLO_CACHE[weights] = model
        return model


class YoloDetector(BaseDetector):
    name = "yolo"

    def __init__(self, weights: str, conf: float, imgsz: int, device: str,
                 classes: Optional[List[str]] = None):
        self.model = _load_yolo(weights)
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.lock = threading.Lock()
        names = self.model.names if isinstance(self.model.names, dict) else dict(enumerate(self.model.names))
        self._names = {int(k): str(v) for k, v in names.items()}
        wanted = set(classes or [])
        # sin lista de clases = reconoce todo lo que el modelo conoce
        self._class_ids = ([i for i, n in self._names.items() if n in wanted]
                           if wanted else None)
        total = len(self._class_ids) if self._class_ids else len(self._names)
        self.description = f"Ultralytics {Path(weights).name} ({device}) - {total} clases"

    def detect(self, frame: np.ndarray) -> List[Detection]:
        with self.lock:
            results = self.model.predict(
                frame, conf=self.conf, imgsz=self.imgsz, device=self.device,
                classes=self._class_ids, verbose=False,
            )
        out: List[Detection] = []
        for res in results:
            boxes = getattr(res, "boxes", None)
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            clss = boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, clss):
                out.append(Detection(float(x1), float(y1), float(x2), float(y2),
                                     float(c), self._names.get(int(k), str(k))))
        return out


# --------------------------------------------------------------------------
# 2. YOLO exportado a ONNX (cv2.dnn, sin PyTorch)
# --------------------------------------------------------------------------
class OnnxYoloDetector(BaseDetector):
    name = "onnx"

    def __init__(self, model_path: str, conf: float, iou: float, imgsz: int,
                 classes: Optional[List[str]] = None):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.wanted = set(classes or [])
        self.lock = threading.Lock()
        self.description = f"ONNX {Path(model_path).name} via OpenCV DNN"

    def detect(self, frame: np.ndarray) -> List[Detection]:
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (self.imgsz, self.imgsz),
                                     swapRB=True, crop=False)
        with self.lock:
            self.net.setInput(blob)
            raw = self.net.forward()
        pred = np.squeeze(raw)
        if pred.ndim != 2:
            return []
        # YOLOv8/11 exporta (84, 8400); YOLOv5 exporta (25200, 85)
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T
            boxes_xywh, scores = pred[:, :4], pred[:, 4:]
        else:
            obj = pred[:, 4:5]
            boxes_xywh, scores = pred[:, :4], pred[:, 5:] * obj
        class_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        keep = confs >= self.conf
        boxes_xywh, class_ids, confs = boxes_xywh[keep], class_ids[keep], confs[keep]
        if len(confs) == 0:
            return []
        gx, gy = w / self.imgsz, h / self.imgsz
        rects, out = [], []
        for (cx, cy, bw, bh) in boxes_xywh:
            rects.append([int((cx - bw / 2) * gx), int((cy - bh / 2) * gy),
                          int(bw * gx), int(bh * gy)])
        idxs = cv2.dnn.NMSBoxes(rects, confs.astype(float).tolist(), self.conf, self.iou)
        for i in np.array(idxs).flatten().astype(int) if len(np.array(idxs)) else []:
            label = COCO_CLASSES[class_ids[i]] if class_ids[i] < len(COCO_CLASSES) else str(class_ids[i])
            if self.wanted and label not in self.wanted:
                continue
            x, y, bw, bh = rects[i]
            out.append(Detection(float(x), float(y), float(x + bw), float(y + bh),
                                 float(confs[i]), label))
        return out


# --------------------------------------------------------------------------
# 3. Fallback sin modelo: movimiento (MOG2) + heuristica de silueta
# --------------------------------------------------------------------------
class MotionDetector(BaseDetector):
    name = "motion"
    description = "Sustraccion de fondo MOG2 + contornos (modo sin modelo)"

    def __init__(self, min_area_ratio: float = 0.004, max_area_ratio: float = 0.55):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=350, varThreshold=28,
                                                     detectShadows=True)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 9))
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.warmup = 0

    def detect(self, frame: np.ndarray) -> List[Detection]:
        h, w = frame.shape[:2]
        mask = self.bg.apply(cv2.GaussianBlur(frame, (5, 5), 0))
        mask[mask < 200] = 0                       # descarta sombras (valor 127)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel, iterations=1)
        mask = cv2.dilate(mask, self.kernel, iterations=2)
        self.warmup += 1
        if self.warmup < 10:                       # deja que el fondo se estabilice
            return []
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = float(h * w)
        out: List[Detection] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area / frame_area < self.min_area_ratio or area / frame_area > self.max_area_ratio:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            ratio = bh / max(bw, 1)
            if ratio < 0.7:                        # una persona es mas alta que ancha
                continue
            fill = area / float(bw * bh)
            conf = float(min(0.95, 0.35 + fill * 0.5))
            out.append(Detection(float(x), float(y), float(x + bw), float(y + bh),
                                 conf, "person", {"source": "motion"}))
        return out


# --------------------------------------------------------------------------
# Fabrica con degradacion automatica
# --------------------------------------------------------------------------
_BACKENDS_CACHE: Optional[Dict[str, bool]] = None


def available_backends(refresh: bool = False) -> Dict[str, bool]:
    """Backends disponibles. Se cachea: comprobarlo importa PyTorch (lento)."""
    global _BACKENDS_CACHE
    if _BACKENDS_CACHE is not None and not refresh:
        cache = dict(_BACKENDS_CACHE)
        cfg_onnx = CONFIG.get("onnx_model") or ""
        cache["onnx"] = bool(list(MODELS_DIR.glob("*.onnx"))) or (
            bool(cfg_onnx) and Path(cfg_onnx).exists())
        return cache
    try:
        import ultralytics  # noqa: F401
        yolo_ok = True
    except Exception:
        yolo_ok = False
    onnx_candidates = list(MODELS_DIR.glob("*.onnx"))
    cfg_onnx = CONFIG.get("onnx_model") or ""
    onnx_ok = bool(onnx_candidates) or (bool(cfg_onnx) and Path(cfg_onnx).exists())
    _BACKENDS_CACHE = {"yolo": yolo_ok, "onnx": onnx_ok, "motion": True}
    return dict(_BACKENDS_CACHE)


def build_detector(preferred: Optional[str] = None,
                   classes: Optional[List[str]] = None) -> BaseDetector:
    """Construye el detector segun configuracion, degradando si algo falta.

    `classes` permite pedir un juego de clases distinto al configurado (lo usa
    la deteccion automatica de zonas, que necesita ver mobiliario aunque el
    analisis normal solo siga a las personas).
    """
    preferred = (preferred or CONFIG.get("detector") or "auto").lower()
    conf = float(CONFIG.get("conf_threshold"))
    iou = float(CONFIG.get("iou_threshold"))
    imgsz = int(CONFIG.get("imgsz"))
    device = str(CONFIG.get("device"))
    if classes is None and CONFIG.get("detect_all_classes"):
        classes = []                      # lista vacia = todas las clases
    else:
        classes = list(classes or CONFIG.get("classes") or ["person"])
    order = [preferred] if preferred != "auto" else ["yolo", "onnx", "motion"]
    if preferred != "auto" and preferred != "motion":
        order.append("motion")                     # red de seguridad

    errors = []
    for backend in order:
        try:
            if backend == "yolo":
                return YoloDetector(str(CONFIG.get("model")), conf, imgsz, device, classes)
            if backend == "onnx":
                path = CONFIG.get("onnx_model") or ""
                if not path or not Path(path).exists():
                    found = sorted(MODELS_DIR.glob("*.onnx"))
                    if not found:
                        raise FileNotFoundError("no hay modelos .onnx en models/")
                    path = str(found[0])
                return OnnxYoloDetector(path, conf, iou, imgsz, classes)
            if backend == "motion":
                return MotionDetector()
        except Exception as exc:  # pragma: no cover - depende del entorno
            errors.append(f"{backend}: {exc}")
            log.warning("Backend '%s' no disponible (%s)", backend, exc)
    log.error("Ningun backend disponible: %s", "; ".join(errors))
    return MotionDetector()

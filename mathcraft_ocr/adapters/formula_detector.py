# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .common import create_session


@dataclass(frozen=True)
class FormulaBox:
    box: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ]
    score: float
    label: str


def warmup_formula_detector(model_dir: str | Path, provider_info) -> None:
    root = Path(model_dir)
    candidates = sorted(root.glob("*mfd*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"no mfd onnx file found under {root}")
    create_session(candidates[0], provider_info)


def _letterbox(image: np.ndarray, target_size: int = 768) -> tuple[np.ndarray, float, tuple[float, float]]:
    height, width = image.shape[:2]
    scale = min(target_size / width, target_size / height)
    new_w = int(round(width * scale))
    new_h = int(round(height * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
    pad_x = (target_size - new_w) / 2
    pad_y = (target_size - new_h) / 2
    left = int(round(pad_x - 0.1))
    top = int(round(pad_y - 0.1))
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas, scale, (float(left), float(top))


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    if len(boxes) == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[current], x1[rest])
        yy1 = np.maximum(y1[current], y1[rest])
        xx2 = np.minimum(x2[current], x2[rest])
        yy2 = np.minimum(y2[current], y2[rest])
        inter_w = np.maximum(0.0, xx2 - xx1)
        inter_h = np.maximum(0.0, yy2 - yy1)
        intersection = inter_w * inter_h
        union = areas[current] + areas[rest] - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        order = rest[iou <= iou_threshold]
    return keep


def detect_formula_boxes(
    image_rgb: np.ndarray,
    model_dir: str | Path,
    provider_info,
    *,
    confidence_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    input_size: int = 768,
) -> tuple[FormulaBox, ...]:
    root = Path(model_dir)
    candidates = sorted(root.glob("*mfd*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"no mfd onnx file found under {root}")
    session = create_session(candidates[0], provider_info)
    preprocessed, scale, (pad_x, pad_y) = _letterbox(image_rgb, input_size)
    model_input = (
        preprocessed.astype(np.float32).transpose(2, 0, 1)[np.newaxis, ...] / 255.0
    )
    output = session.run(None, {session.get_inputs()[0].name: model_input})[0]
    preds = np.asarray(output[0]).T
    if preds.size == 0 or preds.shape[1] < 6:
        return ()
    xywh = preds[:, :4]
    class_scores = preds[:, 4:]
    class_ids = np.argmax(class_scores, axis=1)
    scores = class_scores[np.arange(len(class_scores)), class_ids]
    mask = scores >= confidence_threshold
    if not np.any(mask):
        return ()
    xywh = xywh[mask]
    class_ids = class_ids[mask]
    scores = scores[mask]

    x, y, w, h = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
    boxes = np.stack([x - w / 2, y - h / 2, x + w / 2, y + h / 2], axis=1)
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - pad_x) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - pad_y) / scale
    height, width = image_rgb.shape[:2]
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height)

    labels = ("embedding", "isolated")
    keep = _nms_xyxy(boxes, scores, iou_threshold)
    results: list[FormulaBox] = []
    for index in keep:
        x1, y1, x2, y2 = boxes[index].tolist()
        results.append(
            FormulaBox(
                box=((x1, y1), (x2, y1), (x2, y2), (x1, y2)),
                score=float(scores[index]),
                label=labels[int(class_ids[index])] if int(class_ids[index]) < len(labels) else str(int(class_ids[index])),
            )
        )
    return tuple(results)

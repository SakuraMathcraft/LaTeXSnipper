# coding: utf-8

from __future__ import annotations

from pathlib import Path

import numpy as np
from rapidocr.ch_ppocr_det.utils import DBPostProcess, DetPreProcess

from .common import create_session


def _find_detector_model(root: Path) -> Path:
    candidates = sorted(root.glob("**/*det*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"missing text detector model under {root}")
    return candidates[0]


def warmup_text_detector(model_dir: str | Path, provider_info) -> None:
    root = Path(model_dir)
    create_session(_find_detector_model(root), provider_info)


def _limit_side_len(image: np.ndarray) -> int:
    max_wh = max(image.shape[0], image.shape[1])
    if max_wh < 960:
        return 960
    if max_wh < 1500:
        return 1500
    return 2000


def detect_text_boxes(
    image_bgr: np.ndarray,
    model_dir: str | Path,
    provider_info,
) -> tuple[np.ndarray, tuple[float, ...]]:
    root = Path(model_dir)
    model_path = _find_detector_model(root)
    session = create_session(model_path, provider_info)
    pre = DetPreProcess(
        limit_side_len=_limit_side_len(image_bgr),
        limit_type="min",
        mean=[0.5, 0.5, 0.5],
        std=[0.5, 0.5, 0.5],
    )
    post = DBPostProcess(
        thresh=0.3,
        box_thresh=0.5,
        max_candidates=1000,
        unclip_ratio=1.6,
        use_dilation=True,
    )
    model_input = pre(image_bgr)
    outputs = session.run(
        None,
        {session.get_inputs()[0].name: model_input},
    )
    boxes, scores = post(outputs[0], (image_bgr.shape[0], image_bgr.shape[1]))
    return boxes, tuple(float(score) for score in scores)

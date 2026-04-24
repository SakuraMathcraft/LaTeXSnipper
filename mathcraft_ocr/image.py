# coding: utf-8

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

import numpy as np
from PIL import Image


ImageInput: TypeAlias = str | Path | Image.Image | np.ndarray


def load_image_rgb(image: ImageInput) -> np.ndarray:
    if isinstance(image, (str, Path)):
        with Image.open(image) as handle:
            return np.array(handle.convert("RGB"))
    if isinstance(image, Image.Image):
        return np.array(image.convert("RGB"))
    if not isinstance(image, np.ndarray):
        raise TypeError(f"unsupported image input: {type(image)!r}")
    if image.ndim == 2:
        return np.stack([image, image, image], axis=-1).astype(np.uint8, copy=False)
    if image.ndim == 3 and image.shape[2] == 1:
        return np.repeat(image, 3, axis=2).astype(np.uint8, copy=False)
    if image.ndim == 3 and image.shape[2] == 3:
        return image.astype(np.uint8, copy=False)
    raise ValueError(f"unsupported image shape: {image.shape!r}")


def rgb_to_bgr(image: np.ndarray) -> np.ndarray:
    return image[:, :, ::-1].copy()

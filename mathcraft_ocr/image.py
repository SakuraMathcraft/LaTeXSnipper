from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

import numpy as np
from PIL import Image, ImageOps

ImageInput: TypeAlias = str | Path | Image.Image | np.ndarray


def normalize_formula_polarity(rgb: np.ndarray) -> np.ndarray:
    """Invert light ink on a mostly uniform dark background without changing geometry."""
    if rgb.size == 0:
        return rgb
    gray = rgb.astype(np.float32).mean(axis=2)
    background = float(np.median(gray))
    if background >= 100:
        return rgb
    background_fraction = float(np.mean(np.abs(gray - background) <= 20))
    foreground_fraction = float(np.mean(gray >= background + 60))
    if background_fraction >= 0.65 and 0.003 <= foreground_fraction <= 0.30:
        return 255 - rgb
    return rgb


def prepare_formula_canvas(image: Image.Image | np.ndarray) -> Image.Image:
    """Bound wide-strip distortion before the model's fixed-size resize."""
    rgb = normalize_formula_polarity(load_image_rgb(image))
    canvas = Image.fromarray(rgb)
    if canvas.width > canvas.height * 4:
        target_height = (canvas.width + 3) // 4
        extra = target_height - canvas.height
        canvas = ImageOps.expand(
            canvas, border=(0, extra // 2, 0, extra - extra // 2), fill="white"
        )
    return canvas


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

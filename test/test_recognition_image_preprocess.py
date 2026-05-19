from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_optimize_mathcraft_input_keeps_normal_screenshot_size() -> None:
    from recognition.image_preprocess import optimize_mathcraft_input_image

    image = Image.new("RGB", (1200, 800), "white")
    optimized = optimize_mathcraft_input_image(image)

    assert optimized is image
    assert optimized.size == (1200, 800)


def test_optimize_mathcraft_input_downscales_large_screenshot() -> None:
    from recognition.image_preprocess import (
        MATHCRAFT_MAX_INPUT_EDGE,
        MATHCRAFT_MAX_INPUT_PIXELS,
        optimize_mathcraft_input_image,
    )

    image = Image.new("RGB", (4200, 2600), "white")
    optimized = optimize_mathcraft_input_image(image)
    width, height = optimized.size

    assert width < 4200
    assert height < 2600
    assert max(width, height) <= MATHCRAFT_MAX_INPUT_EDGE
    assert width * height <= MATHCRAFT_MAX_INPUT_PIXELS


def test_qimage_to_rgb_pil_preserves_color_channels() -> None:
    from PyQt6.QtGui import QColor, QImage

    from recognition.image_preprocess import qimage_to_rgb_pil

    image = QImage(4, 3, QImage.Format.Format_ARGB32)
    image.fill(QColor(10, 20, 30))

    pil = qimage_to_rgb_pil(image)

    assert pil.mode == "RGB"
    assert pil.size == (4, 3)
    assert pil.getpixel((0, 0)) == (10, 20, 30)

from __future__ import annotations

from math import sqrt

from PIL import Image
from PyQt6.QtGui import QImage

from mathcraft_ocr.image_color import to_ocr_rgb

MATHCRAFT_MAX_INPUT_EDGE = 2400
MATHCRAFT_MAX_INPUT_PIXELS = 4_000_000


def qimage_to_rgb_pil(image: QImage) -> Image.Image:
    """Convert a QImage to RGB PIL image without PNG encode/decode."""
    mode = "RGBA" if image.hasAlphaChannel() else "RGB"
    image_format = (
        QImage.Format.Format_RGBA8888 if mode == "RGBA" else QImage.Format.Format_RGB888
    )
    fmt_image = image.convertToFormat(image_format)
    width = fmt_image.width()
    height = fmt_image.height()
    ptr = fmt_image.bits()
    assert ptr is not None
    ptr.setsize(height * fmt_image.bytesPerLine())
    return to_ocr_rgb(
        Image.frombytes(
            mode,
            (width, height),
            ptr.asstring(height * fmt_image.bytesPerLine()),
            "raw",
            mode,
            fmt_image.bytesPerLine(),
            1,
        )
    )


def qpixmap_to_rgb_pil(pixmap) -> Image.Image:
    return qimage_to_rgb_pil(pixmap.toImage())


def optimize_mathcraft_input_image(image: Image.Image) -> Image.Image:
    """Keep normal screenshots intact, but cap very large inputs before OCR."""
    image = to_ocr_rgb(image)
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    scale = min(
        1.0,
        MATHCRAFT_MAX_INPUT_EDGE / max(width, height),
        sqrt(MATHCRAFT_MAX_INPUT_PIXELS / max(1, width * height)),
    )
    if scale >= 0.999:
        return image
    target = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(target, Image.Resampling.LANCZOS)

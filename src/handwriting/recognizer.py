from __future__ import annotations

import numpy as np

from PIL import Image, ImageFilter
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from backend.external_model import ExternalModelClient, ExternalModelConfig

# Minimum dimension threshold for upscaling; images below this are scaled up
# to ensure OCR models receive enough pixel detail for small handwriting.
_UPSCALE_MIN_DIM = 120
_UPSCALE_TARGET_DIM = 220


def qimage_to_pil(image: QImage) -> Image.Image:
    """Convert QImage to PIL RGB Image with fast direct-memory path.

    Uses QImage.bits() to avoid PNG encode/decode overhead.
    Only upscales when the image is smaller than _UPSCALE_MIN_DIM
    to avoid wasting time on already-large exports.
    """
    # Ensure 32-bit ARGB format for consistent memory layout
    fmt_image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width = fmt_image.width()
    height = fmt_image.height()
    ptr = fmt_image.bits()
    if ptr is None:
        # Fallback: QImage with no direct memory access (rare)
        from io import BytesIO
        from PyQt6.QtCore import QBuffer, QIODevice
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        image.save(buffer, "PNG")
        data = bytes(buffer.data())
        buffer.close()
        pil = Image.open(BytesIO(data)).convert("RGB")
    else:
        ptr.setsize(height * fmt_image.bytesPerLine())
        arr = np.array(ptr, copy=True).reshape(height, fmt_image.bytesPerLine())
        # ARGB32: bytesPerLine may have padding; strip to width * 4
        arr = arr[:, :width * 4].reshape(height, width, 4)
        # ARGB -> RGB: drop alpha channel (index 0)
        pil = Image.fromarray(arr[:, :, 1:4], "RGB")

    # Only upscale if the image is too small for reliable OCR
    if pil.width < _UPSCALE_MIN_DIM or pil.height < _UPSCALE_MIN_DIM:
        scale = max(2.0, _UPSCALE_TARGET_DIM / min(pil.width, pil.height))
        pil = pil.resize(
            (max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return pil


def enhance_stroke_image(pil: Image.Image) -> Image.Image:
    """Apply lightweight preprocessing to improve OCR of handwritten strokes.

    - Sharpens thin strokes for better edge detection
    - Slightly boosts contrast to make faint ink more visible
    """
    # Sharpening kernel to make thin strokes crisper
    pil = pil.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))
    return pil


class HandwritingRecognitionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        model_wrapper,
        image: QImage,
        model_name: str = "mathcraft",
        external_config: ExternalModelConfig | None = None,
    ):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name
        self.external_config = external_config

    def run(self) -> None:
        try:
            pil_img = qimage_to_pil(self.image)
            pil_img = enhance_stroke_image(pil_img)
            model_name = str(self.model_name or "mathcraft").strip().lower()
            if model_name == "external_model":
                if self.external_config is None:
                    self.failed.emit("外部模型未配置")
                    return
                result_obj = ExternalModelClient(self.external_config).predict(pil_img)
                result = result_obj.best_text(self.external_config.normalized_output_mode()).strip()
            else:
                result = (self.model_wrapper.predict(pil_img, model_name=model_name) or "").strip()

            if not str(result or "").strip():
                self.failed.emit("识别结果为空")
                return
            self.finished.emit(str(result).strip())
        except Exception as exc:
            self.failed.emit(str(exc))

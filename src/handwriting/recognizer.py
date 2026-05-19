from __future__ import annotations

from PIL import Image, ImageFilter
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from backend.external_model import ExternalModelClient, ExternalModelConfig

_UPSCALE_MIN_DIM = 120
_UPSCALE_TARGET_DIM = 220


def _qimage_to_pil_via_png(image: QImage) -> Image.Image:
    from io import BytesIO

    from PyQt6.QtCore import QBuffer, QIODevice

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return Image.open(BytesIO(data)).convert("RGB")


def qimage_to_pil(image: QImage) -> Image.Image:
    """Convert QImage to PIL RGB without PNG encode/decode on the common path."""
    try:
        fmt_image = image.convertToFormat(QImage.Format.Format_RGB888)
        width = fmt_image.width()
        height = fmt_image.height()
        ptr = fmt_image.bits()
        ptr.setsize(height * fmt_image.bytesPerLine())
        pil = Image.frombytes(
            "RGB",
            (width, height),
            bytes(ptr),
            "raw",
            "RGB",
            fmt_image.bytesPerLine(),
            1,
        )
    except Exception:
        pil = _qimage_to_pil_via_png(image)

    if pil.width < _UPSCALE_MIN_DIM or pil.height < _UPSCALE_MIN_DIM:
        scale = max(2.0, _UPSCALE_TARGET_DIM / max(1, min(pil.width, pil.height)))
        pil = pil.resize(
            (max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return pil


def enhance_stroke_image(pil: Image.Image) -> Image.Image:
    return pil.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))


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

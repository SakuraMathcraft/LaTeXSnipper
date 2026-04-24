from __future__ import annotations

from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QObject, pyqtSignal
from PyQt6.QtGui import QImage

from backend.external_model import ExternalModelClient, ExternalModelConfig


def qimage_to_pil(image: QImage) -> Image.Image:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    pil = Image.open(BytesIO(data)).convert("RGB")
    if pil.width < 32 or pil.height < 32:
        pil = pil.resize((max(32, pil.width * 2), max(32, pil.height * 2)), Image.Resampling.LANCZOS)
    else:
        pil = pil.resize((pil.width * 2, pil.height * 2), Image.Resampling.LANCZOS)
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

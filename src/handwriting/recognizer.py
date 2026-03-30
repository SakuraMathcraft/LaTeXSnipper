from __future__ import annotations

from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QObject, pyqtSignal
from PyQt6.QtGui import QImage


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

    def __init__(self, model_wrapper, image: QImage, model_name: str = "pix2text"):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name

    def run(self) -> None:
        try:
            pil_img = qimage_to_pil(self.image)
            result = self.model_wrapper.predict(pil_img, model_name=self.model_name)
            result = (result or "").strip()
            if not result:
                self.failed.emit("识别结果为空")
                return
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

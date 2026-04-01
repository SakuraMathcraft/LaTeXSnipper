import time

from PyQt6.QtCore import QObject, pyqtSignal

from .mineru_client import MineruClient
from .schemas import ExternalModelConfig


class MineruWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: ExternalModelConfig, image):
        super().__init__()
        self.config = config
        self.image = image
        self.elapsed = None

    def run(self):
        t0 = time.perf_counter()
        try:
            from .client import ExternalModelClient

            image_b64 = ExternalModelClient(self.config)._image_to_base64(self.image)
            result = MineruClient(self.config).predict(image_b64)
            self.elapsed = time.perf_counter() - t0
            self.finished.emit(result)
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            self.failed.emit(str(e))

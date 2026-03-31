import time

from PyQt6.QtCore import QObject, pyqtSignal

from .client import ExternalModelClient
from .schemas import ExternalModelConfig


class ExternalModelWorker(QObject):
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
            client = ExternalModelClient(self.config)
            result = client.predict(self.image)
            self.elapsed = time.perf_counter() - t0
            self.finished.emit(result)
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            self.failed.emit(str(e))


class ExternalModelConnectionWorker(QObject):
    finished = pyqtSignal(bool, str)
    failed = pyqtSignal(str)

    def __init__(self, config: ExternalModelConfig):
        super().__init__()
        self.config = config
        self.elapsed = None

    def run(self):
        t0 = time.perf_counter()
        try:
            ok, message = ExternalModelClient(self.config).test_connection()
            self.elapsed = time.perf_counter() - t0
            self.finished.emit(bool(ok), str(message or ""))
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            self.failed.emit(str(e))

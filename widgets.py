# -*- coding: utf-8 -*-
"""工作线程和后台任务组件"""

from PyQt6.QtCore import QObject, pyqtSignal
from PIL import Image


class PredictionWorker(QObject):
    """公式识别工作线程"""
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_wrapper, image: Image.Image, model_name: str):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name

    def run(self):
        try:
            res = self.model_wrapper.predict(self.image, model_name=self.model_name)
            if not res or not res.strip():
                self.failed.emit("识别结果为空")
            else:
                self.finished.emit(res.strip())
        except Exception as e:
            self.failed.emit(str(e))

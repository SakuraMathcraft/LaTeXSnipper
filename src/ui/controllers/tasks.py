"""Own desktop recognition preparation, cancellation and result delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
import logging

from PyQt6.QtCore import QObject, pyqtSignal

from runtime.background_task import BackgroundTask

logger = logging.getLogger(f"latexsnipper.{__name__}")


class RecognitionTaskController(QObject):
    changed = pyqtSignal()

    def __init__(self, parent: QObject, handwriting_busy: Callable[[], bool]):
        super().__init__(parent)
        self._task = BackgroundTask(self)
        self._task.succeeded.connect(self._succeeded)
        self._task.failed.connect(self._failed)
        self._task.finished.connect(self._finished)
        self._cancel_requested = False
        self._handwriting_busy = handwriting_busy
        self._on_success = None
        self._on_failure = None
        self._closing = False
        self._preparation = None
        self._sequence = 0

    @property
    def busy(self):
        return self._task.busy or self._preparation is not None

    def prepare(self):
        if self.busy or self._closing:
            raise RuntimeError("A recognition task is already active or shutting down")
        self._sequence += 1
        self._preparation = self._sequence
        self.changed.emit()
        return self._preparation

    def finish_preparation(self, token):
        if self._closing or self._preparation != token:
            return False
        self._preparation = None
        self.changed.emit()
        return True

    def is_busy(self, source="main"):
        return self.busy or (source != "handwriting" and self._handwriting_busy())

    def start(self, worker, on_success, on_failure):
        if self.busy or self._closing:
            raise RuntimeError("A recognition task is already active or shutting down")
        self._cancel_requested = False
        self._on_success = on_success
        self._on_failure = on_failure
        self._task.start(worker)
        self.changed.emit()

    def _succeeded(self, result):
        try:
            if (
                not self._closing
                and self._cancel_requested
                and (self._on_failure is not None)
            ):
                self._on_failure("canceled by user")
            elif not self._closing and self._on_success is not None:
                self._on_success(result)
        except Exception:
            logger.exception("识别结果处理失败")

    def _failed(self, message):
        try:
            if not self._closing and self._on_failure is not None:
                self._on_failure(message)
        except Exception:
            logger.exception("识别错误处理失败")

    def _finished(self):
        self._on_success = None
        self._on_failure = None
        self.changed.emit()

    def cancel(self):
        if self._preparation is not None:
            self._cancel_requested = True
            self._preparation = None
            self.changed.emit()
            return True
        if self.worker is None:
            return False
        self._cancel_requested = True
        return self._task.cancel()

    def clear_cancellation(self):
        self._cancel_requested = False

    def shutdown(self):
        self._closing = True
        self._cancel_requested = True
        self._preparation = None
        self._on_success = None
        self._on_failure = None
        self._task.shutdown()

    @property
    def worker(self):
        return self._task.worker

    @property
    def cancel_requested(self):
        return self._cancel_requested

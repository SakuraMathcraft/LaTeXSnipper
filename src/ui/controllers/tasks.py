"""Own the active desktop recognition task and its Qt thread lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(f"latexsnipper.{__name__}")


class RecognitionTaskController(QObject):
    changed = pyqtSignal()

    def __init__(self, parent: QObject, handwriting_busy: Callable[[], bool]):
        super().__init__(parent)
        self._thread = None
        self._worker = None
        self._cancel_requested = False
        self._handwriting_busy = handwriting_busy
        self._on_success = None
        self._on_failure = None
        self._closing = False
        self._preparation = None
        self._sequence = 0

    @property
    def busy(self):
        return self._thread is not None or self._preparation is not None

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
        self._worker = worker
        self._on_success = on_success
        self._on_failure = on_failure
        self._thread = QThread(self)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.finished.connect(self._succeeded)
        worker.failed.connect(self._failed)
        self._thread.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._finished)
        self.changed.emit()
        self._thread.start()

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
        finally:
            if self._thread is not None:
                self._thread.quit()

    def _failed(self, message):
        try:
            if not self._closing and self._on_failure is not None:
                self._on_failure(message)
        except Exception:
            logger.exception("识别错误处理失败")
        finally:
            if self._thread is not None:
                self._thread.quit()

    def _finished(self):
        thread = self._thread
        self._worker = None
        self._thread = None
        self._on_success = None
        self._on_failure = None
        if thread is not None:
            thread.deleteLater()
        self.changed.emit()

    def cancel(self):
        if self._preparation is not None:
            self._cancel_requested = True
            self._preparation = None
            self.changed.emit()
            return True
        if self._worker is None:
            return False
        self._cancel_requested = True
        self._worker.cancel()
        if self._thread is not None:
            self._thread.requestInterruption()
        return True

    def clear_cancellation(self):
        self._cancel_requested = False

    def shutdown(self):
        self._closing = True
        self.cancel()
        thread = self._thread
        if thread is not None:
            thread.quit()
            if not thread.wait(3000):
                logger.info("等待识别任务取消完成")
                thread.wait()
            self._finished()

    @property
    def worker(self):
        return self._worker

    @property
    def thread(self):
        return self._thread

    @property
    def cancel_requested(self):
        return self._cancel_requested

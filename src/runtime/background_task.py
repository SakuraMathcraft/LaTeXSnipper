"""Run blocking recognition work without holding application shutdown open."""

from __future__ import annotations

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(f"latexsnipper.{__name__}")


class BackgroundTask(QObject):
    """Own a worker exposing run/cancel and single-value finished/failed signals.

    Worker methods must not use widgets or depend on a Qt event loop. Result
    signals and cleanup are queued to the owner's thread, in emission order.
    """

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)
    finished = pyqtSignal()
    _completed = pyqtSignal()

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._worker = None
        self._closing = False
        self._completed.connect(self._finish)

    @property
    def busy(self):
        return self._worker is not None

    @property
    def worker(self):
        return self._worker

    def start(self, worker):
        if self.busy or self._closing:
            raise RuntimeError("A task is already active or shutting down")
        self._worker = worker
        worker.finished.connect(self._succeed)
        worker.failed.connect(self._fail)
        # Workers use blocking I/O and emit signals; they do not need a Qt event loop.
        # Keep the worker alive until its queued result has been handled on the UI.
        thread = threading.Thread(
            target=self._run, args=(worker,), name="RecognitionTask", daemon=True
        )
        thread.start()

    def _run(self, worker):
        try:
            worker.run()
        except Exception as exc:
            logger.exception("识别任务执行失败")
            try:
                worker.failed.emit(str(exc))
            except RuntimeError:
                pass
        finally:
            try:
                self._completed.emit()
            except RuntimeError:
                # The owning window may have been deleted while I/O was pending.
                worker.deleteLater()

    def _succeed(self, result):
        if not self._closing:
            self.succeeded.emit(result)

    def _fail(self, message):
        if not self._closing:
            self.failed.emit(message)

    def _finish(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if not self._closing:
            self.finished.emit()

    def cancel(self):
        if self._worker is None:
            return False
        self._worker.cancel()
        return True

    def shutdown(self):
        self._closing = True
        self.cancel()

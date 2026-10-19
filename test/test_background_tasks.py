"""Exercise cancellation and window ownership while external I/O is blocked."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from backend.external_model.schemas import ExternalModelConfig
from recognition.external_workers import ExternalModelWorker
from recognition.jobs import RecognitionJobCoordinator
from runtime.background_task import BackgroundTask
from ui.controllers.tasks import RecognitionTaskController


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


def wait_for(application, predicate):
    for _ in range(200):
        application.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


@pytest.mark.parametrize("cancel", [False, True])
def test_result_delivery_runs_on_ui_thread_and_can_be_reused(application, cancel):
    started, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()

    class Worker(QObject):
        finished = pyqtSignal(object)
        failed = pyqtSignal(str)

        def run(self):
            started.set()
            assert release.wait(5)
            self.finished.emit("result")

        def cancel(self):
            pass

    tasks = RecognitionTaskController(application, lambda: False)
    results, failures = [], []
    try:
        for round_index in range(2):
            started.clear()
            release.clear()
            tasks.start(
                Worker(),
                lambda result: results.append((result, threading.get_ident())),
                failures.append,
            )
            assert started.wait(2)
            if cancel:
                assert tasks.cancel()
            release.set()
            wait_for(application, lambda: not tasks.busy)
            if cancel:
                assert failures == ["canceled by user"] * (round_index + 1)
                assert not results
            else:
                assert results == [("result", main_thread)] * (round_index + 1)
                assert not failures
    finally:
        release.set()
        tasks.shutdown()


@pytest.mark.parametrize("source", ["main", "handwriting"])
def test_window_shutdown_does_not_wait_for_external_request(
    application, monkeypatch, source
):
    started, release, returned = (threading.Event() for _ in range(3))

    def predict(*args):
        started.set()
        try:
            assert release.wait(5)
            return "x+1"
        finally:
            returned.set()

    coordinator = RecognitionJobCoordinator(None, external_predictor=predict)
    config = ExternalModelConfig(model_name="test-model")
    parent = QWidget()
    tasks = RecognitionTaskController(parent, lambda: False)
    results, errors = [], []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    window = None
    try:
        if source == "main":
            worker = ExternalModelWorker(
                coordinator, config, Image.new("RGB", (20, 20))
            )
            tasks.start(worker, results.append, results.append)
            shutdown = tasks.shutdown
            owner = parent
        else:
            import handwriting.handwriting_window as handwriting

            monkeypatch.setattr(handwriting, "PreviewWebView", None)
            window = handwriting.HandwritingWindow(
                None, models=None, coordinator=coordinator, tasks=tasks
            )
            monkeypatch.setattr(
                window, "_get_active_model_key", lambda: "external_model"
            )
            monkeypatch.setattr(window, "_is_external_model_ready", lambda: True)
            monkeypatch.setattr(
                window, "_get_handwriting_external_model_config", lambda: config
            )
            monkeypatch.setattr(
                window.canvas,
                "export_image",
                lambda: SimpleNamespace(
                    is_empty=False,
                    image=QImage(20, 20, QImage.Format.Format_RGB32),
                ),
            )
            window._run_recognition()
            assert window.is_recognizing_busy()
            shutdown = window.shutdown
            owner = window
        assert started.wait(2)
        before = time.monotonic()
        shutdown()
        assert time.monotonic() - before < 0.5
        if window is not None:
            window._schedule_recognition()
            window._run_recognition()
            assert not window.recognize_timer.isActive()
        # The request is still blocked when the window is destroyed.
        assert not returned.is_set()
        sip.delete(owner)
        release.set()
        assert returned.wait(2)
        QTest.qWait(100)
        assert not results
        assert not errors
    finally:
        release.set()
        tasks.shutdown()
        coordinator.stop()
        if not sip.isdeleted(parent):
            sip.delete(parent)
        if window is not None and not sip.isdeleted(window):
            sip.delete(window)


def test_worker_exception_is_delivered_and_releases_busy_state(application):
    class Worker(QObject):
        finished = pyqtSignal(object)
        failed = pyqtSignal(str)

        def run(self):
            raise RuntimeError("unexpected worker failure")

        def cancel(self):
            pass

    task = BackgroundTask(application)
    errors = []
    task.failed.connect(errors.append)
    task.start(Worker())
    wait_for(application, lambda: not task.busy)
    assert errors == ["unexpected worker failure"]
    task.shutdown()


def test_application_exits_with_an_unresponsive_request():
    root = Path(__file__).resolve().parents[1]
    code = """
import sys, threading
sys.path.insert(0, sys.argv[1])
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6 import sip
from ui.controllers.tasks import RecognitionTaskController
started = threading.Event()
class Worker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    def run(self):
        started.set()
        threading.Event().wait()
    def cancel(self):
        pass
app = QApplication([])
window = QWidget()
tasks = RecognitionTaskController(window, lambda: False)
tasks.start(Worker(), lambda _: None, lambda _: None)
assert started.wait(2)
tasks.shutdown()
sip.delete(window)
app.processEvents()
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code, str(root / "src")],
        cwd=root,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=8,
    )
    assert result.returncode == 0, result.stdout + result.stderr

"""Verify the real UI import graph in an isolated interpreter."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ui.controllers.tasks import RecognitionTaskController


@pytest.fixture(scope="session")
def controller_app():
    return QApplication.instance() or QApplication([])


def test_main_window_imports_without_test_stubs():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path[:0] = sys.argv[1:]; from ui.main_window import MainWindow; assert callable(MainWindow)",
            str(root / "src"),
            str(root),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_task_result_is_delivered_before_worker_resources_are_released(controller_app):

    class Worker(QObject):
        finished = pyqtSignal(object)
        failed = pyqtSignal(str)

        def run(self):
            self.finished.emit("recognized")

        def cancel(self):
            pass

    tasks = RecognitionTaskController(controller_app, lambda: False)
    worker = Worker()
    delivered = []
    tasks.start(
        worker,
        lambda result: delivered.append((result, tasks.worker is worker, tasks.busy)),
        lambda error: pytest.fail(error),
    )
    try:
        for _ in range(100):
            QTest.qWait(10)
            if not tasks.busy:
                break
        assert delivered == [("recognized", True, True)]
        assert not tasks.busy
    finally:
        tasks.shutdown()


def test_cancelling_preparation_rejects_a_late_warmup_callback(controller_app):
    tasks = RecognitionTaskController(controller_app, lambda: False)
    first = tasks.prepare()
    assert tasks.is_busy()
    assert tasks.cancel()
    assert not tasks.finish_preparation(first)
    second = tasks.prepare()
    assert not tasks.finish_preparation(first)
    assert tasks.finish_preparation(second)
    assert not tasks.is_busy()
    tasks.shutdown()


def test_main_window_controls_keep_configuration_and_preview_in_sync(
    controller_app, monkeypatch, tmp_path
):
    from runtime import app_paths
    from ui import main_window_layout
    from ui.main_window import MainWindow

    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", tmp_path)
    monkeypatch.setattr(main_window_layout, "ensure_webengine_loaded", lambda: False)
    window = MainWindow()
    try:
        assert (
            window.results.coordinator is window.automation_api.recognition_coordinator
        )
        window.preview.set_source("x+1", "mathcraft")
        window.history.add_named_record("x+1", "mathcraft", "sample")
        assert window.latex_editor.toPlainText() == "x+1"
        assert window.history.label_for("x+1") == "sample"
        window.windows.open_settings()
        settings = window.windows.settings_window
        assert settings.context.cfg is window.cfg
        assert settings.context.models is window.models
        window.models.select_model("external_model")
        assert window.cfg.get("recognition_backend") == "external_model"
        assert window.models.current_model == "external_model"
    finally:
        window.lifecycle.prepare_restart()
        window.close()
        window.deleteLater()
        controller_app.processEvents()

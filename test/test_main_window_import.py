"""Verify the real UI import graph in an isolated interpreter."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from ui.controllers.tasks import RecognitionTaskController


@pytest.mark.parametrize("missing_pdf", [False, True])
def test_application_resource_validation_reports_without_opening_the_ui(
    tmp_path, missing_pdf
):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "application-validation.json"
    code = (
        "import runpy,sys; "
        + ("sys.modules['fitz']=None; " if missing_pdf else "")
        + "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            code,
            str(root / "src/main.py"),
            "--validate-application",
            str(output),
        ],
        cwd=root,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --no-sandbox",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    if missing_pdf:
        assert result.returncode == 1
        assert "fitz" in report["error"]
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert report == {
            "pdf": True,
            "xml": True,
            "mathjax_svg": True,
            "mathjax_mathml": True,
            "network_speed": True,
        }


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


@pytest.fixture
def settings_window(controller_app, monkeypatch, tmp_path):
    from runtime import app_paths
    from ui import main_window_layout
    from ui.main_window import MainWindow

    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", tmp_path)
    monkeypatch.setattr(main_window_layout, "ensure_webengine_loaded", lambda: False)
    window = MainWindow()
    window.windows.open_settings()
    try:
        yield window.windows.settings_window
    finally:
        window.lifecycle.prepare_restart()
        window.close()
        window.deleteLater()
        controller_app.processEvents()


@pytest.mark.parametrize("ok", [True, False])
def test_connection_check_restores_controls_and_reports_outcome(
    controller_app, monkeypatch, settings_window, ok
):
    notices = []
    monkeypatch.setattr(
        "recognition.external_workers.ExternalModelClient.test_connection",
        lambda self: (ok, "connection refused"),
    )
    monkeypatch.setattr(
        settings_window, "_show_info", lambda *notice: notices.append(notice)
    )
    settings_window._test_external_model_connection()
    for _ in range(100):
        QTest.qWait(10)
        if settings_window._external_test_task is None:
            break
    assert settings_window.external_test_btn.isEnabled()
    assert notices[-1][-1] == ("success" if ok else "error")


@pytest.mark.parametrize("delete_window", [False, True])
def test_settings_close_ignores_pending_connection_check(
    controller_app, monkeypatch, settings_window, delete_window
):
    from PyQt6 import sip

    started, release, returned = (threading.Event() for _ in range(3))
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    notices = []
    monkeypatch.setattr(
        settings_window, "_show_info", lambda *notice: notices.append(notice)
    )

    def test_connection(self):
        started.set()
        assert release.wait(5)
        returned.set()
        return True, "connected"

    monkeypatch.setattr(
        "recognition.external_workers.ExternalModelClient.test_connection",
        test_connection,
    )
    try:
        settings_window._test_external_model_connection()
        assert started.wait(2)
        settings_window.shutdown()
        if delete_window:
            sip.delete(settings_window)
        release.set()
        assert returned.wait(2)
        QTest.qWait(100)
        assert not errors
        assert not notices
    finally:
        release.set()

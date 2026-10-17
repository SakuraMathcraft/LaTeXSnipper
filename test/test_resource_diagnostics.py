"""Exercise diagnostics opened before the asynchronous model warmup completes."""

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from backend.mathcraft.model import ModelWrapper
from ui import resource_diagnostics
from ui.settings_resources_mixin import SettingsResourcesMixin


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["resource-diagnostics-tests"])


def pump(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


class Models(QObject):
    status_changed = pyqtSignal(str)
    selection_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.model = ModelWrapper(auto_warmup=False)
        self.warming_up = True


class Settings(SettingsResourcesMixin, QWidget):
    def __init__(self, models):
        super().__init__()
        self.context = SimpleNamespace(models=models)


@pytest.mark.parametrize("succeeds", [False, True])
@pytest.mark.parametrize("close_during_warmup", [False, True])
def test_diagnostics_follow_warmup_completion_and_reopen(
    app, monkeypatch, succeeds, close_during_warmup
):
    monkeypatch.setattr(resource_diagnostics, "installed_resources", lambda: None)
    models = Models()
    settings = Settings(models)
    complete = threading.Event()
    finished = threading.Event()

    def request(*_args, **_kwargs):
        assert complete.wait(3)
        if not succeeds:
            raise ModuleNotFoundError("No module named 'onnxruntime'")
        return {
            "ready": True,
            "provider_info": {
                "active_provider": "CPUExecutionProvider",
                "device": "cpu",
            },
        }

    monkeypatch.setattr(models.model, "_send_worker_request", request)

    def warmup():
        models.model.warmup()
        models.warming_up = False
        models.status_changed.emit("finished")
        finished.set()

    thread = threading.Thread(target=warmup)
    thread.start()
    try:
        settings._show_resource_diagnostics()
        dialog = settings._resource_diagnostics_dialog
        pump(app, lambda: dialog._report is not None)
        initial = json.loads(dialog.output.toPlainText())
        assert initial["status"] == "warming-up"
        assert initial["provider"] == {} and initial["failure"] == {}
        if close_during_warmup:
            dialog.close()
        complete.set()
        expected = "ready" if succeeds else "failed"
        pump(
            app,
            lambda: (
                finished.is_set()
                and json.loads(dialog.output.toPlainText())["status"] == expected
            ),
        )
        settings._show_resource_diagnostics()
        assert settings._resource_diagnostics_dialog is dialog
        report = json.loads(dialog.output.toPlainText())
        if succeeds:
            assert report["provider"]["active_provider"] == "CPUExecutionProvider"
            assert report["failure"] == {}
        else:
            assert report["failure"]["code"] == "ONNXRUNTIME_MISSING"
    finally:
        complete.set()
        thread.join(3)
        settings.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_component_hashing_keeps_gui_responsive_and_runtime_current(app, monkeypatch):
    models = Models()
    release = threading.Event()
    component = SimpleNamespace(name="application", content_sha256="a" * 64)
    manifest = SimpleNamespace(
        version="4.0.0", target=("windows", "x86_64", "cpu"), components=(component,)
    )
    monkeypatch.setattr(
        resource_diagnostics,
        "installed_resources",
        lambda: SimpleNamespace(root=Path("installed"), manifest=manifest),
    )

    def verify(*_args):
        assert release.wait(3)
        return ("missing.dll",)

    monkeypatch.setattr(resource_diagnostics, "verify_component", verify)
    dialog = resource_diagnostics.ResourceDiagnosticsDialog(models)
    try:
        dialog.show()
        events = []
        QTimer.singleShot(0, lambda: events.append("responsive"))
        pump(app, lambda: bool(events))
        models.warming_up = False
        models.model.provider_info = {"active_provider": "CPUExecutionProvider"}
        models.model._ready = True
        models.status_changed.emit("ready")
        release.set()
        pump(app, lambda: dialog._report is not None)
        report = json.loads(dialog.output.toPlainText())
        assert report["status"] == "ready"
        assert report["provider"]["active_provider"] == "CPUExecutionProvider"
        assert report["components"]["application"]["damaged"] == ["missing.dll"]
    finally:
        release.set()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_reopening_refreshes_component_integrity(app, monkeypatch):
    models = Models()
    manifest = SimpleNamespace(
        version="4.0.0",
        target=("windows", "x86_64", "cpu"),
        components=(SimpleNamespace(name="application", content_sha256="a" * 64),),
    )
    monkeypatch.setattr(
        resource_diagnostics,
        "installed_resources",
        lambda: SimpleNamespace(root=Path("installed"), manifest=manifest),
    )
    damaged = []
    monkeypatch.setattr(
        resource_diagnostics, "verify_component", lambda *args: tuple(damaged)
    )
    dialog = resource_diagnostics.ResourceDiagnosticsDialog(models)
    try:
        dialog.show()
        pump(app, lambda: not dialog._checking)
        assert (
            json.loads(dialog.output.toPlainText())["components"]["application"][
                "damaged"
            ]
            == []
        )
        dialog.close()
        damaged.append("damaged.dll")
        dialog.show()
        pump(app, lambda: not dialog._checking)
        assert (
            json.loads(dialog.output.toPlainText())["components"]["application"][
                "damaged"
            ]
            == damaged
        )
    finally:
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

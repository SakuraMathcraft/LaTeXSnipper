"""Exercise model-resource actions across repeated opens and pending inspection."""

import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from mathcraft_ocr.cache import ModelCacheState
from ui import model_resources_dialog
from ui.settings_resources_mixin import SettingsResourcesMixin


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["model-resources-test"])


class SettingsHarness(SettingsResourcesMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.button = QPushButton(self)
        self.button.clicked.connect(self._show_model_resources)


def wait_for_directory(app, dialog):
    deadline = time.monotonic() + 3
    while not dialog.open_directory.isEnabled() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert dialog.open_directory.isEnabled()


@pytest.mark.parametrize("close_while_checking", [False, True])
def test_model_resources_can_be_reopened_without_unhandled_exceptions(
    app,
    tmp_path,
    monkeypatch,
    close_while_checking,
):
    ready = threading.Event()
    if not close_while_checking:
        ready.set()
    states = {
        "formula": ModelCacheState("formula", tmp_path / "formula", True, True, ())
    }

    def inspect():
        assert ready.wait(3)
        return states

    resources = SimpleNamespace(manifest_path=None, root=tmp_path, inspect=inspect)
    monkeypatch.setattr(model_resources_dialog, "installed_resources", lambda: None)
    monkeypatch.setattr(
        model_resources_dialog, "desktop_model_resources", lambda _: resources
    )
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    settings = SettingsHarness()
    try:
        settings.button.click()
        dialog = settings._model_resources_dialog
        if not close_while_checking:
            wait_for_directory(app, dialog)
        for _ in range(3):
            dialog.close()
            settings.button.click()
            assert not errors
            assert settings._model_resources_dialog is dialog
            assert dialog.isVisible()
        ready.set()
        wait_for_directory(app, dialog)
        assert dialog.rows_layout.count() == 2
    finally:
        ready.set()
        settings.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_reopening_refreshes_downloaded_models_and_directory_action(
    app, tmp_path, monkeypatch
):
    cache = tmp_path / "models"

    def inspect():
        complete = cache.is_dir()
        return {
            "formula": ModelCacheState(
                "formula",
                cache / "formula",
                complete,
                complete,
                () if complete else ("model.onnx",),
            )
        }

    resources = SimpleNamespace(manifest_path=None, root=cache, inspect=inspect)
    monkeypatch.setattr(model_resources_dialog, "installed_resources", lambda: None)
    monkeypatch.setattr(
        model_resources_dialog, "desktop_model_resources", lambda _: resources
    )
    settings = SettingsHarness()
    try:
        settings._show_model_resources()
        dialog = settings._model_resources_dialog
        deadline = time.monotonic() + 3
        while dialog._checking and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not dialog.open_directory.isEnabled()
        dialog.close()
        cache.mkdir()
        settings._show_model_resources()
        wait_for_directory(app, dialog)
        assert dialog.rows_layout.count() == 2
    finally:
        settings.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

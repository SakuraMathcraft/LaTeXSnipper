from __future__ import annotations

import sys
import threading
import time

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from ui.controllers.model_runtime import ModelRuntimeController
from ui.controllers.status import StatusController


class Config:
    def __init__(self):
        self.data = {"recognition_backend": "mathcraft", "mathcraft_mode": "text"}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def set_many(self, values):
        self.data.update(values)


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("rounds", [1, 2])
def test_incomplete_cache_reports_once_per_warmup_without_qt_slot_errors(
    application, monkeypatch, rounds
):
    errors, notices = [], []
    monkeypatch.setattr(sys, "excepthook", lambda *error: errors.append(error))
    monkeypatch.setattr(
        "ui.controllers.model_runtime.InfoBar.warning",
        lambda **notice: notices.append(notice),
    )
    view = QWidget()
    models = ModelRuntimeController(view, Config(), None, None, lambda: view)
    status = StatusController(view, models, lambda: view)
    models.model.status_signal.connect(status.show_status_message)
    monkeypatch.setattr(models.model, "is_model_ready", lambda mode: False)
    monkeypatch.setattr(
        models, "_should_show_mathcraft_warmup_started_infobar", lambda mode: False
    )

    def warmup(mode):
        for detail in ("missing model; downloading", "resuming archive from 1.0 MB"):
            models.model.status_signal.emit(f"[INFO] MathCraft model cache: {detail}")
        return True

    monkeypatch.setattr(models.model, "warmup", warmup)
    try:
        for round_index in range(rounds):
            models.ensure_warmup(preferred_model="mathcraft_text")
            models._warmup_thread.join(timeout=2)
            assert not models._warmup_thread.is_alive()
            for _ in range(50):
                application.processEvents()
                if not models.warming_up:
                    break
                QTest.qWait(10)
            assert not models.warming_up
            assert not errors
            assert len(notices) == round_index + 1
            assert "missing model; downloading" in notices[-1]["content"]
    finally:
        models.shutdown()
        view.close()


def test_shutdown_bounds_warmup_wait_and_ignores_late_completion(
    application, monkeypatch
):
    started, release = threading.Event(), threading.Event()
    view = QWidget()
    models = ModelRuntimeController(view, Config(), None, None, lambda: view)
    callbacks = []
    monkeypatch.setattr(models.model, "is_model_ready", lambda mode: False)
    monkeypatch.setattr(
        models, "_should_show_mathcraft_warmup_started_infobar", lambda mode: False
    )

    def warmup(mode):
        started.set()
        assert release.wait(5)
        return True

    monkeypatch.setattr(models.model, "warmup", warmup)
    try:
        models.ensure_warmup(on_ready=lambda: callbacks.append("ready"))
        assert started.wait(2)
        before = time.monotonic()
        models.shutdown()
        assert time.monotonic() - before < 1.5
        assert not models.warming_up
        release.set()
        models._warmup_thread.join(timeout=2)
        application.processEvents()
        assert not callbacks
    finally:
        release.set()
        models.shutdown()
        view.close()

"""Exercise process ownership and activation through real local sockets."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from runtime import single_instance


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("ready", [True, False])
def test_second_launch_restores_existing_window(app, tmp_path, monkeypatch, ready):
    monkeypatch.setattr(single_instance, "app_state_dir", lambda: tmp_path)
    assert single_instance.ensure_single_instance()
    single_instance.start_instance_activation(app)
    window = QWidget()
    window.setProperty("recognition_state", "in progress")
    activations = []

    def activate():
        window.showNormal()
        activations.append(window.property("recognition_state"))

    if ready:
        single_instance.set_instance_activation_handler(activate)
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from PyQt6.QtWidgets import QApplication
from runtime import single_instance
from application.bootstrap import _ensure_single_instance
single_instance.app_state_dir = lambda: Path(sys.argv[2])
app = QApplication([])
_ensure_single_instance(app)
raise RuntimeError('A second application instance was allowed to start')
"""
    child = subprocess.Popen(
        [
            sys.executable,
            "-X",
            "utf8",
            "-c",
            code,
            str(Path(__file__).resolve().parents[1] / "src"),
            str(tmp_path),
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        deadline = time.monotonic() + 15
        while child.poll() is None and time.monotonic() < deadline:
            QTest.qWait(10)
        assert child.poll() is not None, "The second launch did not exit"
        output, errors = child.communicate(timeout=1)
        assert child.returncode == 0, output + errors
        QTest.qWait(20)
        if not ready:
            assert not window.isVisible()
            single_instance.set_instance_activation_handler(activate)
        assert window.isVisible()
        assert activations == ["in progress"]
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
        window.close()
        single_instance.release_single_instance_lock()

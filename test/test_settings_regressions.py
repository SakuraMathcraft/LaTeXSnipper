from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import bootstrap.deps_ui as deps_ui_module
import runtime.environment_terminal as terminal_module
import ui.settings_environment_mixin as environment_module
import ui.settings_mathcraft_mixin as mathcraft_module
from runtime.config_manager import ConfigManager
from runtime.environment_terminal import (
    main_environment_terminal_is_active,
    open_main_environment_terminal,
)
from ui.automation_api_controller import AutomationApiController
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin


def test_hosted_user_notice_uses_a_nonblocking_infobar(monkeypatch) -> None:
    calls: list[tuple[object, str, str, str, int]] = []
    monkeypatch.setattr(
        deps_ui_module,
        "show_info_bar",
        lambda parent, title, content, level, duration: calls.append(
            (parent, title, content, level, duration)
        ),
    )
    parent = object()

    assert deps_ui_module.show_user_notice("错误", "操作失败", parent) is True
    assert calls == [(parent, "错误", "操作失败", "error", 5000)]


def test_unready_environment_terminal_reports_through_infobar() -> None:
    messages: list[tuple[str, str, str]] = []

    class Harness(environment_module.SettingsEnvironmentMixin):
        @staticmethod
        def _resolve_dynamic_main_pyexe() -> str:
            return ""

        def _show_info(self, title: str, content: str, level: str = "info") -> None:
            messages.append((title, content, level))

    Harness()._open_terminal()

    assert len(messages) == 1
    assert messages[0][0] == "环境未就绪"
    assert messages[0][2] == "warning"


def test_config_manager_updates_multiple_values_with_one_save() -> None:
    manager = ConfigManager.__new__(ConfigManager)
    manager.data = {}
    saves: list[None] = []
    manager.save = lambda: saves.append(None)

    manager.set_many({"one": 1, "two": 2})

    assert manager.data == {"one": 1, "two": 2}
    assert saves == [None]


def test_automation_api_start_and_stop_operations_are_serialized() -> None:
    class Config:
        def __init__(self) -> None:
            self.data = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value) -> None:
            self.data[key] = value

        def set_many(self, values) -> None:
            self.data.update(values)

    harness = AutomationApiController(Config(), recognition_coordinator=None)
    pending = []
    results = []
    harness._run_automation_api_worker = lambda worker, done: pending.append((worker, done))

    harness._start_automation_api_async(lambda ok, message: results.append((ok, message)))
    harness._stop_automation_api_async(lambda ok, message: results.append((ok, message)))

    assert len(pending) == 1
    assert pending[0][0]._action == "start"

    server = object()
    pending[0][1](True, "started", server)
    assert len(pending) == 2
    assert pending[1][0]._action == "stop"
    assert pending[1][0]._server is server

    pending[1][1](True, "stopped", None)
    assert harness._automation_api_server is None
    assert results == [(True, "started"), (True, "stopped")]


def test_automation_api_unchanged_settings_do_not_restart_running_server() -> None:
    class Config:
        def __init__(self) -> None:
            self.data = {
                "automation_api_access_scope": "local",
                "automation_api_bind_address": "127.0.0.1",
                "automation_api_port": 28765,
            }

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set_many(self, values) -> None:
            self.data.update(values)

    harness = AutomationApiController(Config(), recognition_coordinator=None)
    harness._automation_api_server = object()
    stopped: list[bool] = []
    harness._stop_automation_api_async = lambda _callback=None: stopped.append(True)

    harness.update_automation_api_settings_async(
        {
            "automation_api_access_scope": "local",
            "automation_api_bind_address": "127.0.0.1",
            "automation_api_port": 28765,
        }
    )

    assert stopped == []


def test_settings_python_resolution_does_not_launch_validation_process(tmp_path: Path, monkeypatch) -> None:
    pyexe = tmp_path / ("python.exe" if os.name == "nt" else "python")
    pyexe.write_bytes(b"")
    monkeypatch.setattr(mathcraft_module, "_existing_non_launcher_pyexe_from_env", lambda: "")
    monkeypatch.setattr(mathcraft_module, "iter_python_candidates", lambda _base: [pyexe])

    class Harness(SettingsMathCraftMixin):
        def _current_install_base_dir(self):
            return tmp_path

    assert Harness()._resolve_dynamic_main_pyexe() == str(pyexe)


def test_compute_mode_label_uses_mathcraft_device_report() -> None:
    class Harness(SettingsMathCraftMixin):
        def _set_compute_mode_text(self, text: str, state: str) -> None:
            self.result = (text, state)

    harness = Harness()

    assert harness._apply_compute_mode_from_info(
        {
            "present": True,
            "device": "gpu",
            "device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
            "device_verified": True,
        },
        sys.executable,
    ) is True
    assert harness.result == (
        "🟢 GPU 模式: NVIDIA GeForce RTX 4050 Laptop GPU",
        "gpu",
    )


def test_main_environment_terminal_rejects_an_active_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_terminal_dir", lambda: tmp_path)
    monkeypatch.setattr(terminal_module, "_pid_is_running", lambda pid: pid == 42)
    terminal_module._write_session(42, "active")

    assert main_environment_terminal_is_active() is True
    assert terminal_module._claim_session() is False


def test_main_environment_terminal_discards_a_dead_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_terminal_dir", lambda: tmp_path)
    monkeypatch.setattr(terminal_module, "_pid_is_running", lambda _pid: False)
    terminal_module._write_session(42, "active")

    assert main_environment_terminal_is_active() is False
    assert terminal_module._claim_session() is True


def test_main_environment_terminal_keeps_original_developer_help(monkeypatch) -> None:
    policy = type("Policy", (), {"pip_command": lambda self: "pip install onnxruntime-gpu"})()
    monkeypatch.setattr(environment_module, "_mathcraft_code_roots", lambda: [r"E:\LaTexSnipper"])
    monkeypatch.setattr(environment_module, "onnxruntime_gpu_policy", lambda _pyexe: policy)
    monkeypatch.setattr(environment_module, "onnxruntime_cpu_spec", lambda _pyexe: "onnxruntime<2")

    lines = environment_module.SettingsEnvironmentMixin._main_environment_terminal_help(sys.executable)
    text = "\n".join(lines)

    assert "[Model Policy]" in text
    assert "[ONNX Runtime]" in text
    assert "[MathCraft CPU/ONNX Check]" in text
    assert "from mathcraft_ocr.cli import main" in text
    assert "[Diagnostics]" in text
    assert "[Cache Clean]" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows terminal invocation")
def test_main_environment_terminal_is_bound_and_single_instance(tmp_path: Path, monkeypatch) -> None:
    pyexe = Path(sys.executable)
    calls: list[tuple[list[str], dict]] = []

    def popen(args, **kwargs):
        calls.append((list(args), kwargs))
        return type("Process", (), {"pid": 4242})()

    monkeypatch.setattr(terminal_module, "_terminal_dir", lambda: tmp_path)
    monkeypatch.setattr(terminal_module, "_pid_is_running", lambda pid: pid == 4242)
    monkeypatch.setattr(terminal_module.subprocess, "Popen", popen)

    help_lines = [
        "LaTeXSnipper Terminal - Main Environment",
        "[MathCraft CPU/ONNX Check]",
        "python -c \"from mathcraft_ocr.cli import main\"",
        "pip check",
        "ort.get_available_providers()",
    ]
    def factory():
        return help_lines

    assert open_main_environment_terminal(str(pyexe), tmp_path, factory) is True
    assert open_main_environment_terminal(str(pyexe), tmp_path, factory) is False

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == ["cmd.exe", "/d", "/k"]
    assert kwargs["creationflags"] == subprocess.CREATE_NEW_CONSOLE
    assert kwargs["env"]["LATEXSNIPPER_PYEXE"] == str(pyexe)
    assert kwargs["cwd"] == str(tmp_path)
    launcher_text = Path(args[3]).read_text(encoding="mbcs")
    assert "LaTeXSnipper Terminal - Main Environment" in launcher_text
    assert "[MathCraft CPU/ONNX Check]" in launcher_text
    assert "from mathcraft_ocr.cli import main" in launcher_text
    assert "pip check" in launcher_text
    assert "ort.get_available_providers()" in launcher_text

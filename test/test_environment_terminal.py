from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import runtime.environment_terminal as terminal_module
from runtime.environment_terminal import (
    main_environment_terminal_is_active,
    open_main_environment_terminal,
)


def test_main_environment_terminal_rejects_an_active_session(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(terminal_module, "_terminal_dir", lambda: tmp_path)
    monkeypatch.setattr(terminal_module, "_pid_is_running", lambda pid: pid == 42)
    terminal_module._write_session(42, "active")

    assert main_environment_terminal_is_active() is True
    assert terminal_module._claim_session() is False


def test_main_environment_terminal_discards_a_dead_session(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(terminal_module, "_terminal_dir", lambda: tmp_path)
    monkeypatch.setattr(terminal_module, "_pid_is_running", lambda _pid: False)
    terminal_module._write_session(42, "active")

    assert main_environment_terminal_is_active() is False
    assert terminal_module._claim_session() is True


@pytest.mark.skipif(os.name != "nt", reason="Windows terminal invocation")
def test_main_environment_terminal_is_bound_and_single_instance(
    tmp_path: Path, monkeypatch
) -> None:
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
        'python -c "from mathcraft_ocr.cli import main"',
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

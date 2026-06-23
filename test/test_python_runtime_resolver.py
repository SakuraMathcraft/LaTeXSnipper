from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_existing_dependency_python_does_not_require_ensurepip(monkeypatch, tmp_path) -> None:
    from runtime import python_runtime_resolver as resolver

    pyexe = tmp_path / "python311" / ("python.exe" if sys.platform == "win32" else "python3")
    pyexe.parent.mkdir()
    pyexe.write_text("", encoding="utf-8")

    monkeypatch.setattr(resolver, "_find_install_base_python", lambda _base: pyexe)
    monkeypatch.setattr(resolver, "_win_subprocess_kwargs", lambda: {})

    commands: list[str] = []

    def fake_run(cmd, *args, **kwargs):
        code = cmd[2]
        commands.append(code)
        if "ensurepip" in code or "venv" in code:
            return subprocess.CompletedProcess(cmd, 1, "", "missing ensurepip")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(resolver.subprocess, "run", fake_run)

    assert resolver._find_full_python(tmp_path) == str(pyexe)
    assert commands
    assert all("ensurepip" not in code and "venv" not in code for code in commands)

from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

from bootstrap import deps_python_runtime


def test_system_python3_score_windows_skips_store_alias_without_launching(monkeypatch):
    monkeypatch.setattr(deps_python_runtime.os, "name", "nt")

    score = deps_python_runtime._system_python3_score(
        PureWindowsPath(r"C:\Users\me\AppData\Local\Microsoft\WindowsApps\python.exe")
    )

    assert score == 0


def test_find_system_python3_prefers_macos_python_with_ensurepip(monkeypatch):
    monkeypatch.setattr(deps_python_runtime, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(deps_python_runtime.sys, "platform", "darwin")
    monkeypatch.setattr(deps_python_runtime, "which", lambda name: "/usr/bin/python3")

    scores = {
        Path("/usr/bin/python3"): 1,
        Path("/opt/homebrew/bin/python3"): 2,
    }
    monkeypatch.setattr(deps_python_runtime, "_system_python3_score", lambda p: scores.get(p, 0))

    found = deps_python_runtime.find_system_python3()

    assert found == Path("/opt/homebrew/bin/python3")

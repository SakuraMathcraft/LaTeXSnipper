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


def test_find_system_python3_rejects_macos_python_newer_than_supported(monkeypatch):
    monkeypatch.setattr(deps_python_runtime, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(deps_python_runtime.sys, "platform", "darwin")
    monkeypatch.setattr(deps_python_runtime, "which", lambda name: "/opt/homebrew/bin/python3")

    scores = {
        Path("/opt/homebrew/bin/python3"): 0,
        Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"): 2,
        Path("/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"): 2,
    }
    monkeypatch.setattr(deps_python_runtime, "_system_python3_score", lambda p: scores.get(p, 0))

    found = deps_python_runtime.find_system_python3()

    assert found == Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3")


def test_system_python3_score_rejects_python313_even_with_ensurepip(tmp_path, monkeypatch):
    pyexe = tmp_path / "python3"
    pyexe.write_text("#!/bin/sh\n", encoding="utf-8")

    class Result:
        returncode = 0

    def fake_run(args, *_unused_args, **_kwargs):
        code = args[2]
        if "sys.version_info < (3, 13)" in code:
            result = Result()
            result.returncode = 1
            return result
        return Result()

    monkeypatch.setattr(deps_python_runtime.subprocess, "run", fake_run)

    assert deps_python_runtime._system_python3_score(pyexe) == 0


def test_system_python3_score_rejects_python_without_ensurepip(tmp_path, monkeypatch):
    pyexe = tmp_path / "python3"
    pyexe.write_text("#!/bin/sh\n", encoding="utf-8")

    class Result:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def fake_run(args, *_unused_args, **_kwargs):
        code = args[2]
        if "import ensurepip" in code:
            return Result(1)
        return Result(0)

    monkeypatch.setattr(deps_python_runtime.subprocess, "run", fake_run)

    assert deps_python_runtime._system_python3_score(pyexe) == 0


def test_inject_private_python_paths_replaces_previous_site(monkeypatch, tmp_path):
    old_site = tmp_path / "old" / "Lib" / "site-packages"
    new_root = tmp_path / "new"
    new_site = new_root / "Lib" / "site-packages"
    old_site.mkdir(parents=True)
    new_site.mkdir(parents=True)
    pyexe = new_root / ("python.exe" if deps_python_runtime.os.name == "nt" else "python3")
    pyexe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LATEX_SNIPPER_SITE", str(old_site))
    monkeypatch.setattr(deps_python_runtime, "_active_site_packages", str(old_site))
    monkeypatch.setattr(deps_python_runtime, "_active_dll_directory_handle", None)
    monkeypatch.setattr(deps_python_runtime.sys, "path", [str(old_site), "project-root"])

    deps_python_runtime.inject_private_python_paths(pyexe)

    assert str(old_site) not in deps_python_runtime.sys.path
    assert deps_python_runtime.sys.path[0] == str(new_site)
    assert deps_python_runtime.sys.path.count(str(new_site)) == 1

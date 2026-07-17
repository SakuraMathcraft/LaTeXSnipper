# coding: utf-8

from __future__ import annotations

from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_pandoc_optional_dependency_uses_pypandoc() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = data["project"]["optional-dependencies"]["pandoc"]

    assert any(spec.startswith("pypandoc") for spec in specs)
    assert not any(spec.startswith("pandoc") for spec in specs)


def test_build_requirements_do_not_force_pandoc_runtime() -> None:
    lines = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
    specs = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    assert not any(spec.startswith("pypandoc") for spec in specs)
    assert not any(spec.startswith("pandoc") for spec in specs)


def test_pyinstaller_spec_keeps_pandoc_runtime_backend() -> None:
    spec = (ROOT / "LaTeXSnipper.spec").read_text(encoding="utf-8")
    hiddenimports = re.search(r"hiddenimports=\[(.*?)\],", spec, re.S)
    excludes = re.search(r"excludes=\[(.*?)\],", spec, re.S)
    prune_prefixes = re.search(r"remove_prefixes = \((.*?)\)", spec, re.S)

    assert hiddenimports is not None
    assert excludes is not None
    assert prune_prefixes is not None
    for module_name in (
        "exporting.pandoc_exporter",
        "runtime.pandoc_runtime",
        "pypandoc",
    ):
        assert f'"{module_name}"' in hiddenimports.group(1)
        assert f'"{module_name}"' not in excludes.group(1)
        assert f'"{module_name}"' not in prune_prefixes.group(1)


def test_pandoc_download_sources_target_the_current_release() -> None:
    from bootstrap import deps_pandoc

    archive_name, _binary_name, _archive_type = deps_pandoc._pandoc_platform_archive()
    release_path = f"/jgm/pandoc/releases/download/{deps_pandoc._PANDOC_VERSION}/{archive_name}"
    mirrors = deps_pandoc._build_pandoc_mirrors()

    assert mirrors
    assert mirrors[-1] == f"https://github.com{release_path}"
    assert all(url.startswith("https://") and release_path in url for url in mirrors)


def test_pandoc_tool_is_installed_under_app_tools_root(tmp_path, monkeypatch) -> None:
    from bootstrap import deps_pandoc
    from runtime import app_paths
    from runtime.dependency_python import dependency_root_from_python

    dependency_root = tmp_path / "LaTexSnipper"
    app_state = tmp_path / "state"
    external_python_root = tmp_path / "OtherDrive" / "python378"
    python_exe = external_python_root / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    scripts_python = external_python_root / "Scripts" / "python.exe"
    scripts_python.parent.mkdir()
    scripts_python.write_text("", encoding="utf-8")

    monkeypatch.setenv("LATEXSNIPPER_INSTALL_BASE_DIR", str(dependency_root))
    monkeypatch.delenv("LATEXSNIPPER_DEPS_DIR", raising=False)
    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", app_state)

    expected = app_state / "tools" / "pandoc"
    assert deps_pandoc._pandoc_data_dir(str(python_exe)) == expected
    assert deps_pandoc._pandoc_data_dir(str(scripts_python)) == expected
    assert dependency_root_from_python(dependency_root / "python311" / "python.exe") == dependency_root
    assert dependency_root_from_python(dependency_root / "python311" / "Scripts" / "python.exe") == dependency_root


def test_pandoc_exporter_ignores_unmanaged_binary_in_working_directory(tmp_path, monkeypatch) -> None:
    from exporting import pandoc_exporter

    unmanaged = tmp_path / "pandoc.exe"
    unmanaged.write_text("stub", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pandoc_exporter, "load_configured_pandoc_path", lambda: None)
    monkeypatch.setattr(pandoc_exporter.shutil, "which", lambda _name: None)

    assert pandoc_exporter._find_pandoc_binary() is None


def test_dependency_progress_close_reuses_post_install_verify_result() -> None:
    source = (ROOT / "src" / "bootstrap" / "deps_entry.py").read_text(encoding="utf-8")

    assert 'install_verified_in_progress_ui = bool(post_install_verify_passed.get("value", False))' in source
    assert "skip_next_ui_runtime_verify = install_verified_in_progress_ui" in source
    assert source.count("skip_next_ui_runtime_verify = install_verified_in_progress_ui") >= 2

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


def test_pandoc_dependency_wizard_does_not_use_dead_msi_cleanup_or_broken_proxy() -> None:
    source = (ROOT / "src" / "bootstrap" / "deps_pandoc.py").read_text(encoding="utf-8")

    assert "mirror.ghproxy.com" not in source
    assert "github.geekery.cn" not in source
    assert 'Path.cwd() / "deps" / "pandoc"' not in source
    assert "pandoc-*.msi" not in source
    assert "pandoc-*-windows-x86_64.msi" not in source


def test_pandoc_and_argos_tools_are_installed_under_app_tools_root(tmp_path, monkeypatch) -> None:
    from bootstrap import deps_pandoc
    from runtime.config_manager import DEPENDENCY_ROOT_CLEANUP_HISTORY_KEY, remember_dependency_root
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
    assert app_paths.app_tool_dir("translation_env") == app_state / "tools" / "translation_env"
    assert dependency_root_from_python(dependency_root / "python311" / "python.exe") == dependency_root
    assert dependency_root_from_python(dependency_root / "python311" / "Scripts" / "python.exe") == dependency_root

    cfg: dict[str, str] = {}
    remember_dependency_root(cfg, dependency_root)
    remember_dependency_root(cfg, dependency_root / "python311")
    assert str(dependency_root) in cfg[DEPENDENCY_ROOT_CLEANUP_HISTORY_KEY]


def test_pandoc_exporter_does_not_scan_cwd_dependency_directory() -> None:
    source = (ROOT / "src" / "exporting" / "pandoc_exporter.py").read_text(encoding="utf-8")

    assert 'Path.cwd() / "deps" / "pandoc"' not in source


def test_settings_window_does_not_duplicate_pandoc_dependency_checks() -> None:
    source = (ROOT / "src" / "ui" / "settings_window.py").read_text(encoding="utf-8")

    assert "_detect_pandoc" not in source
    assert "pandoc_detect_btn" not in source
    assert "pandoc_install_btn" not in source
    assert "check_pandoc_available" not in source


def test_dependency_progress_close_reuses_post_install_verify_result() -> None:
    source = (ROOT / "src" / "bootstrap" / "deps_entry.py").read_text(encoding="utf-8")

    assert 'install_verified_in_progress_ui = bool(post_install_verify_passed.get("value", False))' in source
    assert "skip_next_ui_runtime_verify = install_verified_in_progress_ui" in source
    assert source.count("skip_next_ui_runtime_verify = install_verified_in_progress_ui") >= 2

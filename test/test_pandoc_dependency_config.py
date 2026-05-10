# coding: utf-8

from __future__ import annotations

from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_pandoc_optional_dependency_uses_pypandoc() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = data["project"]["optional-dependencies"]["pandoc"]

    assert any(spec.startswith("pypandoc") for spec in specs)
    assert not any(spec.startswith("pandoc") for spec in specs)


def test_build_requirements_use_pypandoc_wrapper() -> None:
    lines = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
    specs = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    assert any(spec.startswith("pypandoc") for spec in specs)
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
    source = (ROOT / "src" / "bootstrap" / "deps_bootstrap.py").read_text(encoding="utf-8")

    assert "mirror.ghproxy.com" not in source
    assert "pandoc-*.msi" not in source
    assert "pandoc-*-windows-x86_64.msi" not in source


def test_settings_window_does_not_duplicate_pandoc_dependency_checks() -> None:
    source = (ROOT / "src" / "settings_window.py").read_text(encoding="utf-8")

    assert "_detect_pandoc" not in source
    assert "pandoc_detect_btn" not in source
    assert "pandoc_install_btn" not in source
    assert "check_pandoc_available" not in source

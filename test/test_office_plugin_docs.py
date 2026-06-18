# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_office_docs_describe_the_released_plugin() -> None:
    root_readme = (ROOT / "readme.md").read_text(encoding="utf-8")
    plugin_readme = (ROOT / "office_plugin" / "README.md").read_text(encoding="utf-8")

    assert "released Windows plugin" in root_readme
    assert "OfficePluginSetup-<version>.exe" in root_readme
    assert "Released Windows VSTO add-in" in plugin_readme
    assert "office_plugin\\installer\\build.bat 2.4.0 Release" in plugin_readme
    assert "127.0.0.1:28765" in plugin_readme
    assert "Office 2016 is not officially supported" in plugin_readme
    assert "Office 2024 / 2021 / 2019" in plugin_readme
    assert "OLE formulas use local MathJax layout" in plugin_readme
    assert "localhost:8765" not in plugin_readme
    assert "office_addin" not in plugin_readme
    assert "sideload" not in plugin_readme
    assert "retired" not in plugin_readme
    assert "target architecture" not in plugin_readme
    assert "active Office product architecture" not in plugin_readme

# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_office_docs_point_to_native_plugin_as_final_direction() -> None:
    root_readme = (ROOT / "readme.md").read_text(encoding="utf-8")
    plugin_readme = (ROOT / "office_plugin" / "README.md").read_text(encoding="utf-8")
    plugin_doc = (ROOT / "docs" / "office_plugin_design.md").read_text(encoding="utf-8")

    assert "Windows-native `office_plugin`" in root_readme
    assert "active Office product architecture" in plugin_readme
    assert "127.0.0.1:28765" in plugin_readme
    assert "Windows" in plugin_doc
    assert "Office 2016" in plugin_doc
    assert "Office 2024" in plugin_doc
    assert "OLE" in plugin_doc
    assert "localhost:8765" not in plugin_readme
    assert "office_addin" not in plugin_readme
    assert "sideload" not in plugin_readme
    assert "retired" not in plugin_readme

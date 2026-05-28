# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_office_docs_point_to_native_plugin_as_final_direction() -> None:
    root_readme = (ROOT / "readme.md").read_text(encoding="utf-8")
    addin_readme = (ROOT / "office_addin" / "README.md").read_text(encoding="utf-8")
    migration_doc = (ROOT / "docs" / "office_addin_design.md").read_text(encoding="utf-8")
    plugin_doc = (ROOT / "docs" / "office_plugin_design.md").read_text(encoding="utf-8")

    assert "Office Integration Direction" in root_readme
    assert "Windows-native plugin" in root_readme
    assert "office_addin` project is kept as a migration reference" in root_readme
    assert "不是 LaTeXSnipper Office 集成的最终方向" in addin_readme
    assert "Office.js Add-in 迁移记录" in migration_doc
    assert "不适合作为最终产品形态" in migration_doc
    assert "Windows 原生 Office 插件目标架构" in plugin_doc
    assert "LaTeXSnipper OLE 公式对象" in plugin_doc
    assert "本地 MathJax 原生渲染管线" in plugin_doc
    assert "双击编辑" in plugin_doc
    assert "OfficeDeploymentManifests" not in addin_readme
    assert "Microsoft 365 Integrated apps" not in addin_readme

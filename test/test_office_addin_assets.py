# coding: utf-8

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ADDIN = ROOT / "office_addin"


def test_office_addin_manifests_are_well_formed_and_have_ribbon_tabs() -> None:
    for manifest_name in ("manifest.word.xml", "manifest.powerpoint.xml"):
        root = ET.parse(ADDIN / manifest_name).getroot()
        text = ET.tostring(root, encoding="unicode")

        assert "PrimaryCommandSurface" in text
        assert "TabLaTeXSnipper" in text
        assert "OpenEditorButton" in text
        assert "InsertFormulaButton" in text
        assert "NumberedFormulaButton" in text
        assert "ScreenshotOcrButton" in text


def test_office_addin_static_icon_assets_exist() -> None:
    for size in (16, 32, 80):
        path = ADDIN / "public" / "assets" / f"icon-{size}.png"
        assert path.is_file()
        assert path.stat().st_size > 0

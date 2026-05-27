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
        assert "Auto Numbered" in text
        assert "ScreenshotOcrButton" in text
        if manifest_name == "manifest.word.xml":
            assert "LoadSelectedButton" in text
            assert "DeleteSelectedButton" in text
            assert "RenumberButton" in text
            assert "Renumber All" in text
            assert "ExecuteFunction" in text
            assert "SharedRuntime" in text
            assert 'lifetime="long"' in text
            assert "helpCommand" in text
            assert "Commands.Url" not in text
        else:
            assert "Commands.Url" not in text


def test_office_addin_static_icon_assets_exist() -> None:
    icons = ("editor", "insert", "ocr", "load", "delete", "numbered", "renumber", "help")
    sizes = (16, 20, 24, 32, 40, 48, 64, 80)
    expected_sources = {f"icon-{icon}.svg" for icon in icons}
    expected_published = {f"icon-{icon}-{size}.png" for icon in icons for size in sizes}
    assert {path.name for path in (ADDIN / "assets").iterdir() if path.is_file()} == expected_sources
    assert {path.name for path in (ADDIN / "public" / "assets").iterdir() if path.is_file()} == expected_published

    for icon in icons:
        source = ADDIN / "assets" / f"icon-{icon}.svg"
        assert source.is_file()
        assert "<text" not in source.read_text(encoding="utf-8")
        for size in sizes:
            path = ADDIN / "public" / "assets" / f"icon-{icon}-{size}.png"
            assert path.is_file()
            assert path.stat().st_size > 0

    assert not (ADDIN / "assets" / "icon-update.svg").exists()


def test_office_addin_includes_local_mathlive_runtime() -> None:
    runtime = ADDIN / "public" / "vendor" / "mathlive.min.mjs"
    license_file = ADDIN / "public" / "vendor" / "mathlive.LICENSE.txt"
    loader = (ADDIN / "src" / "taskpane" / "mathliveEditor.ts").read_text(encoding="utf-8")
    taskpane = (ADDIN / "taskpane.html").read_text(encoding="utf-8")
    dialog = (ADDIN / "src" / "dialog" / "editorDialog.html").read_text(encoding="utf-8")

    assert runtime.is_file()
    assert runtime.stat().st_size > 0
    assert license_file.is_file()
    assert "customElements.whenDefined" in loader
    assert "/vendor/mathlive.min.mjs" in taskpane
    assert "/vendor/mathlive.min.mjs" in dialog


def test_office_addin_help_documents_word_runtime_boundaries() -> None:
    help_text = (ADDIN / "help.html").read_text(encoding="utf-8")

    assert "WordApi 1.3" in help_text
    assert "SharedRuntime 1.1" in help_text
    assert "Version 2205 (Build 15202.10000)" in help_text
    assert "Word 2024" in help_text
    assert "Word 2016、2019 与 2021 不在本加载项的 Windows 支持范围内" in help_text


def test_word_insert_keeps_numbered_equation_operations_atomic() -> None:
    adapter = (ADDIN / "src" / "office" / "wordInsert.ts").read_text(encoding="utf-8")

    assert "INSERT_IN_EQUATION_ERROR" in adapter
    assert "INSERT_IN_NUMBERED_EQUATION_ERROR" in adapter
    assert "const parentTable = selection.parentTableOrNullObject;" in adapter
    assert "return paragraph.getRange(Word.RangeLocation.after);" in adapter
    assert "equationControl.parentTableCell.parentRow.delete();" in adapter
    assert "inspectNumberedLayoutTable" in adapter
    assert "normalizeNumberedEquationTable(numberControls.items[0]);" in adapter

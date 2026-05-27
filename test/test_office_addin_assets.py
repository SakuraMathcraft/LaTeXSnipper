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
        assert 'Locale="zh-CN"' in text
        if manifest_name == "manifest.word.xml":
            assert "Auto Numbered" in text
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
            assert "Insert Manual #" in text
            assert "ImageCoercion" in text
            assert "SharedRuntime" in text
            assert 'lifetime="long"' in text
            assert "ExecuteFunction" in text
            assert "insertFormulaCommand" in text
            assert "numberedFormulaCommand" in text
            assert "helpCommand" in text
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


def test_office_addin_help_documents_runtime_boundaries_in_both_languages() -> None:
    help_text = (ADDIN / "help.html").read_text(encoding="utf-8")
    chinese_help = (ADDIN / "help.zh-cn.html").read_text(encoding="utf-8")

    assert "WordApi 1.3" in help_text
    assert "SharedRuntime 1.1" in help_text
    assert "ImageCoercion 1.1" in help_text
    assert "Version 2205 (Build 15202.10000)" in help_text
    assert "Word 2024" in help_text
    assert "Office.js Capability Boundary" in help_text
    assert "Office.js 能力边界" in chinese_help
    assert "PowerPoint" in chinese_help


def test_word_insert_keeps_numbered_equation_operations_atomic() -> None:
    adapter = (ADDIN / "src" / "office" / "wordInsert.ts").read_text(encoding="utf-8")

    assert "INSERT_IN_EQUATION_ERROR" in adapter
    assert "INSERT_IN_NUMBERED_EQUATION_ERROR" in adapter
    assert "const parentTable = selection.parentTableOrNullObject;" in adapter
    assert "return paragraph.getRange(Word.RangeLocation.after);" in adapter
    assert "equationControl.parentTableCell.parentRow.delete();" in adapter
    assert "inspectNumberedLayoutTable" in adapter
    assert "normalizeNumberedEquationTable(numberControls.items[0]);" in adapter


def test_office_addin_localization_and_powerpoint_workflow_assets() -> None:
    taskpane = (ADDIN / "taskpane.html").read_text(encoding="utf-8")
    dialog = (ADDIN / "src" / "dialog" / "editorDialog.html").read_text(encoding="utf-8")
    app = (ADDIN / "src" / "taskpane" / "App.ts").read_text(encoding="utf-8")
    i18n = (ADDIN / "src" / "services" / "i18n.ts").read_text(encoding="utf-8")
    powerpoint = (ADDIN / "src" / "office" / "powerpointInsert.ts").read_text(encoding="utf-8")
    package = (ADDIN / "package.json").read_text(encoding="utf-8")

    assert "data-i18n" in taskpane
    assert "data-i18n" in dialog
    assert "Office.context.displayLanguage" in app
    assert 'insertCurrentLatex(elements, "auto")' not in app
    assert "pptManualNumberPrompt" in app
    assert 'type: "insertFailed"' in app
    assert 'type: "ocrResult"' in app
    assert "protocol" not in i18n
    assert "conversionOnly" not in i18n
    assert '"zh-CN"' in i18n
    assert "DialogParentMessageReceived" in (ADDIN / "src" / "dialog" / "editorDialog.ts").read_text(encoding="utf-8")
    assert "appendNumberToImage" in powerpoint
    assert "trimImageToContent" in powerpoint
    assert "allocateEquationNumber" not in powerpoint
    assert "PowerPoint numbered images require a manual number." in powerpoint
    assert "setSelectedText" not in powerpoint
    assert '"dev:powerpoint"' in package
    assert (ADDIN / "scripts" / "start_office_dev.ps1").is_file()
    assert not (ADDIN / "scripts" / "start_word_dev.ps1").exists()
    assert not (ADDIN / "scripts" / "register_word_catalog.ps1").exists()
    assert not (ADDIN / "src" / "dialog" / "previewRender.ts").exists()


def test_office_addin_release_packaging_uses_installed_https_runtime() -> None:
    windows_build = (ROOT / "scripts" / "build_office_addin_installer.ps1").read_text(encoding="utf-8")
    windows_install = (ADDIN / "installer" / "windows" / "install.ps1").read_text(encoding="utf-8")
    macos_build = (ROOT / "scripts" / "build_office_addin_macos.sh").read_text(encoding="utf-8")
    macos_install = (ADDIN / "installer" / "macos" / "postinstall").read_text(encoding="utf-8")
    bridge = (ROOT / "src" / "integration" / "office" / "bridge_server.py").read_text(encoding="utf-8")
    controller = (ROOT / "src" / "ui" / "office_bridge_controller.py").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "https://localhost:8765" in windows_build
    assert "https://localhost:8765" in macos_build
    assert "New-SelfSignedCertificate" in windows_install
    assert "16.0\\WEF" in windows_install
    assert '"Developer"' in windows_install
    assert '"TrustedCatalogs"' in windows_install
    assert "New-SmbShare" not in windows_install
    assert "security add-trusted-cert" in macos_install
    assert "com.microsoft.Word" in macos_install
    assert "com.microsoft.Powerpoint" in macos_install
    assert "wef" in macos_install
    assert "OfficeDeploymentManifests-" in windows_build
    assert "site_root" in bridge
    assert "find_installed_office_addin" in controller
    assert "OfficeAddinSetup-" in release
    assert "OfficeAddin-" in release
    assert "OfficeDeploymentManifests-" in release

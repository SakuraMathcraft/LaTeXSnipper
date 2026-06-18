# coding: utf-8

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "office_plugin"


def read_word_adapter_sources() -> str:
    host_root = PLUGIN / "hosts" / "WordAddIn"
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(host_root.glob("DynamicWordApplicationAdapter*.cs"))
    )


def test_office_plugin_foundation_is_modular() -> None:
    assert (PLUGIN / "LaTeXSnipper.OfficePlugin.slnx").is_file()
    assert (PLUGIN / "Directory.Build.props").is_file()
    assert (PLUGIN / "NuGet.config").is_file()
    assert (PLUGIN / "README.md").is_file()

    projects = {
        "LaTeXSnipper.OfficePlugin.Abstractions": ("FormulaMetadata.cs", "OfficeCommandTimeouts.cs"),
        "LaTeXSnipper.OfficePlugin.Bridge": ("BridgeClient.cs", "BridgeOptions.cs", "BridgeConfiguration.cs"),
        "LaTeXSnipper.OfficePlugin.Rendering": ("OlePresentationPipeline.cs", "OlePresentationRendererNotRegisteredException.cs"),
        "LaTeXSnipper.OfficePlugin.Editor": ("FormulaEditorSession.cs",),
    }

    for project, expected_files in projects.items():
        project_root = PLUGIN / "src" / project
        project_file = project_root / f"{project}.csproj"
        project_text = project_file.read_text(encoding="utf-8")
        assert project_file.is_file()
        assert "<TargetFrameworks>net48;net9.0</TargetFrameworks>" in project_text
        if project in {"LaTeXSnipper.OfficePlugin.Rendering", "LaTeXSnipper.OfficePlugin.Editor"}:
            assert 'PackageReference Include="Microsoft.Web.WebView2"' in project_text
        else:
            assert "<PackageReference" not in project_text
        for filename in expected_files:
            assert (project_root / filename).is_file()


def test_office_editor_uses_shared_mathfield_input_policy() -> None:
    shared_input = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "mathfield-input.js"
    ).read_text(encoding="utf-8")

    assert 'const VISIBLE_MATH_SPACE = "\\\\,";' in shared_input
    assert '"addRowAfter"' in shared_input
    assert "\\\\begin{aligned}#@\\\\\\\\#?\\\\end{aligned}" in shared_input
    assert 'mathfield.mode === "latex"' in shared_input
    assert "luminance > 0.72" in shared_input
    assert 'mathfield.style.backgroundColor' in shared_input
    assert "event.shiftKey" in shared_input
    assert "onAccept();" in shared_input
    for shortcut in ("f:", "r:", "h:", "l:", "j:"):
        assert shortcut in shared_input
    for menu_id in (
        "add-row-before",
        "add-row-after",
        "add-column-before",
        "add-column-after",
        "delete-row",
        "delete-column",
    ):
        assert f'"{menu_id}"' in shared_input
    assert 'document.addEventListener("menu-select"' in shared_input
    assert "event.preventDefault();" in shared_input
    assert 'mathfield.executeCommand("selectAll")' in shared_input
    assert "mathfield.selection = selection" in shared_input

    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        editor_html = (assets / "editor.html").read_text(encoding="utf-8")
        editor_js = (assets / "editor.js").read_text(encoding="utf-8")

        assert "mathfield-input.js" in editor_html
        assert "LaTeXSnipperMathfieldInput.configure(mathfield, accept)" in editor_js
        assert "LaTeXSnipperMathfieldInput.setDefaultFontStyle" in editor_js
        assert "scheduleSourceSync" in editor_js
        assert "requestIdleCallback(syncSourceNow" in editor_js
        assert "cancelIdleCallback(sourceSyncHandle)" in editor_js
        assert "removeDefaultFontWrapper" in editor_js
        assert 'Bold: ["\\\\mathbf", "\\\\boldsymbol", "\\\\bm"]' in editor_js
        assert "mathfield.onScrollIntoView = scheduleCaretVisibility" in editor_js
        assert 'querySelector(".ML__caret, .ML__latex-caret")' in editor_js
        assert (
            'event.key === "Enter" && event.shiftKey'
            in editor_js
        )
        assert (
            'event.key === "Enter" && !event.isComposing'
            not in editor_js
        )


def test_office_editor_matrix_templates_are_shared_and_ordered() -> None:
    shared_assets = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
    )
    matrix_templates = (shared_assets / "matrix-templates.js").read_text(encoding="utf-8")
    symbol_library = (shared_assets / "symbol-library.js").read_text(encoding="utf-8")

    for template_name in ("jacobian", "hessian", "identity", "diagonal", "augmented"):
        assert f'environment === "{template_name}"' in matrix_templates
    assert "rows,\n        cols," in matrix_templates

    for latex in (
        "\\\\overset{#?}{#@}",
        "\\\\underset{#?}{#@}",
        "\\\\vec{#@}",
    ):
        assert symbol_library.count(latex) == 1

    for latex in (
        "\\\\overset{\\\\scriptscriptstyle -}{#@}",
        "\\\\overset{\\\\wedge}{#@}",
        "\\\\overset{\\\\sim}{#@}",
        "\\\\overset{\\\\cdot}{#@}",
        "\\\\overset{\\\\scriptscriptstyle \\\\bullet\\\\!\\\\bullet}{#@}",
        "\\\\overset{\\\\vee}{#@}",
    ):
        assert symbol_library.count(latex) == 1

    for latex in (
        "\\\\bar{#@}",
        "\\\\hat{#@}",
        "\\\\tilde{#@}",
        "\\\\dot{#@}",
        "\\\\ddot{#@}",
        "\\\\check{#@}",
    ):
        assert latex not in symbol_library

    ordered_entries = (
        "matrix:bmatrix",
        "matrix:pmatrix",
        "matrix:Bmatrix",
        "matrix:jacobian",
        "matrix:hessian",
        "matrix:identity",
        "matrix:diagonal",
        "matrix:augmented",
        "matrix:vmatrix",
    )
    positions = [symbol_library.index(entry) for entry in ordered_entries]
    assert positions == sorted(positions)

    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        editor_html = (assets / "editor.html").read_text(encoding="utf-8")
        editor_js = (assets / "editor.js").read_text(encoding="utf-8")

        assert "matrix-templates.js" in editor_html
        assert "LaTeXSnipperMatrixTemplates.insert(mathfield, env, rows, cols)" in editor_js
        assert "LaTeXSnipperMathfieldInput.insertTemplate(mathfield, latex)" in editor_js
        assert 'button.addEventListener("pointerdown", event => event.preventDefault())' in editor_js
        assert '["identity", "diagonal"].includes(env)' in editor_js
        assert '" square"' in editor_js
        editor_css = (assets / "editor.css").read_text(encoding="utf-8")
        assert ".matrix-row.square" in editor_css


def test_office_editor_symbol_group_counts_and_shortcuts() -> None:
    symbol_library = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "symbol-library.js"
    ).read_text(encoding="utf-8")

    assert '["{x∈A|P}", "\\\\left\\\\{#?\\\\in#?\\\\mid#?\\\\right\\\\}"' in symbol_library
    assert '["A×B", "#?\\\\times#?"' in symbol_library
    assert '["⟷", "\\\\longleftrightarrow"]' in symbol_library
    assert '["→ᵃ", "\\\\xrightarrow{#?}"' in symbol_library
    expected_counts = {
        "greek": 52,
        "structures": 43,
        "delimiters": 36,
        "relations": 112,
        "operators": 64,
        "bigops": 20,
        "arrows": 68,
        "sets": 40,
        "misc": 56,
    }
    for group_id, expected_count in expected_counts.items():
        group = symbol_library.split(f'id: "{group_id}"', 1)[1].split("\n  {", 1)[0]
        assert group.count('["') == expected_count

    assert '"\\\\omicron"' in symbol_library
    assert '"\\\\Upsilon"' in symbol_library
    assert '"\\\\varTheta"' in symbol_library
    assert '"\\\\varDelta"' in symbol_library
    greek_group = symbol_library.split('id: "greek"', 1)[1].split("\n  {", 1)[0]
    assert '["Ϝ", "Ϝ"]' in greek_group
    for latex in (
        "\\\\Sampi",
        "\\\\sampi",
        "\\\\backepsilon",
        "\\\\varGamma",
        "\\\\varLambda",
        "\\\\varPi",
    ):
        assert f'"{latex}"' in greek_group
    for latex in (
        "\\\\partial",
        "\\\\nabla",
        "\\\\infty",
        "\\\\aleph",
        "\\\\beth",
        "\\\\gimel",
        "\\\\daleth",
    ):
        assert f'"{latex}"' not in greek_group

    operators_group = symbol_library.split('id: "operators"', 1)[1].split("\n  {", 1)[0]
    assert operators_group.count('"\\\\dotplus"') == 1
    for latex in ("\\\\partial", "\\\\nabla", "\\\\intercal"):
        assert f'"{latex}"' in operators_group
    for latex in ("\\\\smallsmile", "\\\\smallfrown"):
        assert f'"{latex}"' not in operators_group

    relations_group = symbol_library.split('id: "relations"', 1)[1].split("\n  {", 1)[0]
    for latex in (
        "\\\\mid",
        "\\\\nmid",
        "\\\\smallsmile",
        "\\\\smallfrown",
        "\\\\lneqq",
        "\\\\gneqq",
    ):
        assert relations_group.count(f'"{latex}"') == 1

    bigops_group = symbol_library.split('id: "bigops"', 1)[1].split("\n  {", 1)[0]
    for latex in ("\\\\sum", "\\\\prod", "\\\\int", "\\\\smallint", "\\\\bigcup"):
        assert f'"{latex}"' in bigops_group
    for latex in ("\\\\sumint", "\\\\bigtimes", "\\\\amalg", "\\\\intsl", "\\\\intBar"):
        assert f'"{latex}"' not in bigops_group

    misc_group = symbol_library.split('id: "misc"', 1)[1].split("\n  {", 1)[0]
    for latex in (
        "\\\\spadesuit",
        "\\\\heartsuit",
        "\\\\clubsuit",
        "\\\\diamondsuit",
        "\\\\copyright",
        "\\\\yen",
        "\\\\Finv",
        "\\\\Game",
        "\\\\diagup",
        "\\\\blacktriangledown",
    ):
        assert f'"{latex}"' in misc_group
    for latex in ("\\\\times", "\\\\dag", "\\\\ddag", "\\\\triangle"):
        assert f'"{latex}"' not in misc_group

    chemistry_group = symbol_library.split('id: "chemistry"', 1)[1].split("\n  {", 1)[0]
    assert "\\\\ce{ #?" not in chemistry_group
    assert "\\\\ce{#?" not in chemistry_group
    for latex in (
        "\\\\mathrm{#?}",
        "\\\\mathrm{#?}\\\\rightarrow\\\\mathrm{#?}",
        "\\\\mathrm{#?}\\\\rightleftharpoons\\\\mathrm{#?}",
        "\\\\mathrm{#?}\\\\xrightarrow[#?]{#?}\\\\mathrm{#?}",
        "{}^{#?}_{#?}\\\\mathrm{#?}",
    ):
        assert f'"{latex}"' in chemistry_group

    assert '"\\\\overleftrightarrow{#@}"' in symbol_library
    assert '"\\\\enclose{horizontalstrike}{#@}"' in symbol_library
    assert '"\\\\sout{#?}"' not in symbol_library
    assert '"\\\\textwarning"' not in symbol_library
    assert '"\\\\textcelsius"' not in symbol_library
    assert '"\\\\textfahrenheit"' not in symbol_library
    assert '"\\\\diameter"' not in symbol_library
    for latex in ("\\\\mho", "\\\\Bbbk", "\\\\circledS", "\\\\maltese", "\\\\backprime"):
        assert f'"{latex}"' in symbol_library

    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        settings_html = (assets / "settings.html").read_text(encoding="utf-8")
        settings_js = (assets / "settings.js").read_text(encoding="utf-8")

        assert "<kbd>Shift</kbd>" in settings_html
        for key in ("F", "R", "H", "L", "J"):
            assert f"<kbd>{key}</kbd>" in settings_html
        assert "新建数学行" in settings_js
        assert "start a new math row" in settings_js
        assert "在公式编辑器中换行" not in settings_js
        assert "insert a line break in the formula editor" not in settings_js


def test_word_addin_host_has_first_workflow_surface() -> None:
    slnx = (PLUGIN / "LaTeXSnipper.OfficePlugin.slnx").read_text(encoding="utf-8")
    host_root = PLUGIN / "hosts" / "WordAddIn"
    project_file = host_root / "LaTeXSnipper.OfficePlugin.WordAddIn.csproj"
    project_text = project_file.read_text(encoding="utf-8")

    assert "hosts/WordAddIn/LaTeXSnipper.OfficePlugin.WordAddIn.csproj" in slnx
    assert project_file.is_file()
    assert "<TargetFramework>net48</TargetFramework>" in project_text
    assert 'PackageReference Include="Microsoft.Web.WebView2"' in project_text
    assert (host_root / "Ribbon" / "WordRibbon.xml").is_file()
    assert (host_root / "WordRibbonCallbacks.cs").is_file()
    assert (host_root / "WordRibbonXml.cs").is_file()
    assert (host_root / "WordPluginController.cs").is_file()
    assert (host_root / "WordOmmlDocumentBuilder.cs").is_file()
    assert not (host_root / "BridgeConversionParser.cs").exists()
    assert not (host_root / "BridgeConversionResult.cs").exists()
    assert (host_root / "BridgeRecognitionParser.cs").is_file()
    assert (host_root / "WordFormulaMetadataStore.cs").is_file()
    assert (host_root / "WordAddInText.cs").is_file()
    assert (host_root / "IWordStatusSink.cs").is_file()
    assert (host_root / "IWordFormulaOptionsProvider.cs").is_file()
    assert (host_root / "WordFormulaOptions.cs").is_file()
    assert (host_root / "VisibleWordStatusSink.cs").is_file()
    assert (host_root / "WordStatusTaskPaneControl.cs").is_file()
    assert (host_root / "OfficePluginHelp.cs").is_file()
    assert (host_root / "WordPluginIcon.cs").is_file()
    assert (host_root / "WordNumberPlacement.cs").is_file()
    assert (host_root / "WordPluginSettings.cs").is_file()
    assert (host_root / "WordSettingsWindow.cs").is_file()
    assert (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditor.cs").is_file()
    assert (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditorForm.cs").is_file()
    assert (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Abstractions" / "FormulaEditorAcceptedEventArgs.cs").is_file()
    assert (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Abstractions" / "FormulaEditorSubmissionResult.cs").is_file()
    assert (host_root / "EditorAssets" / "editor.html").is_file()
    assert (host_root / "EditorAssets" / "taskpane.html").is_file()
    assert (host_root / "EditorAssets" / "taskpane.css").is_file()
    assert (host_root / "EditorAssets" / "taskpane.js").is_file()
    assert (host_root / "EditorAssets" / "help.html").is_file()
    factory = (host_root / "WordAddInFactory.cs").read_text(encoding="utf-8")
    bridge_client = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Bridge" / "BridgeClient.cs").read_text(encoding="utf-8")
    editor = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditor.cs").read_text(encoding="utf-8")
    editor_form = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditorForm.cs").read_text(encoding="utf-8")
    assert "http://127.0.0.1:28765/" in factory
    assert "LATEXSNIPPER_OFFICE_BRIDGE_TOKEN" in factory
    assert "FormulaSubmitting" in factory
    assert "FormulaAccepted" not in factory
    assert "TryAcceptEditorFormulaAsync" in factory
    assert "ConfigAsync" in bridge_client
    assert "EnsureConfiguredAsync" in bridge_client
    assert "https://localhost:8765/" not in factory
    assert "CaptureInputLanguage()" in editor
    assert "InputLanguage.CurrentInputLanguage" in editor_form
    assert "WmInputLangChangeRequest" in editor_form
    assert "ImmGetConversionStatus" in editor_form
    assert "ImmSetConversionStatus" in editor_form
    assert "RestoreInputLanguage()" in editor_form
    assert "RestoreInputLanguageWhenOwnerIsForegroundAsync" in editor_form
    assert "GetForegroundWindow() == snapshot.ForegroundWindow" in editor_form

    ribbon = (host_root / "Ribbon" / "WordRibbon.xml").read_text(encoding="utf-8")
    assert "LaTeXSnipperTab" in ribbon
    assert "OnOpenEditor" not in ribbon
    assert "OpenEditorButton" not in ribbon
    assert "OnInsertOmml" not in ribbon
    assert "OnInsertInline" in ribbon
    assert "OnInsertDisplay" in ribbon
    assert "OnInsertNumbered" in ribbon
    assert "OnScreenshotOcr" in ribbon
    assert "OnLoadSelected" in ribbon
    assert "OnDeleteSelected" in ribbon
    assert "OnAutoNumberSelected" in ribbon
    assert "OnRenumberAll" in ribbon
    assert "OnShowTaskPane" in ribbon
    assert "OnSettings" in ribbon
    assert "OnHelp" in ribbon
    assert "LaTeXSnipperFormulaGroup" in ribbon
    assert "LaTeXSnipperEditGroup" in ribbon
    assert "LaTeXSnipperNumberingGroup" in ribbon
    assert "LaTeXSnipperToolsGroup" in ribbon
    assert "label=\"{RibbonTab}\"" in ribbon
    assert "getLabel=\"GetLabel\"" not in ribbon
    assert "getSupertip=\"GetSupertip\"" not in ribbon
    assert "UpdateSelectedButton" not in ribbon
    assert ribbon.count('size="large"') >= 9
    assert "TaskPaneInsert" not in ribbon
    assert "ReviewingPane" in ribbon
    assert "SettingsButton" in ribbon
    assert 'keytip="LS"' in ribbon
    assert 'keytip="I"' in ribbon
    assert 'keytip="D"' in ribbon
    assert 'keytip="N"' in ribbon
    assert 'keytip="S"' in ribbon
    assert "EquationProfessional" in ribbon
    assert "EquationInsertGallery" in ribbon
    assert "Numbering" in ribbon
    assert "AdvancedFileProperties" in ribbon
    assert 'getImage="GetImage"' not in ribbon

    metadata_store = (host_root / "WordFormulaMetadataStore.cs").read_text(encoding="utf-8")
    adapter = read_word_adapter_sources()
    callbacks = (host_root / "WordRibbonCallbacks.cs").read_text(encoding="utf-8")
    addin_text = (host_root / "WordAddInText.cs").read_text(encoding="utf-8")
    taskpane = (host_root / "WordStatusTaskPaneControl.cs").read_text(encoding="utf-8")
    taskpane_html = (host_root / "EditorAssets" / "taskpane.html").read_text(encoding="utf-8")
    taskpane_js = (host_root / "EditorAssets" / "taskpane.js").read_text(encoding="utf-8")
    controller = (host_root / "WordPluginController.cs").read_text(encoding="utf-8")
    icon = (host_root / "WordPluginIcon.cs").read_text(encoding="utf-8")
    project_text = project_file.read_text(encoding="utf-8")
    assert "latexsnipper-eq-" in metadata_store
    assert "latexsnipper-eqn-" in metadata_store
    assert "latexsnipper-eqm-" not in metadata_store
    assert "MetadataVariablePrefix" in metadata_store
    assert "BuildMetadataStorageKey" in metadata_store
    assert 'Guid.NewGuid().ToString("N").Substring(0, 10)' in metadata_store
    assert "TryLoadEmbedded" not in metadata_store
    assert "LoadSelectedFormulaAsync" in adapter
    assert "UpdateFormulaAsync" in adapter
    assert "DeleteSelectedFormulaAsync" in adapter
    assert "RenumberAutomaticFormulasAsync" in adapter
    assert "ReplaceNumberControlText" in adapter
    assert "FindSelectedFormulas" in adapter
    assert "AddSelectedFormulasOverlappingRange" not in adapter
    assert "RangesOverlap" in adapter
    assert "DeleteFormula" in adapter
    assert "CountAutoNumberedFormulasAsync" not in adapter
    assert "LoadAllManagedFormulasAsync" not in adapter
    assert "MoveSelectionAfterInlineControl" in adapter
    assert "MoveSelectionAfterDisplayParagraph" in adapter
    assert "MoveSelectionAfterTable" not in adapter
    assert "MoveSelectionAfterContentControl" in adapter
    assert "TryMoveSelectionOutsideFormula" in adapter
    assert "RangeTouchesManagedFormula" in adapter
    assert "CollapsedRangeIntersectsManagedFormula" in adapter
    assert "if (IsCollapsedRange(range))" in adapter
    assert "Selection.SetRange" in adapter
    assert "ExecuteWithScreenUpdatingSuspended" in adapter
    assert "BeginUndoRecord" in adapter
    assert "UndoRecordScope" in adapter
    assert "_undoRecordDepth" in adapter
    assert "ResolveInsertionTargetRange" in adapter
    assert "ResolveInsertionTargetRange(selection, display)" in adapter
    assert "ResolveManagedEquationInsertionRange" in adapter
    assert "return insertionPoint.Paragraphs.Item(1).Range;" in adapter
    assert "dynamic range = ResolveManagedEquationInsertionRange(selection, display);" in adapter
    assert "ParagraphHasContent" in adapter
    assert "TryMoveSelectionToFollowingParagraph" in adapter
    assert "TryResolveAfterEmptyParagraphFollowingNumberedTable" not in adapter
    assert "TryGetNumberedTableFromPreviousParagraph" not in adapter
    assert "TryGetNumberedTableBeforeParagraph" not in adapter
    assert "CreateInsertionRangeAfterNumberedTable" not in adapter
    assert "IsInsideManagedContent" not in adapter
    assert "TypeParagraph" not in adapter
    assert "CreateRangeAfterTable" not in adapter
    assert "CreateRecoveredFormulaMetadata" not in adapter
    assert "WordFormulaMetadataStore.Load(" in adapter
    assert "TryLoadFormulaTagMetadata" not in adapter
    assert "WordFormulaMetadataStore.Delete" not in adapter
    assert "RestoreManagedEquationControlIdentity" in adapter
    assert "FormulaMetadata stored = WordFormulaMetadataStore.Load(" in adapter
    assert "LoadFormulaFromNumberControl" in adapter
    assert "RenderEngineKind.MathJaxSvg" in adapter.split("private SelectedWordFormula LoadFormulaFromNumberControl", 1)[1]
    assert "GetContainingParagraphRange(control)" in adapter
    assert "NormalizeNumberedTable" not in adapter
    assert "ApplyNumberedParagraphLayout" in adapter
    assert "TabStops.Add" in adapter
    assert "ClearParagraphContent(paragraphRange)" in adapter
    assert "metadata.NumberingMode != currentMetadata.NumberingMode ||" in adapter
    assert "metadata.NumberingMode != NumberingMode.None" in adapter.split(
        "private void ReplaceFormulaContent",
        1,
    )[1].split("private void ReplaceParagraphWithFormula", 1)[0]
    assert "metadata.DisplayMode != FormulaDisplayMode.Inline" in adapter.split(
        "private void ReplaceFormulaContent",
        1,
    )[1].split("private void ReplaceParagraphWithFormula", 1)[0]
    assert "ReplaceExistingEquationControlContent(control, equationContentOoxml, metadata)" in adapter
    assert "SaveFormulaMetadata(control, metadata)" in adapter
    assert "ReplaceParagraphWithFormula(control, ooxml, metadata)" in adapter
    assert "ReplaceNumberedFormulaControl" not in adapter
    assert "RemoveEmptyParagraphBeforeFollowingContent" in adapter
    assert "paragraphRange.Delete()" not in adapter
    assert "TryGetManagedNumberedFormulaTable" not in adapter
    assert "InsertNumberControlAtRange(CreateDocumentRange(paragraphStart, paragraphStart), metadata)" in adapter
    assert "ApplyNumberControlVerticalAlignment" in adapter
    assert "CalculateNumberVerticalOffset" in adapter
    assert "EstimateFormulaRows" in adapter
    assert "(renderedHeightPoints - WordOleBaseFontPoints) / 2" in adapter
    assert "Math.Min(14" not in adapter
    assert "* 0.18" not in adapter
    assert "ApplyNumberedOleInlineShapeBaseline" in adapter
    assert "DeleteNumberedParagraphBlock" not in adapter
    assert "DeleteNumberedFormulaById" in adapter
    assert "AddAdjacentTabDeletionTargets" in adapter
    assert "TryStartUndoRecord" in adapter
    assert "StartCustomRecord(\"LaTeXSnipper\")" in adapter
    assert "using (_wordAdapter.BeginUndoRecord())" in controller
    assert "GetCurrentFontSizePoints" in adapter
    assert "ApplyManagedEquationFontSizeById" in adapter
    assert "ReadManagedEquationFontSize" in adapter
    assert "control.Range.Font.Size = fontSizePoints" in adapter
    assert "ApplyOleInlineShapeBaseline" in adapter
    assert "inlineShape.Range.Font.Position = -baseline" in adapter
    assert "ResetSelectionFormulaTextFormatting" in adapter
    assert "NormalizePlainTextBaselineAroundRange" in adapter
    assert "NormalizeManagedInlineEquationBaseline" in adapter
    assert "NormalizePlainTextBaselineByFormulaId" not in adapter
    assert "NormalizeManagedInlineEquationBaseline(metadata, insertedControl)" in adapter
    assert "NormalizeManagedInlineEquationBaseline(metadata, FindFormulaControlById(metadata.Identity.EquationId))" in adapter
    assert "LoadManagedFormulaSpans" in adapter
    assert "ResetPlainTextBaseline" in adapter
    assert "_wordApplication.Selection.Font.Position = 0" in adapter
    assert "_wordApplication.Selection.Font.Superscript = 0" in adapter
    assert "_wordApplication.Selection.Font.Subscript = 0" in adapter
    assert "ActivateForEditingAsync" in adapter
    assert "_wordApplication.ActiveWindow.Activate()" in adapter
    assert "_wordApplication.ActiveWindow.SetFocus()" in adapter
    assert "_wordApplication.Selection.Range.Select()" not in adapter
    assert "MoveSelectionAfterDisplayRange" not in adapter
    assert "OnUpdateSelected" not in callbacks
    assert "OnScreenshotOcr" in callbacks
    assert "OnOpenEditor" not in callbacks
    assert "OnInsertInline" in callbacks
    assert "OnInsertDisplay" in callbacks
    assert "OnInsertNumbered" in callbacks
    assert "OnSettings" in callbacks
    assert "CancelScreenshotOcr" in callbacks
    assert "CancelScreenshotOcrAsync" in callbacks
    assert "RunScreenshotOcrAsync" in callbacks
    assert "TryRunCommandAsync" in callbacks
    assert "ct => _controller.RecognizeScreenshotAsync(ct)" not in callbacks
    assert "_runningCommand" not in callbacks
    assert "OcrWaitingStatus" in callbacks
    assert "OcrRecognizingStatus" in addin_text
    assert "OcrCanceledStatus" in callbacks
    assert "MessageBox.Show" not in callbacks
    assert "WordAddInText.Get" in callbacks
    assert "Waiting for screenshot OCR" in addin_text
    assert "Recognizing screenshot formula" in addin_text
    assert "Help opened." in addin_text
    assert "SettingsNumberingGroup" in addin_text
    assert "可从 Ribbon 或此窗格使用" not in addin_text
    assert "ListBox" not in taskpane
    assert "WebView2" in taskpane
    assert "taskpane.html" in taskpane
    assert "statusIcon" not in taskpane_html
    assert 'textContent = "OK"' not in taskpane_js
    assert "DefaultLatex = \"e^{i\\\\pi}+1=0\"" in taskpane
    assert "private bool _displayMode;" in taskpane
    assert "saved?.DisplayMode ?? false" in taskpane
    assert 'id="displayMode" type="checkbox" checked' not in taskpane_html
    assert "display: false" in taskpane_js
    assert "els.displayMode.checked = Boolean(payload.display)" in taskpane_js
    assert "IWordFormulaOptionsProvider" in taskpane
    assert "NumberingMode.Manual" in taskpane
    assert "ConnectRequested" in taskpane
    assert "SetOcrActive" in taskpane
    assert "LoadSelectedRequested" not in taskpane
    assert "DeleteSelectedRequested" not in taskpane
    assert "previewField.readOnly" not in taskpane_js
    assert 'field.addEventListener("input"' in taskpane_js
    assert "resizePreview" in taskpane_js
    assert "ocrActive" in taskpane_js
    assert "cancelOcr" in taskpane_js
    taskpane_css = (host_root / "EditorAssets" / "taskpane.css").read_text(encoding="utf-8")
    assert "overflow-x: auto" in taskpane_css
    assert "width: max-content" in taskpane_css
    assert "min-height: 44px" in taskpane_css
    assert "CreateDefaultLatex" in controller
    assert "CreateEditorDraftFromOptions" in controller
    assert "AutoNumberDisplayOnlyStatus" in controller
    assert "selected.DisplayMode != FormulaDisplayMode.Display" in controller
    assert "CancelScreenshotOcrAsync" in controller
    assert "BridgeRecognitionProgress.RunScreenshotOcrAsync" in controller
    assert "InsertInlineAsync" in controller
    assert "InsertDisplayAsync" in controller
    assert "InsertNumberedAsync" in controller
    assert "OpenEditorForInsertAsync" in controller
    assert "GetOleFontScale" in controller
    assert "GetCurrentFontSizePoints" in controller
    assert "FontScale = 1.2" not in controller
    assert "_pendingEditorInsertOptions" in controller
    assert "ShowSettingsAsync" in controller
    assert "UpdateDraftIfOpenAsync" in controller
    assert "SemaphoreSlim _commandGate" in controller
    assert "TryRunCommandAsync" in controller
    assert "TryAcceptEditorFormulaAsync" in controller
    assert "ActivateForEditingAsync" in controller
    assert "WaitAsync(0" in controller
    assert "OpenEditorAsync" not in controller
    assert "OfficePluginHelp.Open" in controller
    assert "RenumberAutomaticFormulasAsync" in controller
    assert "ResetDraftState" in controller
    assert "ApplyFormulaMetadata(metadata" not in controller
    assert "e^{i\\\\pi}+1=0" in controller
    open_editor_method = controller.split("private async Task OpenEditorForInsertAsync", 1)[1].split("private async Task InsertAndRenumberIfNeededAsync", 1)[0]
    assert "CreateDefaultLatex" not in open_editor_method
    assert "string.Empty" in controller.split("private static FormulaMetadata CreateEditorDraftFromOptions", 1)[1].split("private static FormulaMetadata CreateDefaultFormula", 1)[0]
    omml_builder = (host_root / "WordOmmlDocumentBuilder.cs").read_text(encoding="utf-8")
    assert "BuildFlatOpcDocument(string omml, FormulaMetadata metadata" in omml_builder
    assert "ExtractEquationOmml" in omml_builder
    assert "XElement.Parse" in omml_builder
    assert 'element.Name.LocalName == "oMath"' in omml_builder
    assert "Regex.Match" not in omml_builder
    assert "BuildEquationTag(metadata.Identity.EquationId)" in omml_builder
    assert "BuildEquationTag(equationId, metadata)" not in omml_builder
    assert "inlineMath" not in omml_builder
    assert "w:vanish" not in omml_builder
    assert "WrapNumberContentControl" in omml_builder
    assert "WordNumberPlacement" in omml_builder
    assert "<w:tbl" not in omml_builder
    assert "<w:tabs>" not in omml_builder
    assert "w:pos=\\\"4680\\\"" not in omml_builder
    assert "w:pos=\\\"9360\\\"" not in omml_builder
    assert "paragraphRange.ParagraphFormat.TabStops.Add" in adapter
    assert "<w:r><w:t>" in omml_builder
    assert "</m:t></m:r></m:oMath>" not in omml_builder
    assert "icon.ico" in project_text
    shared_editor_form = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditorForm.cs").read_text(encoding="utf-8")
    shared_editor = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditor.cs").read_text(encoding="utf-8")
    assert "_options.Icon" in shared_editor_form
    assert "FormulaSubmitting" in shared_editor
    assert "FormulaAccepted" not in shared_editor
    assert "RecreateForm()" in shared_editor
    assert "e.Cancel = true" not in shared_editor_form
    assert "\n            Hide();" not in shared_editor_form
    assert "CloseOnCommit" not in shared_editor_form
    assert "CloseOnCommit" not in shared_editor
    assert "form.DisposeForShutdown()" in shared_editor
    assert "SetSubmittingAsync(true)" in shared_editor_form
    assert "SetSubmittingAsync(false)" in shared_editor_form
    assert "TrySetSubmittingAsync(false)" in shared_editor_form
    assert "ExecuteEditorScriptAsync" in shared_editor_form
    assert "if (InvokeRequired)" in shared_editor_form
    assert "FormulaEditorSubmissionResult" in shared_editor_form
    assert "WordPluginIcon.Load" in factory
    assert "WordPluginIcon.Load" in (host_root / "OfficePluginHelp.cs").read_text(encoding="utf-8")
    settings_window = (host_root / "WordSettingsWindow.cs").read_text(encoding="utf-8")
    assert "WebView2" in settings_window
    assert "settings.html" in settings_window
    assert "ShowDialog" not in settings_window
    assert "src\", \"assets\", \"icon.ico" not in icon
    assert "InstalledAssetResolver.FindInstallDirectory()" in icon
    assert "AppDomain.CurrentDomain.BaseDirectory" not in icon
    assert "WinFormsFormulaEditor" not in factory
    assert "ShowDialog" not in (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditor.cs").read_text(encoding="utf-8")
    assert "MinimizeBox = false" not in shared_editor_form
    editor_html = (host_root / "EditorAssets" / "editor.html").read_text(encoding="utf-8")
    editor_js = (host_root / "EditorAssets" / "editor.js").read_text(encoding="utf-8")
    editor_css = (host_root / "EditorAssets" / "editor.css").read_text(encoding="utf-8")
    assert "displayMode" not in editor_html
    assert "display: true" in editor_js
    assert "let submitting = false" in editor_js
    assert "function setSubmitting" in editor_js
    assert "setSubmitting(false);" in editor_js
    assert "acceptButton.disabled = submitting" in editor_js
    assert "cancelButton.disabled = submitting" in editor_js
    assert "if (submitting)" in editor_js
    assert "setStatus," in editor_js
    assert "setSubmitting," in editor_js
    assert 'event.key === "Enter"' in editor_js
    assert "!event.ctrlKey" in editor_js
    assert 'event.key === "Escape"' in editor_js
    assert "mathfield.defaultMode" not in editor_js
    assert "mathfield.smartMode = false" not in editor_js
    assert "mathVirtualKeyboard?.hide()" in editor_js
    apply_init_block = editor_js.split("function applyInit", 1)[1].split("async function bootstrap", 1)[0]
    assert "mathfield?.focus()" not in apply_init_block
    bootstrap_tail = editor_js.split("if (pendingInit || window.__latexSnipperPendingInit)", 1)[1].split("}", 1)[0]
    assert "mathfield.focus()" not in bootstrap_tail
    latex_source_handler = editor_js.split('latexSource.addEventListener("input"', 1)[1].split('cancelButton.addEventListener("click"', 1)[0]
    assert "mathfield.focus()" not in latex_source_handler
    hide_keyboard = editor_js.split("function hideVirtualKeyboard()", 1)[1].split("function configureText()", 1)[0]
    assert "mathfield.focus()" not in hide_keyboard
    escape_block = editor_js.split('if (event.key === "Escape") {', 1)[1].split('if (event.key === "Enter"', 1)[0]
    assert "hideVirtualKeyboard();" in escape_block
    assert 'send({ type: "cancel" })' not in escape_block
    assert "symbol-grid" in editor_html
    assert "flex-direction: column" in editor_css
    assert "border: 1px solid transparent" in editor_css
    shared_symbol_library = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "EditorAssets" / "symbol-library.js").read_text(encoding="utf-8")
    assert "window.LaTeXSnipperEditorSymbols" in editor_js
    assert "window.LaTeXSnipperEditorSymbols" in shared_symbol_library
    assert "analysis:" in shared_symbol_library
    assert "algebra:" in shared_symbol_library
    assert "numberTheory:" in shared_symbol_library
    assert 'id: "numberTheory"' in shared_symbol_library
    assert "accents:" not in editor_js
    assert 'id: "accents"' not in shared_symbol_library
    assert "latexSnipperEditorLibraryState" in editor_js
    assert "function loadLibraryState" in editor_js
    assert "function saveLibraryState" in editor_js
    assert "function restoreGridScroll" in editor_js
    assert "preserveScroll" in editor_js
    assert "preserveGlobalSearch" in editor_js
    assert "selectGroup(GROUPS[0])" not in editor_js
    assert '["\\\\bigl( \\\\bigr)"' not in shared_symbol_library
    assert '"( ) 大"' not in shared_symbol_library
    assert '"[ ] 大"' not in shared_symbol_library
    assert '"|ₓ"' in shared_symbol_library
    assert '"\\\\underbrace{#@}_{#?}"' in shared_symbol_library
    assert '"⎛ ⎞"' in shared_symbol_library
    assert '"⟪ ⟫"' in shared_symbol_library
    assert '"≞"' in shared_symbol_library
    assert '"≝"' in shared_symbol_library
    assert '"≟"' in shared_symbol_library
    assert '["\\\\overset{!}{=}"' not in shared_symbol_library
    assert '["\\\\overset{\\\\text{def}}{=}"' not in shared_symbol_library
    assert '["\\\\overset{?}{=}"' not in shared_symbol_library
    assert '"𝒫(A)"' in shared_symbol_library
    assert '"𝟙_A"' in shared_symbol_library
    assert '"△"' in shared_symbol_library
    assert '"幂集"' not in shared_symbol_library
    assert '"指示函数"' not in shared_symbol_library
    assert '"对称差"' not in shared_symbol_library
    assert '"section": "数学分析 / 实分析 - 概念 / 性质"' in shared_symbol_library
    assert '"section": "PDE / 变分法 / 微局部 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "群论 / 伽罗瓦理论 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "曲线曲面 / 黎曼几何 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "微分拓扑 / Morse 理论 / 流形拓扑 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "初等数论 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "解析数论 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "代数数论 / 算术几何 - 定理 / 公式"' in shared_symbol_library
    assert '"section": "模形式 / 表示 - 定理 / 公式"' in shared_symbol_library
    assert "function isSectionItem(item)" in editor_js
    assert 'className = "symbol-section-label"' in editor_js
    assert "if (isSectionItem(item)) return false;" in editor_js
    assert "Stone-Weierstrass" in shared_symbol_library
    assert "Mikhlin 乘子" in shared_symbol_library
    assert "De Giorgi-Nash-Moser" in shared_symbol_library
    assert "Runge 定理" in shared_symbol_library
    assert "T(1) 定理" in shared_symbol_library
    assert "Harnack 不等式" in shared_symbol_library
    assert "微分中值定理" in shared_symbol_library
    assert "第一积分中值" in shared_symbol_library
    assert "Newton-Leibniz" in shared_symbol_library
    assert "Galois 基本定理" in shared_symbol_library
    assert "Peter-Weyl" in shared_symbol_library
    assert "Auslander-Buchsbaum" in shared_symbol_library
    assert "Grothendieck-Riemann-Roch" in shared_symbol_library
    assert "线性无关" in shared_symbol_library
    assert "基扩张定理" in shared_symbol_library
    assert "Gauss-Bonnet-Chern" in shared_symbol_library
    assert "Toponogov 比较" in shared_symbol_library
    assert "Uhlenbeck 紧性" in shared_symbol_library
    assert "点到直线距离" in shared_symbol_library
    assert "曲面参数化" in shared_symbol_library
    assert "Poincaré-Hopf" in shared_symbol_library
    assert "庞加莱-霍普夫指标" in shared_symbol_library
    assert "Atiyah-Hirzebruch 谱序列" in shared_symbol_library
    assert "Adams-Novikov" in shared_symbol_library
    assert "Kirby 演算" in shared_symbol_library
    assert "Baum-Connes" in shared_symbol_library
    assert "子空间拓扑" in shared_symbol_library
    assert "路径提升" in shared_symbol_library
    assert "二次互反律" in shared_symbol_library
    assert "素数定理" in shared_symbol_library
    assert "类数公式" in shared_symbol_library
    assert "模性定理" in shared_symbol_library
    assert "Langlands 对应" in shared_symbol_library
    assert "probability" in shared_symbol_library
    assert '"section": "经典力学 / 分析力学"' in shared_symbol_library
    assert '"section": "连续介质 / 流体 / 声学"' in shared_symbol_library
    assert '"section": "电路 / 电磁学"' in shared_symbol_library
    assert '"section": "光学 / 波动"' in shared_symbol_library
    assert '"section": "热学 / 热力学 / 统计物理"' in shared_symbol_library
    assert '"section": "量子力学 / 原子物理"' in shared_symbol_library
    assert '"section": "狭义相对论 / 广义相对论 / 宇宙学"' in shared_symbol_library
    assert '"section": "量子场论 / 粒子物理 / 规范理论"' in shared_symbol_library
    assert '"section": "凝聚态 / 固体物理 / 材料"' in shared_symbol_library
    assert '"section": "核物理 / 等离子体 / 天体物理"' in shared_symbol_library
    assert '"section": "弦论 / 量子引力"' in shared_symbol_library
    assert "Navier-Stokes" in shared_symbol_library
    assert "Einstein 方程" in shared_symbol_library
    assert "Yang-Mills" in shared_symbol_library
    assert "AdS/CFT" in shared_symbol_library
    assert '"section": "初等函数"' in shared_symbol_library
    assert '"section": "Gamma / Beta / Zeta / 数论函数"' in shared_symbol_library
    assert '"section": "Bessel / Airy / 正交多项式"' in shared_symbol_library
    assert '"section": "超几何 / q-函数 / 模函数"' in shared_symbol_library
    assert '"section": "阶跃 / 分布 / 病态函数"' in shared_symbol_library
    assert '"Γ"' in shared_symbol_library
    assert '"ζ"' in shared_symbol_library
    assert '"Jν"' in shared_symbol_library
    assert '"Ai"' in shared_symbol_library
    assert '"₂F₁"' in shared_symbol_library
    assert '"j(τ)"' in shared_symbol_library
    assert '"W(x)"' in shared_symbol_library
    assert '"R(x)"' in shared_symbol_library
    assert '"D(x)"' in shared_symbol_library
    assert '"C(x)"' in shared_symbol_library
    assert '"多对数"' not in shared_symbol_library
    assert '"Euler φ"' not in shared_symbol_library
    functions_block = shared_symbol_library.split('id: "functions"', 1)[1].split("],\n  },", 1)[0]
    assert "\\\\Gamma(z)=\\\\int_0^\\\\infty" in shared_symbol_library
    assert "B(x,y)=\\\\int_0^1" in shared_symbol_library
    assert "\\\\zeta(s)=\\\\sum_{n=1}^\\\\infty" in shared_symbol_library
    assert "{}_2F_1(a,b;c;z)=\\\\sum" in shared_symbol_library
    assert "\\\\wp(z;\\\\Lambda)=" in shared_symbol_library
    assert "W(x)=\\\\sum_{n=0}^{\\\\infty}" in shared_symbol_library
    assert "D(x)=\\\\begin{cases}1,&x\\\\in\\\\mathbb Q" in shared_symbol_library
    assert "\\Gamma(#?)" not in functions_block
    assert "B(#?,#?)" not in functions_block
    assert "{}_2F_1(#?,#?;#?;#?)" not in functions_block
    assert "W(#?)" not in functions_block
    assert shared_symbol_library.count("matrix:vmatrix") == 1
    assert editor_css.count(".symbol-section-label") == 2

    expected_math_sections = {
        "analysis": ("调和分析 / Fourier 分析", "PDE / 变分法 / 微局部", "泛函分析 / 算子理论"),
        "algebra": ("同调代数 / 范畴论", "表示论 / 李理论", "代数几何 / 非交换代数"),
        "geometry": ("微分流形 / 张量几何", "辛几何 / 接触几何 / Poisson", "几何分析 / 全局分析 / 规范理论"),
        "topology": ("同伦论 / 谱序列 / 稳定同伦", "纤维丛 / 示性类 / K 理论", "低维拓扑 / 纽结 / 几何拓扑"),
        "numberTheory": ("初等数论", "解析数论", "代数数论 / 算术几何", "模形式 / 表示"),
    }
    minimum_section_counts = {
        "analysis": 12,
        "algebra": 12,
        "geometry": 12,
        "topology": 12,
        "numberTheory": 8,
    }
    for group_id, expected_sections in expected_math_sections.items():
        group_block = shared_symbol_library.split(f'id: "{group_id}"', 1)[1].split("],\n  },", 1)[0]
        for section in expected_sections:
            assert section in group_block
        assert group_block.count('"section": "') >= minimum_section_counts[group_id]

    power_point_root = PLUGIN / "hosts" / "PowerPointAddIn"
    ppt_controller = (power_point_root / "PowerPointPluginController.cs").read_text(encoding="utf-8")
    assert "CreateEditorDraft" in ppt_controller
    insert_formula_method = ppt_controller.split("public async Task InsertFormulaAsync", 1)[1].split("public async Task InsertFormulaFromTaskPaneAsync", 1)[0]
    assert "DefaultLatex" not in insert_formula_method
    assert editor_js == (power_point_root / "EditorAssets" / "editor.js").read_text(encoding="utf-8")
    assert editor_css == (power_point_root / "EditorAssets" / "editor.css").read_text(encoding="utf-8")

    help_html = (host_root / "EditorAssets" / "help.html").read_text(encoding="utf-8")
    assert "LaTeXSnipper Office 插件" in help_html
    assert "LaTeXSnipper Office Plugin" in help_html
    assert "Microsoft 365 Apps" in help_html
    assert "Office 2024 / 2021 / 2019" in help_html
    assert "旧 add-in" not in help_html
    assert "Old add-in" not in help_html
    assert "<img" not in help_html
    settings_html = (host_root / "EditorAssets" / "settings.html").read_text(encoding="utf-8")
    settings_js = (host_root / "EditorAssets" / "settings.js").read_text(encoding="utf-8")
    assert "LaTeXSnipper Office 插件设置" in settings_html
    assert "LaTeXSnipper Office Plugin Settings" in settings_js
    assert "Shift" in settings_html
    for key in ("F", "R", "H", "L", "J"):
        assert f"<kbd>{key}</kbd>" in settings_html
    assert "Enter" in settings_html
    assert "Esc" in settings_html
    assert "<img" not in settings_html
    assert '"{\\"timeout\\":" + ((int)_options.ScreenshotOcrHttpTimeout.TotalSeconds - 30)' in bridge_client
    assert "recognize/screenshot/cancel" in bridge_client
    assert "ScreenshotOcrHttpTimeout" in bridge_client
    assert "Timeout.InfiniteTimeSpan" in bridge_client
    assert "CreateHttpErrorMessage" in bridge_client
    assert "无法连接到 LaTeXSnipper" in bridge_client


def test_word_vsto_shell_is_a_thin_office_loader() -> None:
    shell_root = PLUGIN / "hosts" / "WordVstoAddIn"
    project_file = shell_root / "LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj"
    project_text = project_file.read_text(encoding="utf-8")
    this_addin = (shell_root / "ThisAddIn.cs").read_text(encoding="utf-8")
    ribbon_adapter = (shell_root / "WordRibbonExtensibility.cs").read_text(encoding="utf-8")

    assert project_file.is_file()
    assert "{BAA0C2D2-18E2-41B9-852F-F413020CAA33}" in project_text
    assert "<OfficeApplication>Word</OfficeApplication>" in project_text
    assert "<VSTO_ProjectType>Application</VSTO_ProjectType>" in project_text
    assert "<FriendlyName>LaTeXSnipper</FriendlyName>" in project_text
    assert "Microsoft.VisualStudio.Tools.Office.targets" in project_text
    assert "..\\..\\src\\LaTeXSnipper.OfficePlugin.Abstractions\\LaTeXSnipper.OfficePlugin.Abstractions.csproj" in project_text
    assert "..\\WordAddIn\\LaTeXSnipper.OfficePlugin.WordAddIn.csproj" in project_text
    assert "CreateRibbonExtensibilityObject" in this_addin
    assert "CustomTaskPanes.Add" in this_addin
    assert "taskPane.Width = 480" in this_addin
    assert "ActiveWindowStatusPaneHost" in this_addin
    assert "Dictionary<int, PaneEntry>" in this_addin
    assert "addIn.CustomTaskPanes.Add(control, WordAddInText.Get(\"TaskPaneTitle\"), window)" in this_addin
    assert "VisibleWordStatusSink" in this_addin
    assert "WordAddInFactory.CreateController(Application, visibleStatusSink, statusPaneHost)" in this_addin
    assert "AttachTaskPaneCommands" in this_addin
    assert "IRibbonExtensibility" in ribbon_adapter
    assert "[ComVisible(true)]" in ribbon_adapter
    assert "[Guid(" in ribbon_adapter
    assert "GetImage" not in ribbon_adapter
    assert "OnInsertOmml" in ribbon_adapter
    assert "OnInsertInline" in ribbon_adapter
    assert "OnInsertDisplay" in ribbon_adapter
    assert "OnInsertNumbered" in ribbon_adapter
    assert "OnScreenshotOcr" in ribbon_adapter
    assert "OnAutoNumberSelected" in ribbon_adapter
    assert "OnRenumberAll" in ribbon_adapter
    assert "OnShowTaskPane" in ribbon_adapter
    assert "OnSettings" in ribbon_adapter
    assert "OnHelp" in ribbon_adapter
    assert "GetLabel" not in ribbon_adapter
    assert "GetSupertip" not in ribbon_adapter
    assert "RibbonIconFactory.cs" not in project_text

    build_script = PLUGIN / "tools" / "Build-VstoAddIns.ps1"
    build_text = build_script.read_text(encoding="utf-8")
    assert build_script.is_file()
    assert "VisualStudioForApplicationsBuild" in build_text
    assert "ManifestCertificateThumbprint" in build_text
    assert "Microsoft.VisualStudio.Tools.Office.targets" in build_text
    assert "/p:VSToolsPath=" in build_text
    assert "/p:VisualStudioVersion=" in build_text
    assert "Export-Certificate" in build_text
    assert "1.3.6.1.5.5.7.3.3" in build_text
    assert "-CodeSigningCert" not in build_text
    assert "System32\\WindowsPowerShell\\v1.0\\Modules" in build_text
    assert "Microsoft.PowerShell.Security.psd1" in build_text
    assert "PKI\\PKI.psd1" in build_text
    assert "New-PSDrive -Name Cert -PSProvider Certificate" in build_text
    assert build_text.index('"MSBuild\\Current\\Bin\\MSBuild.exe"') < build_text.index(
        '"MSBuild\\Current\\Bin\\amd64\\MSBuild.exe"'
    )
    assert 'v17.0\\OfficeTools' not in build_text
    assert "RegisterOfficeAddin" not in build_text
    assert "VSTOInstaller.exe" not in build_text
    assert "HKCU:" not in build_text
    assert "HKLM:" not in build_text

    native_build_script = PLUGIN / "tools" / "Build-NativeOleHandler.ps1"
    native_build_text = native_build_script.read_text(encoding="utf-8")
    assert native_build_script.is_file()
    assert 'Where-Object { $_.Name -match "^v\\d+$" }' in native_build_text
    assert 'foreach ($platform in @("x64", "Win32"))' in native_build_text
    assert "/p:PlatformToolset=" in native_build_text
    assert "WindowsUserModeDriver" not in native_build_text

def test_office_plugin_keeps_only_current_module_documentation() -> None:
    assert not (PLUGIN / "hosts" / "OleFormulaObject").exists()
    assert not (PLUGIN / "hosts" / "WordVstoAddIn" / "README.md").exists()
    assert not (PLUGIN / "hosts" / "PowerPointVstoAddIn" / "README.md").exists()
    assert not (PLUGIN / "tools" / "Register-OfficeVstoAddIns.ps1").exists()
    assert not (PLUGIN / "tools" / "Register-WordVstoAddIn.ps1").exists()
    assert not (PLUGIN / "tools" / "Register-PowerPointVstoAddIn.ps1").exists()
    assert not (PLUGIN / "tools" / "OfficeVstoRegistration.ps1").exists()


def test_ole_objects_are_registered_as_static_display_objects() -> None:
    setup_text = (PLUGIN / "installer" / "setup.iss").read_text(encoding="utf-8")
    native_text = (PLUGIN / "hosts" / "OleFormulaObjectNative" / "src" / "FormulaOleObject.cpp").read_text(encoding="utf-8")
    force_clean_text = (PLUGIN / "tools" / "ForceClean.ps1").read_text(encoding="utf-8")
    word_adapter_text = read_word_adapter_sources()

    assert "Verb\\0" not in setup_text
    assert "\\Insertable" not in setup_text
    assert "OleFormulaRenderer" not in setup_text
    assert 'Source: "..\\hosts\\WordAddIn\\bin\\{#Config}\\net48\\MathJax-3.2.2\\*"' in setup_text
    assert 'ValueData: "672280"' in setup_text
    assert "Software\\Classes\\CLSID\\{{B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F}" in setup_text
    assert "Software\\WOW6432Node\\Classes\\CLSID\\{{B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F}" in setup_text
    assert "OLEMISC_STATIC" in native_text
    assert "OLEMISC_NOUIACTIVATE" in native_text
    assert "OLEMISC_IGNOREACTIVATEWHENVISIBLE" in native_text
    assert "STDMETHODIMP FormulaOleObject::DoVerb" in native_text
    assert "STDMETHODIMP FormulaOleObject::DoVerb(LONG, LPMSG, IOleClientSite*, LONG, HWND, LPCRECT)" in native_text
    assert "WriteNativeOleLog(L\"FormulaOleObject DoVerb.\");\n    return S_OK;" in native_text
    assert "*enumOleVerb = nullptr;" in native_text
    assert "HKLM:\\Software\\Classes\\CLSID\\$OleFormulaClassId" in force_clean_text
    assert "HKLM:\\Software\\WOW6432Node\\Classes\\CLSID\\$OleFormulaClassId" in force_clean_text
    assert "shapeScale = Math.Max(0.05f, Math.Min(widthScale, heightScale));" in word_adapter_text
    assert "inlineShape.LockAspectRatio = true" in word_adapter_text
    assert "heightScale = originalHeight / (float)naturalHeight" in word_adapter_text
    add_ole_method = word_adapter_text.split("private dynamic AddOleInlineShapeAtRange", 1)[1].split("private dynamic ReplaceOleInlineShape", 1)[0]
    insert_method = word_adapter_text.split("public Task InsertOleFormulaObjectAsync", 1)[1].split("public Task UpdateOleFormulaObjectAsync", 1)[0]
    assert "SaveOleNaturalSize" not in add_ole_method
    assert "SaveOleNaturalSize" not in insert_method
    assert "legacy" not in (PLUGIN / "hosts" / "WordAddIn" / "EditorAssets" / "settings.js").read_text(encoding="utf-8").lower()
    assert "legacy" not in (PLUGIN / "hosts" / "PowerPointAddIn" / "EditorAssets" / "settings.js").read_text(encoding="utf-8").lower()


def test_office_plugin_installation_surface_is_clean_and_explicit() -> None:
    setup_text = (PLUGIN / "installer" / "setup.iss").read_text(encoding="utf-8")
    ci_text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "ArchitecturesInstallIn64BitMode=x64compatible" in setup_text
    assert "OleFormulaObject\\x64" in setup_text
    assert "OleFormulaObject\\x86" in setup_text
    assert "OleFormulaObject\\arm64" not in setup_text
    assert "Software\\Microsoft\\Office\\Word\\Addins" in setup_text
    assert "Software\\Microsoft\\Office\\16.0\\Word\\Addins" in setup_text
    assert "Software\\Microsoft\\Office\\PowerPoint\\Addins" in setup_text
    assert "Software\\Microsoft\\Office\\16.0\\PowerPoint\\Addins" in setup_text
    assert "ClickToRun\\REGISTRY\\MACHINE\\Software\\Microsoft\\Office\\Word\\Addins" in setup_text
    assert "ClickToRun\\REGISTRY\\MACHINE\\Software\\Microsoft\\Office\\PowerPoint\\Addins" in setup_text
    assert "WOW6432Node\\Microsoft\\Office\\Word\\Addins" in setup_text
    assert "WOW6432Node\\Microsoft\\Office\\PowerPoint\\Addins" in setup_text
    assert "Run Office plugin tests" in ci_text
    assert "test/test_office_plugin_structure.py" in ci_text
    assert "lfs: true" in ci_text
    assert "Run Office plugin tests" not in release_text
    assert "Install test runner" in ci_text
    assert "Install test runner" not in release_text
    office_job = release_text.split("  build-office-plugin-installer:", 1)[1].split(
        "\n  build-linux-deb:", 1
    )[0]
    assert "actions/setup-dotnet" not in office_job
    assert "windows-2025" not in office_job
    assert "Visual Studio" not in office_job
    assert "build.bat" not in office_job
    assert "office_plugin/release/OfficePluginSetup-${version}.exe" in office_job
    assert "sha256sum" in office_job
    assert "checksum mismatch" in office_job
    assert "lfs: true" in office_job
    installer_build_text = (PLUGIN / "installer" / "build.bat").read_text(encoding="utf-8")
    assert "Build-NativeOleHandler.ps1" in installer_build_text
    assert "WindowsPowerShell\\v1.0\\powershell.exe" in installer_build_text
    assert "call powershell " not in installer_build_text
    for obsolete_release_logic in (
        "vs_BuildTools.exe",
        "Ensure Office and ATL build tools",
        "ManifestCertificateThumbprint",
        "New-SelfSignedCertificate",
        "PlatformToolset=$toolset",
        "WordVstoAddIn.user.props",
        "Install-CiBuildPrerequisites.ps1",
    ):
        assert obsolete_release_logic not in release_text
    assert "publish_assets:" in release_text
    assert "github.event_name == 'workflow_dispatch' && inputs.publish_assets" in release_text

    release_dir = PLUGIN / "release"
    installers = list(release_dir.glob("OfficePluginSetup-*.exe"))
    assert len(installers) == 1
    checksum_path = installers[0].with_suffix(installers[0].suffix + ".sha256")
    assert checksum_path.is_file()
    checksum_text = checksum_path.read_text(encoding="ascii")
    assert installers[0].name in checksum_text
    assert hashlib.sha256(installers[0].read_bytes()).hexdigest() == checksum_text.split()[0]


def test_office_plugin_help_describes_current_paths() -> None:
    for host in ("WordAddIn", "PowerPointAddIn"):
        help_html = (PLUGIN / "hosts" / host / "EditorAssets" / "help.html").read_text(encoding="utf-8")
        assert "EMF+Dual vector preview" in help_html
        assert "Compatibility PNG" not in help_html
        assert "PNG image insertion" in help_html
        assert "side pane is not an update entry point" in help_html
        assert "Press Enter in the MathLive field to start a new math row" in help_html
        assert "Press Shift+Enter to insert or update the formula" in help_html
        assert "Space inserts a mathematical thin space" in help_html
        assert "Esc does not close the editor" in help_html
        assert "Editor submissions are serialized with Office commands" in help_html
        assert "Numbered formulas center the formula and place the number" in help_html
        assert "exactly one selected managed formula" in help_html
        assert "Format All only restores manually resized formulas to natural size" in help_html
        assert "selected formulas or the whole document" not in help_html
        assert "32-bit and 64-bit Windows desktop Office only" in help_html
        assert "Office 2024 / 2021 / 2019" in help_html
        assert "Office LTSC 2024 / 2021" in help_html
    word_help = (PLUGIN / "hosts" / "WordAddIn" / "EditorAssets" / "help.html").read_text(
        encoding="utf-8",
    )
    assert "Add Number only applies to unnumbered display equations" in word_help


def test_editor_and_mathjax_are_preheated_and_reused() -> None:
    editor_interface = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Abstractions" / "IFormulaEditor.cs").read_text(encoding="utf-8")
    editor_session = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "FormulaEditorSession.cs").read_text(encoding="utf-8")
    editor = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditor.cs").read_text(encoding="utf-8")
    editor_form = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditorForm.cs").read_text(encoding="utf-8")
    mathjax_renderer = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "MathJaxSvgRenderer.cs").read_text(encoding="utf-8")
    word_controller = (PLUGIN / "hosts" / "WordAddIn" / "WordPluginController.cs").read_text(encoding="utf-8")
    power_point_controller = (PLUGIN / "hosts" / "PowerPointAddIn" / "PowerPointPluginController.cs").read_text(encoding="utf-8")
    word_vsto = (PLUGIN / "hosts" / "WordVstoAddIn" / "ThisAddIn.cs").read_text(encoding="utf-8")
    power_point_vsto = (PLUGIN / "hosts" / "PowerPointVstoAddIn" / "ThisAddIn.cs").read_text(encoding="utf-8")

    assert "Task WarmUpAsync(CancellationToken cancellationToken);" in editor_interface
    assert "public sealed class FormulaEditorSession : IDisposable" in editor_session
    assert "return _editor.WarmUpAsync(cancellationToken);" in editor_session
    assert "public Task WarmUpAsync(CancellationToken cancellationToken)" in editor
    assert "return GetOrCreateForm().WarmUpAsync();" in editor
    assert "DisposeForShutdown" in editor
    assert "_activeForm = null;" in editor
    assert "public Task WarmUpAsync()" in editor_form
    assert "_warmUpTask ??= InitializeAsync();" in editor_form
    assert "e.Cancel = true;" not in editor_form
    assert "\n            Hide();" not in editor_form
    assert "Hide();" in editor_form
    assert "editor.html?_=" not in editor_form
    assert "DateTime.UtcNow.Ticks" not in editor_form
    assert "new Uri(\"https://\" + _options.EditorHostName + \"/editor.html\")" in editor_form
    assert "public Task WarmUpAsync(CancellationToken cancellationToken)" in mathjax_renderer
    assert "return EnsureInitializedAsync(cancellationToken);" in mathjax_renderer
    assert "public sealed class MathJaxSvgRenderer : IFormulaRenderer, IDisposable" in mathjax_renderer
    for controller in (word_controller, power_point_controller):
        assert "public async Task WarmUpAsync(CancellationToken cancellationToken)" in controller
        assert "await _editorSession.WarmUpAsync(cancellationToken);" in controller
        assert "await _mathJaxRenderer.WarmUpAsync(cancellationToken);" in controller
        assert "SemaphoreSlim _commandGate" in controller
        assert "TryRunCommandAsync" in controller
        assert "TryAcceptEditorFormulaAsync" in controller
        assert "WaitAsync(0" in controller
        assert "public void Dispose()" in controller
        assert "_editorSession.Dispose();" in controller
        assert "_commandGate.Dispose();" in controller
    assert "_ = WarmUpControllerAsync(controller, statusPaneHost);" in word_vsto
    assert "_ = WarmUpControllerAsync(controller, statusPaneHost);" in power_point_vsto
    for vsto in (word_vsto, power_point_vsto):
        assert "await controller.WarmUpAsync(timeout.Token);" in vsto
        assert "controller?.Dispose();" in vsto


def test_mathjax_supports_mathlive_styles_and_chemistry() -> None:
    script_builder = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "MathJaxRenderScriptBuilder.cs"
    ).read_text(encoding="utf-8")
    runtime = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "WebView2MathJaxJavaScriptRuntime.cs"
    ).read_text(encoding="utf-8")
    response = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "MathJaxSvgRenderResponse.cs"
    ).read_text(encoding="utf-8")
    mathlive = (ROOT / "src" / "assets" / "mathlive" / "vendor" / "mathlive.min.mjs").read_text(
        encoding="utf-8"
    )
    normalizer = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Abstractions"
        / "MathLiveLatexStyleNormalizer.cs"
    ).read_text(encoding="utf-8")

    for package in ("bbox", "boldsymbol", "color", "enclose", "mhchem"):
        assert f"'[tex]/{package}'" in script_builder
    assert "normalizeMathLiveLatex" in script_builder
    assert ".replace(/\\\\bm" in script_builder
    assert 'FormulaFontStyle.Bold => "\\\\bm{" + latex + "}"' in normalizer
    assert 'FormulaFontStyle.Bold => "\\\\boldsymbol{" + latex + "}"' not in normalizer
    assert "'\\\\bbox[' + color.content.trim()" in script_builder
    assert ".replace(/(^|[^\\\\])\\$/g, '$1')" in script_builder
    assert "MathJax rendering failed:" in response
    assert "SetVirtualHostNameToFolderMapping" in runtime
    assert "MathJax-script" in runtime
    assert "File.ReadAllText(mathJaxBundlePath)" not in runtime
    assert 'version="0.110.0"' in mathlive
    assert "toMathMl: function(input)" in script_builder
    assert "MathJax.startup.document.toMML(root)" in script_builder
    for host in ("WordAddIn", "PowerPointAddIn"):
        project = (
            PLUGIN / "hosts" / host / f"LaTeXSnipper.OfficePlugin.{host}.csproj"
        ).read_text(encoding="utf-8")
        vendor_item = project.split(
            '<Content Include="..\\..\\..\\src\\assets\\mathlive\\vendor\\**\\*">', 1
        )[1].split("</Content>", 1)[0]
        assert "<CopyToOutputDirectory>Always</CopyToOutputDirectory>" in vendor_item


def test_editor_applies_formula_metadata_color() -> None:
    editor_form = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveFormulaEditorForm.cs"
    ).read_text(encoding="utf-8")
    shared_input = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "mathfield-input.js"
    ).read_text(encoding="utf-8")
    assert '["fontColor"] = _currentInitialFormula?.FontColor ?? "#000000"' in editor_form
    assert "function setDefaultColor(mathfield, fontColor)" in shared_input
    assert "mathfield.style.color = color" in shared_input
    for host in ("WordAddIn", "PowerPointAddIn"):
        editor = (PLUGIN / "hosts" / host / "EditorAssets" / "editor.js").read_text(encoding="utf-8")
        assert "setDefaultColor(" in editor


def test_office_native_conversion_paths_use_local_mathjax() -> None:
    word_controller = (PLUGIN / "hosts" / "WordAddIn" / "WordPluginController.cs").read_text(encoding="utf-8")
    word_document_commands = (
        PLUGIN / "hosts" / "WordAddIn" / "WordPluginController.DocumentCommands.cs"
    ).read_text(encoding="utf-8")
    omml_converter = (PLUGIN / "hosts" / "WordAddIn" / "MathMlToOmmlConverter.cs").read_text(encoding="utf-8")
    native_omml_converter = (
        PLUGIN / "hosts" / "WordAddIn" / "OmmlToMathMlConverter.cs"
    ).read_text(encoding="utf-8")
    word_entry = (PLUGIN / "hosts" / "WordAddIn" / "WordFormulaEntry.cs").read_text(encoding="utf-8")
    word_adapter = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.SelectionDiscovery.cs"
    ).read_text(encoding="utf-8")
    word_lifecycle = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.FormulaLifecycle.cs"
    ).read_text(encoding="utf-8")
    mathjax_script = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Rendering"
        / "MathJaxRenderScriptBuilder.cs"
    ).read_text(encoding="utf-8")
    power_point_controller = (
        PLUGIN / "hosts" / "PowerPointAddIn" / "PowerPointPluginController.cs"
    ).read_text(encoding="utf-8")
    png_rasterizer = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "SvgPngRasterizer.cs"
    ).read_text(encoding="utf-8")

    assert "ConvertToMathMlAsync" in word_controller
    assert 'new[] { "omml" }' not in word_controller
    assert "MML2OMML.XSL" in omml_converter
    assert "OMML2MML.XSL" in native_omml_converter
    assert "XslCompiledTransform" in omml_converter
    assert "XslCompiledTransform" in native_omml_converter
    assert "NormalizeMathMl(output.ToString())" in native_omml_converter
    assert 'document.Root?.Name.LocalName == "math"' in native_omml_converter
    assert "IsNativeWordFormula" in word_entry
    assert "CollectSelectedNativeWordFormulaEntries" in word_adapter
    assert "TryGetParentContentControl(range) != null" in word_adapter
    assert "ReplaceNativeWordFormulaWithOleAsync" in word_document_commands
    assert "ReplaceNativeWordFormulaWithOleAsync" in word_lifecycle
    assert "RestoreNativeWordFormula(insertionRange, originalOoxml)" in word_lifecycle
    assert "insertionRange.InsertXML(originalOoxml)" in word_lifecycle
    assert 'StartsWith("<?xml"' in word_controller
    assert "<\\?xml[\\s\\S]*?\\?>" in mathjax_script
    assert "^<([a-z_][\\w.-]*:)?math" not in mathjax_script
    assert "mathml: trimmed" in mathjax_script
    assert "SvgPngRasterizer.Rasterize" in power_point_controller
    assert 'new[] { "png" }' not in power_point_controller
    assert "SvgVectorGraphicsRenderer.Draw" in png_rasterizer


def test_powerpoint_uses_one_initial_scale_for_ole_and_png() -> None:
    controller = (
        PLUGIN / "hosts" / "PowerPointAddIn" / "PowerPointPluginController.cs"
    ).read_text(encoding="utf-8")
    assert "private const double InitialFormulaScale = 2.5;" in controller
    assert controller.count("FontScale = InitialFormulaScale * metadata.FontScale") == 2
    assert "FontScale = 3.0" not in controller


def test_powerpoint_conversion_formatting_and_defaults_are_connected() -> None:
    host = PLUGIN / "hosts" / "PowerPointAddIn"
    ribbon = (host / "Ribbon" / "PowerPointRibbon.xml").read_text(encoding="utf-8")
    callbacks = (host / "PowerPointRibbonCallbacks.cs").read_text(encoding="utf-8")
    vsto_callbacks = (
        PLUGIN / "hosts" / "PowerPointVstoAddIn" / "PowerPointRibbonExtensibility.cs"
    ).read_text(encoding="utf-8")
    commands = (host / "PowerPointPluginController.DocumentCommands.cs").read_text(encoding="utf-8")
    adapter = (host / "DynamicPowerPointApplicationAdapter.cs").read_text(encoding="utf-8")
    metadata = (host / "PowerPointFormulaMetadataStore.cs").read_text(encoding="utf-8")
    settings = (host / "PowerPointPluginSettings.cs").read_text(encoding="utf-8")
    settings_window = (host / "PowerPointSettingsWindow.cs").read_text(encoding="utf-8")
    settings_html = (host / "EditorAssets" / "settings.html").read_text(encoding="utf-8")

    assert ribbon.count("<tab ") == 1
    assert 'id="LaTeXSnipperPowerPointConversionGroup"' in ribbon
    assert 'id="LaTeXSnipperPowerPointFormattingGroup"' in ribbon
    assert 'imageMso="ObjectEditDialog"' in ribbon
    for callback in (
        "OnConvertSelectedToOle",
        "OnConvertSelectedToPng",
        "OnFormatSelected",
        "OnFormatAll",
    ):
        assert callback in ribbon
        assert callback in callbacks
        assert callback in vsto_callbacks

    assert "ConvertAllToOleAsync" not in commands
    assert "ConvertAllToPngAsync" not in commands
    convert_method = commands.split("private async Task ConvertSelectedAsync", 1)[1].split(
        "private async Task FormatAsync",
        1,
    )[0]
    assert "LoadSelectedFormulaEntriesAsync" in convert_method
    assert "SingleFormulaRequired" not in convert_method
    assert "entry.Metadata.RenderEngine == target" in convert_method
    assert "continue;" in convert_method
    assert "LoadAllFormulaEntriesAsync" not in adapter
    assert "ResetCustomFormulaSizesAsync" in adapter
    assert "ResetCustomFormulaSizesAsync" in commands
    full_format_branch = commands.split("if (all)", 1)[1].split(
        "PowerPointPluginSettings settings",
        1,
    )[0]
    assert "ResetCustomFormulaSizesAsync" in full_format_branch
    assert "ReplaceEntryAsync" not in full_format_branch
    assert "InsertOleFormulaObjectOnSlideAsync" in adapter
    assert "InsertFormulaImageOnSlideAsync" in adapter
    assert "entry.SlideIndex" in commands
    assert "Math.Abs(entry.Scale - 1) > 0.01" in commands
    assert "NoFormattingNeededStatus" in commands
    assert "LoadFromShape" in metadata
    assert 'shape.AlternativeText = "LaTeXSnipper formula "' in metadata
    for tag in (
        "LatexChunkCountTag",
        "LatexByteLengthTag",
        "RenderEngineTag",
        "FontColorTag",
        "FontStyleTag",
        "FontScaleTag",
    ):
        assert tag in metadata
    assert "LoadFromAlternativeText" not in metadata
    assert "Encoding.UTF8.GetBytes" in metadata
    assert 'valueByte.ToString("X2"' in metadata
    assert "ReadEncodedText(shape)" in metadata
    assert "ReadRequiredEnumTag" in metadata
    assert "ReadEnumTag" not in metadata
    assert "shape.Tags.Add(FontColorTag, metadata.FontColor)" in metadata
    assert "shape.Tags.Add(FontStyleTag, metadata.FontStyle.ToString())" in metadata
    assert "shape.Tags.Add(FontScaleTag, metadata.FontScale.ToString" in metadata
    assert "FormulaColor" in settings
    assert "FormulaFontStyle" in settings
    assert "FormulaFontScale" in settings
    assert "MaximumFormulaFontScale = 1.5" in settings
    assert '["formulaColor"] = settings.FormulaColor' in settings_window
    assert '["formulaFontStyle"] = settings.FormulaFontStyle.ToString()' in settings_window
    assert '["formulaFontScale"] = settings.FormulaFontScale' in settings_window
    assert 'id="formulaColor"' in settings_html
    assert 'id="formulaFontStyle"' in settings_html
    assert 'id="formulaFontScale"' in settings_html
    assert "settings.FormulaFontScale" in commands


def test_word_and_powerpoint_load_current_font_and_color_metadata() -> None:
    word_controller = (
        PLUGIN / "hosts" / "WordAddIn" / "WordPluginController.cs"
    ).read_text(encoding="utf-8")
    powerpoint_controller = (
        PLUGIN / "hosts" / "PowerPointAddIn" / "PowerPointPluginController.cs"
    ).read_text(encoding="utf-8")
    editor_form = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "MathLiveFormulaEditorForm.cs"
    ).read_text(encoding="utf-8")
    shared_input = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "mathfield-input.js"
    ).read_text(encoding="utf-8")

    word_load = word_controller.split("public async Task LoadSelectedAsync", 1)[1].split(
        "public async Task DeleteSelectedAsync",
        1,
    )[0]
    powerpoint_load = powerpoint_controller.split(
        "public async Task LoadSelectedAsync",
        1,
    )[1].split("public async Task DeleteSelectedAsync", 1)[0]
    assert "OpenForEditAsync(selected" in word_load
    assert "OpenForEditAsync(selected" in powerpoint_load
    assert '["fontStyle"] = (_currentInitialFormula?.FontStyle' in editor_form
    assert '["fontColor"] = _currentInitialFormula?.FontColor' in editor_form
    assert "mathfield.__latexSnipperDefaultFontStyle = style" in shared_input
    assert "mathfield.applyStyle(style);" in shared_input


def test_word_formatting_skips_default_formulas_and_inline_conversion_removes_wrapper() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    commands = (host / "WordPluginController.DocumentCommands.cs").read_text(encoding="utf-8")
    adapter = read_word_adapter_sources()
    assert "NeedsFormatting(formula, settings)" in commands
    assert "_wordAdapter.HasCustomFormulaScale(metadata)" in commands
    assert "formula.FontStyle != settings.FormulaFontStyle" in commands
    assert "settings.FormulaFontScale" in commands
    assert "PrepareRenderedFormulaAsync" in commands
    assert "_editorSession.UpdateDraftIfOpenAsync(formatted, updateMode: true" not in commands
    assert "NoFormattingNeededStatus" in commands
    assert "control.Delete(true);" in adapter
    assert "RemoveOmmlConversionSource(control, metadata)" in adapter
    assert "ResetManagedEquationBaseline" in adapter
    assert "equation.Range.Font.Position = 0" in adapter


def test_word_status_task_panes_are_window_scoped() -> None:
    addin = (PLUGIN / "hosts" / "WordVstoAddIn" / "ThisAddIn.cs").read_text(encoding="utf-8")
    assert "ActiveWindowStatusPaneHost" in addin
    assert "Dictionary<int, PaneEntry>" in addin
    assert "addIn.CustomTaskPanes.Add(control, WordAddInText.Get(\"TaskPaneTitle\"), window)" in addin
    assert "private Microsoft.Office.Tools.CustomTaskPane? statusTaskPane" not in addin
    assert "private WordStatusTaskPaneControl? statusPaneControl" not in addin


def test_powerpoint_status_task_panes_are_window_scoped() -> None:
    addin = (PLUGIN / "hosts" / "PowerPointVstoAddIn" / "ThisAddIn.cs").read_text(encoding="utf-8")
    assert "ActiveWindowStatusPaneHost" in addin
    assert "Dictionary<int, PaneEntry>" in addin
    assert "using PowerPoint = Microsoft.Office.Interop.PowerPoint;" in addin
    assert "Application.WindowActivate += OnWindowActivate;" in addin
    assert "Application.WindowActivate -= OnWindowActivate;" in addin
    assert "private void OnWindowActivate(PowerPoint.Presentation presentation, PowerPoint.DocumentWindow window)" in addin
    assert "InitializeActiveStatusPane();" in addin
    assert "public void EnsurePane(PowerPoint.DocumentWindow window)" in addin
    assert "PowerPoint.DocumentWindow window = addIn.Application.ActiveWindow" in addin
    assert "Convert.ToInt32(window.HWND)" in addin
    assert "addIn.CustomTaskPanes.Add(control, PowerPointAddInText.Get(\"TaskPaneTitle\"), window)" in addin
    assert "TryGetActivePane(out PaneEntry entry)" in addin
    assert "CreateTaskPane(control, window)" not in addin
    assert "addIn.CustomTaskPanes.Add(control, PowerPointAddInText.Get(\"TaskPaneTitle\"));" not in addin
    assert "PowerPointAddInFactory.CreateController(Application, visibleStatusSink, statusPaneHost)" in addin
    assert "private Microsoft.Office.Tools.CustomTaskPane? statusTaskPane" not in addin
    assert "private PowerPointStatusTaskPaneControl? statusPaneControl" not in addin


def test_word_large_ole_selection_remains_selection_first() -> None:
    adapter = read_word_adapter_sources()
    selected = adapter.split("private IReadOnlyList<SelectedWordFormula> CollectSelectedFormulas()", 1)[1].split(
        "private void AddSelectedFormulasFromRange", 1
    )[0]
    anchor = adapter.split("private void AddSelectedOleInlineShapesFromAnchor", 1)[1].split(
        "private void AddSelectedOleInlineShape", 1
    )[0]
    assert "AddSelectedOleInlineShapesFromAnchor" in selected
    assert "selectionType != 7 && selectionType != 8" in anchor
    assert "selectionRange.Paragraphs.Item(1).Range" in anchor
    assert "ActiveDocument.InlineShapes" not in anchor


def test_word_load_selected_is_selection_first() -> None:
    adapter = read_word_adapter_sources()
    find_selected = adapter.split("private IReadOnlyList<SelectedWordFormula> CollectSelectedFormulas()", 1)[1].split("private void AddSelectedFormulasFromRange", 1)[0]
    selected_ole = adapter.split("private void AddSelectedOleInlineShapes", 1)[1].split("private void AddSelectedOleInlineShape", 1)[0]
    selected_formula = adapter.split("private void AddSelectedFormula", 1)[1].split("private object FindFormulaControlById", 1)[0]

    assert "AddSelectedFormulasOverlappingRange" not in adapter
    assert "AddSelectedFormulasOverlappingRange" not in find_selected
    assert "ActiveDocument.ContentControls" not in find_selected
    assert "ActiveDocument.InlineShapes" not in selected_ole
    assert "TryFindOleInlineShapeById" not in selected_formula
    assert "FindFormulaControlById" not in selected_formula
    assert "selectionType != 6 && selectionType != 7 && selectionType != 8" in adapter
    assert "inlineShape.AlternativeText = tag;" in adapter
    assert "Word did not preserve the OLE formula identifier." in adapter
    assert "WordFormulaMetadataStore.Save(" in adapter


def test_emf_plus_dual_writer_uses_float_vector_paths() -> None:
    writer = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "SvgEnhancedMetafileWriter.cs").read_text(encoding="utf-8")
    vector_renderer = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "SvgVectorGraphicsRenderer.cs"
    ).read_text(encoding="utf-8")
    path_parser = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "SvgPathDataParser.cs").read_text(encoding="utf-8")
    transform_parser = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Rendering" / "SvgTransformParser.cs").read_text(encoding="utf-8")

    assert "EmfType.EmfPlusDual" in writer
    assert "new RectangleF" in writer
    assert "HorizontalPaddingPoints" in writer
    assert "VerticalPaddingPoints" in writer
    assert "graphics.TranslateTransform(horizontalPaddingPixels, verticalPaddingPixels)" in writer
    assert "SvgVectorGraphicsRenderer.Draw" in writer
    assert "GraphicsPath" in vector_renderer
    assert "batch.Path.AddPath" in vector_renderer
    assert "graphics.FillPath(brush, batch.Path)" in vector_renderer
    assert "graphics.DrawPath(pen, batch.Path)" in vector_renderer
    assert 'ResolvePaint(element, "stroke"' in vector_renderer
    assert '"stroke-width"' in vector_renderer
    assert "ApplyNestedViewport" in vector_renderer
    assert "CreateNestedViewportClip" in vector_renderer
    assert "graphics.SetClip(batch.Clip, CombineMode.Intersect)" in vector_renderer
    assert 'element.Name.LocalName == "svg" && element.Parent != null' in vector_renderer
    assert 'element.Name.LocalName == "text"' in vector_renderer
    assert 'element.Name.LocalName == "polygon"' in vector_renderer
    assert 'element.Name.LocalName == "polyline"' in vector_renderer
    assert 'element.Name.LocalName == "line"' in vector_renderer
    assert 'element.Name.LocalName == "circle"' in vector_renderer
    assert 'element.Name.LocalName == "ellipse"' in vector_renderer
    assert "AddPolygonGeometry" in vector_renderer
    assert "AddPolylineGeometry" in vector_renderer
    assert "AddLineGeometry" in vector_renderer
    assert "AddEllipseGeometry" in vector_renderer
    assert "ParsePoints" in vector_renderer
    assert "path.AddString(" in vector_renderer
    assert '"Microsoft YaHei", "SimSun", "Segoe UI"' in vector_renderer
    assert "ResolvePaint" in vector_renderer
    assert "ColorTranslator.FromHtml" in vector_renderer
    assert "new SolidBrush(batch.Color)" in vector_renderer
    assert "DrawString" not in writer
    assert "DrawText" not in writer
    assert "Math.Round" not in writer
    assert "Math.Ceiling(points / PointsPerInch * Dpi)" in writer
    assert "AddBezier" in path_parser
    assert "AddQuadratic" in path_parser
    assert "PointF" in path_parser
    assert "float.Parse" in path_parser
    assert "matrix|translate|scale" in transform_parser
    assert "rotate" not in transform_parser
    assert "arc" not in path_parser.lower()
    assert "case 'A'" not in path_parser


def test_office_plugin_build_outputs_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "office_plugin/**/bin/" in gitignore
    assert "office_plugin/**/obj/" in gitignore


def test_word_document_workflow_tabs_are_modular_and_connected() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    ribbon = (host / "Ribbon" / "WordRibbon.xml").read_text(encoding="utf-8")
    callbacks = (host / "WordRibbonCallbacks.cs").read_text(encoding="utf-8")
    controller = (host / "WordPluginController.DocumentCommands.cs").read_text(encoding="utf-8")
    main_controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")
    operations = (host / "DynamicWordApplicationAdapter.Operations.cs").read_text(encoding="utf-8")
    adapter = read_word_adapter_sources()
    formatting = (host / "DynamicWordApplicationAdapter.Formatting.cs").read_text(encoding="utf-8")
    metadata_store = (host / "WordFormulaMetadataStore.cs").read_text(encoding="utf-8")
    metadata = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Abstractions" / "FormulaMetadata.cs").read_text(encoding="utf-8")
    settings = (host / "WordPluginSettings.cs").read_text(encoding="utf-8")
    numbering = (host / "WordAutomaticNumberFormatter.cs").read_text(encoding="utf-8")

    assert ribbon.count("<tab ") == 1
    for group_id in (
        "LaTeXSnipperConversionGroup",
        "LaTeXSnipperReferenceGroup",
        "LaTeXSnipperNumberingGroup",
        "LaTeXSnipperFormattingGroup",
    ):
        assert f'id="{group_id}"' in ribbon
    assert 'id="ConvertToOleMenu"' not in ribbon
    assert 'id="ConvertToOmmlMenu"' not in ribbon
    assert 'id="SelectedToOleButton"' in ribbon
    assert 'id="SelectedToOmmlButton"' in ribbon
    assert 'imageMso="ObjectEditDialog"' in ribbon
    assert 'imageMso="ConvertTextToTable"' in ribbon
    assert 'id="FormattingSettingsButton"' not in ribbon
    assert 'imageMso="ObjectEdit"' not in ribbon
    assert 'imageMso="OutlineNumbering"' not in ribbon
    for callback in (
        "OnConvertSelectedToOle",
        "OnConvertSelectedToOmml",
        "OnInsertReference",
        "OnInsertChapterBoundary",
        "OnInsertSectionBoundary",
        "OnFormatSelected",
        "OnFormatAll",
    ):
        assert callback in ribbon
        assert callback in callbacks

    assert "ConvertSelectedAsync" in controller
    convert_method = controller.split("private async Task ConvertSelectedAsync", 1)[1].split(
        "private async Task FormatAsync",
        1,
    )[0]
    assert "LoadSelectedFormulaEntriesAsync" in convert_method
    assert "SingleFormulaRequired" not in convert_method
    assert "formula.RenderEngine == targetEngine" in convert_method
    assert "continue;" in convert_method
    assert "ConvertAllToOleAsync" not in controller
    assert "ConvertAllToOmmlAsync" not in controller
    assert "NoConversionNeededStatus" in controller
    assert "FormatAsync(bool all" in controller
    assert 'WordAddInText.Get("WorkingStatus")' in controller
    assert "reportProgress: false" in controller
    assert "MathLiveLatexStyleNormalizer.RemoveColorFormatting" in controller
    assert "MathLiveLatexStyleNormalizer.ApplyRenderFontStyle" in main_controller
    assert "LoadAllFormulaEntriesAsync" not in operations
    assert "LoadSelectedFormulaEntriesAsync" in adapter
    assert ".OrderByDescending(item => item.Start)" in adapter
    assert "AddOleInlineShapesInsideSelection(selectedFormulas)" in adapter
    assert "shapeStart >= selectionStart && shapeStart < selectionEnd" in adapter
    assert "ResetCustomFormulaSizesAsync" in controller
    assert "ResetCustomFormulaSizesAsync" in formatting
    natural_size_method = controller.split("private async Task ResetAllNaturalSizesAsync", 1)[1].split(
        "private async Task InsertBoundaryAsync",
        1,
    )[0]
    assert "PrepareRenderedFormulaAsync" not in natural_size_method
    assert "SaveOmmlNaturalFontSize" in adapter
    assert "TryLoadOmmlNaturalFontSize" in formatting
    assert "OmmlNaturalFontSizeVariablePrefix" in metadata_store
    assert "double oleFontSizePoints = ReadOleEquivalentFontSize(inlineShape)" in adapter
    assert "SaveFormulaMetadata(metadata)" in adapter.split("public Task UpdateFormulaAsync", 1)[1].split(
        "private dynamic RemoveOmmlConversionSource",
        1,
    )[0]
    assert "replacementOoxml = equationOoxml" in adapter
    assert "metadata.NumberingMode == NumberingMode.None" in adapter
    assert "replacementOoxml = equationOoxml" in adapter
    assert 'private const string InlineConversionSlot = "\\u2060";' in adapter
    assert "CreateInlineConversionSlot(insertionPoint)" in adapter
    assert "control.Delete(false)" in adapter
    assert "dynamic insertionRange = RemoveOmmlConversionSource(control, metadata)" in adapter
    remove_source = adapter.split("private dynamic RemoveOmmlConversionSource", 1)[1].split(
        "private dynamic CreateInlineConversionSlot",
        1,
    )[0]
    assert "metadata.NumberingMode != NumberingMode.None" in remove_source
    assert "metadata.DisplayMode == FormulaDisplayMode.Display" in remove_source
    assert "control.Range.Text = InlineConversionSlot" in remove_source
    assert "control.Delete(false)" in remove_source
    assert "metadata.RenderEngine != actualRenderEngine" in adapter
    assert "SaveFormulaMetadata(corrected)" not in adapter
    assert "SaveNewFormulaMetadata" not in adapter
    assert "LoadMetadataControlIndex" not in adapter
    assert "AddMetadataControlDeletionTarget" not in adapter
    assert "GetNextAutomaticNumberText()" in main_controller
    assert "GetBackend(metadata.RenderEngine)" in main_controller
    assert "SetAutoNumberChapter" in adapter
    assert "SetAutoNumberSection" in adapter
    assert "ReferencePlaceholderTag" in operations
    assert "ReferenceTagPrefix" in operations
    assert '" REF " + bookmarkName + " \\\\h "' in operations
    assert "ApplyReferenceControlFormatting" in operations
    assert "HideContentControlChrome(control)" in operations
    assert "control.Range.Font.Position = 0" in operations
    assert "control.Range.Font.Superscript = 0" in operations
    assert "control.Range.Font.Subscript = 0" in operations
    assert "LoadMetadataControlIndex" not in operations
    assert "TryNavigateSelectedReference" not in operations
    assert "FindSelectedCommandControls" in operations
    assert "DeleteCommandControl" in operations
    assert "ActiveDocument.ContentControls" in operations
    assert "Task<IReadOnlyList<string>> DeleteSelectedFormulaAsync" in adapter
    assert "UpdateFormulaReferences" in operations
    assert "ChapterBoundaryTag" in operations
    assert "SectionBoundaryTag" in operations
    assert "FontColor" in metadata
    assert "FontStyle" in metadata
    assert "FontScale" in metadata
    assert "FontWeightPercent" not in metadata
    assert "FormulaFontStyle" in settings
    assert "FormulaFontScale" in settings
    assert "MaximumFormulaFontScale = 1.5" in settings
    assert "FormulaWeightPercent" not in settings
    assert "IncludeChapter" in settings
    assert "IncludeSection" in settings
    assert "HideChapterBoundary" in settings
    assert "HideSectionBoundary" in settings
    assert "NumberSeparator" in settings
    assert "string.Join(settings.NumberSeparator, parts)" in numbering
    assert "SectionArabic" not in numbering
    assert "LoadNumberingDocumentEntries()" in adapter
    assert "LoadFormulaMetadataById" not in adapter
    assert "ApplyAutomaticNumberAsync" not in adapter
    assert "ApplyAutomaticNumberAsync" not in (
        host / "IWordApplicationAdapter.cs"
    ).read_text(encoding="utf-8")
    assert "MeasureFormulaWidthPoints" not in adapter
    assert "WdHorizontalPositionRelativeToTextBoundary" not in adapter
    assert "contentWidth / 2" in adapter
    assert "WdAlignTabCenter" in adapter
    renumber_method = adapter.split("public Task<int> RenumberAutomaticFormulasAsync", 1)[1].split(
        "private void ReplaceFormulaContent",
        1,
    )[0]
    assert "ApplyNumberingBoundaryVisibility(settings)" not in renumber_method
    assert "return ordered" in operations
    auto_number = main_controller.split("public async Task AutoNumberSelectedAsync", 1)[1].split(
        "public async Task RenumberAllAsync",
        1,
    )[0]
    assert "UpdateRenderedFormulaAndRenumberAsync(numbered" in auto_number
    assert "PrepareRenderedFormulaAsync" in main_controller
    assert "UpdatePreparedFormulaAsync(prepared" in main_controller


def test_word_formula_color_default_tracks_windows_theme() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    defaults = (host / "WordFormulaColorDefaults.cs").read_text(encoding="utf-8")
    settings = (host / "WordPluginSettings.cs").read_text(encoding="utf-8")
    settings_window = (host / "WordSettingsWindow.cs").read_text(encoding="utf-8")
    settings_js = (host / "EditorAssets" / "settings.js").read_text(encoding="utf-8")

    assert "AppsUseLightTheme" in defaults
    assert "OfficeThemeRegistryPath" in defaults
    assert "OfficeThemeValue" in defaults
    assert "Convert.ToInt32(officeTheme) == 2" in defaults
    assert 'IsDarkMode() ? "#FFFFFF" : "#000000"' in defaults
    assert "UseSystemFormulaColor" in settings
    assert "defaultValue: true" in settings
    assert '["defaultFormulaColor"] = WordFormulaColorDefaults.Current' in settings_window
    assert '["useSystemFormulaColor"] = settings.UseSystemFormulaColor' in settings_window
    assert '["formulaFontScale"] = settings.FormulaFontScale' in settings_window
    assert "useSystemFormulaColor = false" in settings_js
    assert "useSystemFormulaColor = true" in settings_js
    assert "formulaFontScale" in settings_js
    assert "percentToScale" in settings_js
    assert "resetToWhite" in settings_js
    adapter = read_word_adapter_sources()
    controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")
    assert "WdColorAutomatic" in adapter
    assert "WordPluginSettings.Load().UseSystemFormulaColor" in adapter
    assert "backend == FormulaInsertionBackend.Ole || !settings.UseSystemFormulaColor" in controller


def test_installed_asset_resolvers_do_not_trust_vsto_cache_location() -> None:
    for host_name in ("WordAddIn", "PowerPointAddIn"):
        resolver = (
            PLUGIN / "hosts" / host_name / "InstalledAssetResolver.cs"
        ).read_text(encoding="utf-8")
        method = resolver.split("public static string? FindInstallDirectory()", 1)[1]

        assert method.index("foreach (string subPath in RegistryPaths)") < method.index(
            "Assembly.Location"
        )
        assert "Registry.LocalMachine.OpenSubKey(subPath)" in resolver
        assert "ContainsHostAssets" in resolver
        assert 'Directory.Exists(Path.Combine(directory!, "EditorAssets"))' in resolver


def test_word_insert_status_and_inline_conversion_preserve_semantics() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    text = (host / "WordAddInText.cs").read_text(encoding="utf-8")
    controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")
    adapter = read_word_adapter_sources()

    assert '"OleInsertedStatus" => "已插入 OLE 公式。"' in text
    assert '"OmmlInsertedStatus" => "已插入 OMML 公式。"' in text
    assert 'WordAddInText.Get("OleInsertedStatus")' in controller
    assert 'WordAddInText.Get("OmmlInsertedStatus")' in controller
    assert "CreateInlineConversionSlot(insertionPoint)" in adapter
    assert "HasContentAfterRangeInParagraph(inlineShape.Range)" in adapter
    assert "MergeFollowingParagraphIntoFormulaParagraph" in adapter
    assert "insertionRange.InsertXML(replacementOoxml)" in adapter
    assert "control.Delete(false)" in adapter
    assert "CreateInlineConversionSlot(insertionPoint)" in adapter
    remove_source = adapter.split("private dynamic RemoveOmmlConversionSource", 1)[1].split(
        "private dynamic CreateInlineConversionSlot",
        1,
    )[0]
    assert "control.Range.Text = InlineConversionSlot" in remove_source
    assert "control.Delete(false)" in remove_source


def test_word_taskpane_rebuilds_preview_when_restoring_draft() -> None:
    taskpane = (
        PLUGIN / "hosts" / "WordAddIn" / "EditorAssets" / "taskpane.js"
    ).read_text(encoding="utf-8")

    assert "function createPreviewField(latex)" in taskpane
    assert "els.previewHost.replaceChildren(field)" in taskpane
    assert "setLatex(payload.latex || DEFAULT_LATEX, true)" in taskpane


def test_word_dynamic_adapter_is_split_by_responsibility() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    main = host / "DynamicWordApplicationAdapter.cs"
    expected_modules = (
        "FormulaLifecycle",
        "Selection",
        "SelectionDiscovery",
        "Numbering",
        "Layout",
        "Deletion",
        "Metadata",
        "ComInterop",
    )

    assert len(main.read_text(encoding="utf-8").splitlines()) < 180
    for module in expected_modules:
        path = host / f"DynamicWordApplicationAdapter.{module}.cs"
        assert path.is_file()
        assert "public sealed partial class DynamicWordApplicationAdapter" in path.read_text(encoding="utf-8")


def test_word_number_controls_hide_content_control_chrome() -> None:
    lifecycle = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.FormulaLifecycle.cs"
    ).read_text(encoding="utf-8")
    alignment = lifecycle.split(
        "private static void ApplyNumberControlVerticalAlignment",
        1,
    )[1].split("private double ReadManagedEquationFontSize", 1)[0]

    assert "HideContentControlChrome(control)" in alignment
    assert "control.Range.Font.Position = offset" in alignment


def test_word_managed_content_control_chrome_matches_control_role() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    interop = (host / "DynamicWordApplicationAdapter.ComInterop.cs").read_text(encoding="utf-8")
    operations = (host / "DynamicWordApplicationAdapter.Operations.cs").read_text(encoding="utf-8")
    metadata = (host / "DynamicWordApplicationAdapter.Metadata.cs").read_text(encoding="utf-8")
    builder = (host / "WordOmmlDocumentBuilder.cs").read_text(encoding="utf-8")

    assert "private static void HideContentControlChrome" in interop
    assert "control.Appearance = 2" in interop
    assert "private static void ShowContentControlChrome" in interop
    assert "control.Appearance = 0" in interop
    assert "ApplyBoundaryVisibility" in operations
    boundary_visibility = operations.split(
        "private static void ApplyBoundaryVisibility",
        1,
    )[1]
    assert "HideContentControlChrome(control)" in boundary_visibility
    assert "ApplyMetadataControlFormatting" not in metadata
    assert 'xmlns:w15=\\"http://schemas.microsoft.com/office/word/2012/wordml\\"' in builder
    assert "BuildFlatOpcEquationContentDocument" in builder
    assert builder.count('<w15:appearance w15:val=\\"hidden\\"/>') == 1
    assert '<w15:appearance w15:val=\\"tags\\"/>' not in builder


def test_word_numbered_omml_insert_is_single_pass_and_uses_configured_backend() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    lifecycle = (host / "DynamicWordApplicationAdapter.FormulaLifecycle.cs").read_text(
        encoding="utf-8"
    )
    controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")

    insert_method = lifecycle.split("public Task InsertManagedEquationAsync", 1)[1].split(
        "public Task InsertOleFormulaObjectAsync",
        1,
    )[0]
    assert "range.InsertXML(ooxml)" in insert_method
    assert "ReplaceParagraphWithNumberedFormula(" not in insert_method
    assert "ShowContentControlChrome((dynamic)equationControl)" in lifecycle
    insert_command = controller.split("private async Task InsertAndRenumberIfNeededAsync", 1)[1].split(
        "private static string BuildFormattedLatex",
        1,
    )[0]
    assert "includeEquationOoxml: false" in insert_command
    assert 'WordAddInText.Get("OmmlInsertingStatus")' in controller


def test_word_formula_metadata_does_not_create_hidden_document_controls() -> None:
    store = (
        PLUGIN / "hosts" / "WordAddIn" / "WordFormulaMetadataStore.cs"
    ).read_text(encoding="utf-8")
    metadata_adapter = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.Metadata.cs"
    ).read_text(encoding="utf-8")

    assert "WordFormulaMetadataStore.Save(" in metadata_adapter
    assert "SaveFormulaMetadata(equationControl, metadata)" in metadata_adapter
    assert "string tag = WordFormulaMetadataStore.Save" in metadata_adapter
    assert "shape.Tag = tag" in metadata_adapter
    assert "FormulaMetadata stored = WordFormulaMetadataStore.Load" in metadata_adapter
    assert "shape.AlternativeText = WordFormulaMetadataStore.Save" in metadata_adapter
    assert "TryLoadOleNaturalSize(" in metadata_adapter
    assert "ContentControls.Add" not in store
    assert "MetadataControlTagPrefix" not in store
    assert "MaxWordTagLength = 64" in store
    assert "ValidateTagLength" in store
    assert "ReadRequiredDouble" in store
    assert "ReadEnum(dto, \"displayMode\"," not in store
    assert "WithRenderEngine(metadata, actualRenderEngine)" not in metadata_adapter


def test_word_ole_natural_size_uses_the_actual_inserted_shape() -> None:
    lifecycle = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.FormulaLifecycle.cs"
    ).read_text(encoding="utf-8")
    tag_method = lifecycle.split("private static void TagOleInlineShape", 1)[1]

    assert "(float width, float height) = GetInlineShapeSize" in tag_method
    assert "metadata,\n            width,\n            height" in tag_method
    assert "presentation.WidthPoints,\n            presentation.HeightPoints" not in tag_method


def test_word_renumbering_indexes_formula_objects_once() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    operations = (host / "DynamicWordApplicationAdapter.Operations.cs").read_text(
        encoding="utf-8"
    )
    numbering = (host / "DynamicWordApplicationAdapter.Numbering.cs").read_text(
        encoding="utf-8"
    )
    load_entries = operations.split("private IReadOnlyList<NumberingDocumentEntry> LoadNumberingDocumentEntries()", 1)[1]

    assert "Dictionary<string, IndexedFormulaObject>" in load_entries
    assert "ActiveDocument.InlineShapes" in load_entries
    assert "LoadFormulaMetadataById(equationId)" not in load_entries
    assert "formulaObject.Value," in load_entries
    assert "formulaObject.RenderEngine" in load_entries
    assert "SaveFormulaMetadata(formula.FormulaObject, renumbered)" in numbering

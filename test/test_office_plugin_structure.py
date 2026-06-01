# coding: utf-8

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "office_plugin"


def test_office_plugin_foundation_is_modular() -> None:
    assert (PLUGIN / "LaTeXSnipper.OfficePlugin.slnx").is_file()
    assert (PLUGIN / "Directory.Build.props").is_file()
    assert (PLUGIN / "NuGet.config").is_file()
    assert (PLUGIN / "README.md").is_file()

    projects = {
        "LaTeXSnipper.OfficePlugin.Abstractions": ("FormulaMetadata.cs", "OfficeCommandTimeouts.cs"),
        "LaTeXSnipper.OfficePlugin.Bridge": ("BridgeClient.cs", "BridgeOptions.cs", "BridgeConfiguration.cs"),
        "LaTeXSnipper.OfficePlugin.Rendering": ("FormulaRenderPipeline.cs", "RendererNotRegisteredException.cs"),
        "LaTeXSnipper.OfficePlugin.Editor": ("FormulaEditorSession.cs",),
    }

    for project, expected_files in projects.items():
        project_root = PLUGIN / "src" / project
        project_file = project_root / f"{project}.csproj"
        project_text = project_file.read_text(encoding="utf-8")
        assert project_file.is_file()
        assert "<TargetFrameworks>net48;net9.0</TargetFrameworks>" in project_text
        assert "<PackageReference" not in project_text
        for filename in expected_files:
            assert (project_root / filename).is_file()


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
    assert (host_root / "BridgeConversionParser.cs").is_file()
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
    assert (host_root / "MathLiveFormulaEditor.cs").is_file()
    assert (host_root / "MathLiveFormulaEditorForm.cs").is_file()
    assert (host_root / "FormulaEditorAcceptedEventArgs.cs").is_file()
    assert (host_root / "EditorAssets" / "editor.html").is_file()
    assert (host_root / "EditorAssets" / "taskpane.html").is_file()
    assert (host_root / "EditorAssets" / "taskpane.css").is_file()
    assert (host_root / "EditorAssets" / "taskpane.js").is_file()
    assert (host_root / "EditorAssets" / "help.html").is_file()
    factory = (host_root / "WordAddInFactory.cs").read_text(encoding="utf-8")
    bridge_client = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Bridge" / "BridgeClient.cs").read_text(encoding="utf-8")
    assert "http://127.0.0.1:28765/" in factory
    assert "LATEXSNIPPER_OFFICE_BRIDGE_TOKEN" in factory
    assert "ConfigAsync" in bridge_client
    assert "EnsureConfiguredAsync" in bridge_client
    assert "https://localhost:8765/" not in factory

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
    adapter = (host_root / "DynamicWordApplicationAdapter.cs").read_text(encoding="utf-8")
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
    assert "latexsnipper-eqm-" in metadata_store
    assert "LaTeXSnipper.Equation." in metadata_store
    assert "TryLoadBackup" in metadata_store
    assert "LoadSelectedFormulaAsync" in adapter
    assert "UpdateFormulaAsync" in adapter
    assert "DeleteSelectedFormulaAsync" in adapter
    assert "RenumberAutomaticFormulasAsync" in adapter
    assert "ReplaceNumberControlText" in adapter
    assert "FindSelectedFormulas" in adapter
    assert "AddSelectedFormulasOverlappingRange" in adapter
    assert "RangesOverlap" in adapter
    assert "DeleteFormula" in adapter
    assert "CountAutoNumberedFormulasAsync" not in adapter
    assert "LoadAllManagedFormulasAsync" not in adapter
    assert "MoveSelectionAfterInlineControl" in adapter
    assert "MoveSelectionAfterDisplayParagraph" in adapter
    assert "MoveSelectionAfterTable" in adapter
    assert "MoveSelectionAfterContentControl" in adapter
    assert "TryMoveSelectionOutsideFormula" in adapter
    assert "RangeTouchesManagedFormula" in adapter
    assert "Selection.SetRange" in adapter
    assert "ExecuteWithScreenUpdatingSuspended" in adapter
    assert "ResolveInsertionTargetRange" in adapter
    assert "TryResolveAfterEmptyParagraphFollowingNumberedTable" in adapter
    assert "TryGetNumberedTableFromPreviousParagraph" in adapter
    assert "TryGetNumberedTableBeforeParagraph" in adapter
    assert "CreateInsertionRangeAfterNumberedTable" not in adapter
    assert "IsInsideManagedContent" not in adapter
    assert "TypeParagraph" in adapter
    assert "CreateRangeAfterTable" not in adapter
    assert "CreateRecoveredFormulaMetadata" in adapter
    assert "GetContainingParagraphRange(control)" in adapter
    assert "NormalizeNumberedTable" in adapter
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
    assert "_displayMode = true" in taskpane
    assert "IWordFormulaOptionsProvider" in taskpane
    assert "NumberingMode.Manual" in taskpane
    assert "ConnectRequested" in taskpane
    assert "SetOcrActive" in taskpane
    assert "LoadSelectedRequested" not in taskpane
    assert "DeleteSelectedRequested" not in taskpane
    assert "previewField.readOnly" not in taskpane_js
    assert 'previewField.addEventListener("input"' in taskpane_js
    assert "resizePreview" in taskpane_js
    assert "ocrActive" in taskpane_js
    assert "cancelOcr" in taskpane_js
    taskpane_css = (host_root / "EditorAssets" / "taskpane.css").read_text(encoding="utf-8")
    assert "overflow-x: auto" in taskpane_css
    assert "width: max-content" in taskpane_css
    assert "min-height: 44px" in taskpane_css
    assert "CreateDefaultLatex" in controller
    assert "CancelScreenshotOcrAsync" in controller
    assert "BridgeRecognitionProgress.RunScreenshotOcrAsync" in controller
    assert "InsertInlineAsync" in controller
    assert "InsertDisplayAsync" in controller
    assert "InsertNumberedAsync" in controller
    assert "OpenEditorForInsertAsync" in controller
    assert "_pendingEditorInsertOptions" in controller
    assert "ShowSettingsAsync" in controller
    assert "UpdateDraftIfOpenAsync" in controller
    assert "OpenEditorAsync" not in controller
    assert "OfficePluginHelp.Open" in controller
    assert "RenumberAutomaticFormulasAsync" in controller
    assert "ResetDraftState" in controller
    assert "ApplyFormulaMetadata(metadata" not in controller
    assert "e^{i\\\\pi}+1=0" in controller
    omml_builder = (host_root / "WordOmmlDocumentBuilder.cs").read_text(encoding="utf-8")
    assert "BuildFlatOpcDocument(string omml, FormulaMetadata metadata" in omml_builder
    assert "NormalizeOmmlForInlineRun" in omml_builder
    assert "BuildEquationTag(equationId, metadata)" in omml_builder
    assert "w:vanish" not in omml_builder
    assert "WrapNumberContentControl" in omml_builder
    assert "WordNumberPlacement" in omml_builder
    assert "<w:r><w:t>" in omml_builder
    assert "</m:t></m:r></m:oMath>" not in omml_builder
    assert "icon.ico" in project_text
    assert "WordPluginIcon.Load" in (host_root / "MathLiveFormulaEditorForm.cs").read_text(encoding="utf-8")
    assert "WordPluginIcon.Load" in (host_root / "OfficePluginHelp.cs").read_text(encoding="utf-8")
    settings_window = (host_root / "WordSettingsWindow.cs").read_text(encoding="utf-8")
    assert "WebView2" in settings_window
    assert "settings.html" in settings_window
    assert "ShowDialog" not in settings_window
    assert "src\", \"assets\", \"icon.ico" not in icon
    assert "Path.Combine(baseDirectory, \"icon.ico\")" in icon
    assert "WinFormsFormulaEditor" not in factory
    assert "ShowDialog" not in (host_root / "MathLiveFormulaEditor.cs").read_text(encoding="utf-8")
    assert "MinimizeBox = false" not in (host_root / "MathLiveFormulaEditorForm.cs").read_text(encoding="utf-8")
    editor_html = (host_root / "EditorAssets" / "editor.html").read_text(encoding="utf-8")
    editor_js = (host_root / "EditorAssets" / "editor.js").read_text(encoding="utf-8")
    editor_css = (host_root / "EditorAssets" / "editor.css").read_text(encoding="utf-8")
    assert "displayMode" not in editor_html
    assert "display: true" in editor_js
    assert "event.ctrlKey" not in editor_js
    assert "symbol-grid" in editor_html
    assert "flex-direction: column" in editor_css
    assert "border: 1px solid transparent" in editor_css
    assert "calculus" in editor_js
    assert "linear" in editor_js
    assert "probability" in editor_js
    assert editor_js.count("matrix:vmatrix") == 1

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
    assert "Ctrl" in settings_html
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
    assert "..\\WordAddIn\\LaTeXSnipper.OfficePlugin.WordAddIn.csproj" in project_text
    assert "CreateRibbonExtensibilityObject" in this_addin
    assert "CustomTaskPanes.Add" in this_addin
    assert "statusTaskPane.Width = 480" in this_addin
    assert "VisibleWordStatusSink" in this_addin
    assert "WordAddInFactory.CreateController(Application, visibleStatusSink, statusPaneControl)" in this_addin
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

    register_script = PLUGIN / "tools" / "Register-WordVstoAddIn.ps1"
    smoke_script = PLUGIN / "tools" / "Test-WordVstoAddIn.ps1"
    shared_registration = PLUGIN / "tools" / "OfficeVstoRegistration.ps1"
    register_text = register_script.read_text(encoding="utf-8")
    smoke_text = smoke_script.read_text(encoding="utf-8")
    shared_registration_text = shared_registration.read_text(encoding="utf-8")
    assert register_script.is_file()
    assert smoke_script.is_file()
    assert shared_registration.is_file()
    assert "Invoke-OfficeVstoRegistration" in register_text
    assert "RegisterOfficeAddin" in shared_registration_text
    assert "TrustedPublisher" in shared_registration_text
    assert "CommandLineSafe" in shared_registration_text
    assert "VSTOInstaller.exe" in shared_registration_text
    assert "COMAddIns" in smoke_text


def test_office_plugin_hosts_are_explicit_scaffolds() -> None:
    for host in ("WordAddIn", "WordVstoAddIn", "PowerPointAddIn", "OleFormulaObject"):
        readme = PLUGIN / "hosts" / host / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert readme.is_file()
        assert "Responsibilities" in text or "VSTO shell" in text

    ole_text = (PLUGIN / "hosts" / "OleFormulaObject" / "README.md").read_text(encoding="utf-8")
    assert "double-click" in ole_text
    assert "MathJax" in ole_text
    assert "EMF/GDI" in ole_text
    assert "must not be inserted into Office as normal pictures" in ole_text


def test_office_plugin_build_outputs_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "office_plugin/**/bin/" in gitignore
    assert "office_plugin/**/obj/" in gitignore


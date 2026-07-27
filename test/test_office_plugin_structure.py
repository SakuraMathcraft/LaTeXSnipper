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
    editor_form = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "MathLiveFormulaEditorForm.cs"
    ).read_text(encoding="utf-8")

    assert 'const VISIBLE_MATH_SPACE = "\\\\,";' in shared_input
    assert '"addRowAfter"' in shared_input
    assert "\\\\begin{aligned}#@\\\\\\\\#?\\\\end{aligned}" in shared_input
    assert 'mathfield.mode === "latex"' in shared_input
    assert "luminance > 0.72" in shared_input
    assert 'mathfield.style.backgroundColor' in shared_input
    assert "function normalizeLatex" in shared_input
    assert '.replace(/\\\\bm(?=\\s*\\{)/g, "\\\\boldsymbol")' in shared_input
    assert "normalizeAlphabetLimitedFontCommands" not in shared_input
    assert "rewriteAlphabetLimitedContent" not in shared_input
    assert "translateMathAlphabetCharacter" not in shared_input
    assert "String.fromCodePoint" not in shared_input
    assert "normalizeLatex," in shared_input
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
    set_default_font_style = shared_input.split("function setDefaultFontStyle", 1)[1].split(
        "function setDefaultColor",
        1,
    )[0]
    assert 'mathfield.executeCommand("selectAll")' not in set_default_font_style
    assert "mathfield.selection = selection" not in set_default_font_style
    assert "const FONT_STYLE_MAP = Object.freeze" in shared_input
    for font_style, mathlive_style in {
        "RomanUpright": '{ variant: "normal", variantStyle: "up" }',
        "Bold": '{ variant: "main", variantStyle: "bold" }',
        "BoldUpright": '{ variant: "normal", variantStyle: "bold" }',
        "BoldItalic": '{ variant: "main", variantStyle: "bolditalic" }',
        "Italic": '{ variant: "main", variantStyle: "italic" }',
        "SansSerif": '{ variant: "sans-serif", variantStyle: "up" }',
        "SansSerifBold": '{ variant: "sans-serif", variantStyle: "bold" }',
        "SansSerifItalic": '{ variant: "sans-serif", variantStyle: "italic" }',
        "SansSerifBoldItalic": '{ variant: "sans-serif", variantStyle: "bolditalic" }',
        "Typewriter": '{ variant: "monospace", variantStyle: "up" }',
        "Calligraphic": '{ variant: "calligraphic", variantStyle: "up" }',
        "Script": '{ variant: "script", variantStyle: "up" }',
        "Fraktur": '{ variant: "fraktur", variantStyle: "up" }',
        "Blackboard": '{ variant: "double-struck", variantStyle: "up" }',
    }.items():
        assert f'{font_style}: {mathlive_style}' in shared_input
    resize_method = editor_form.split("private void OnResize", 1)[1].split(
        "private void OnFormClosing",
        1,
    )[0]
    cancel_method = editor_form.split("private void NotifyEditorCancelled", 1)[1].split(
        "private void Commit",
        1,
    )[0]
    assert "WindowState == FormWindowState.Minimized" in resize_method
    assert "NotifyEditorCancelled();" in resize_method
    assert "_currentSessionGeneration <= 0" in cancel_method
    assert "new FormulaEditorCancelledEventArgs(_currentSessionGeneration)" in cancel_method

    editor_js = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "editor.js"
    ).read_text(encoding="utf-8")

    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        editor_html = (assets / "editor.html").read_text(encoding="utf-8")
        editor_css = (assets / "editor.css").read_text(encoding="utf-8")
        taskpane_js = (assets / "taskpane.js").read_text(encoding="utf-8")

        assert "mathfield-input.js" in editor_html
        assert "https://latexsnipper-editor-shared.officeplugin.local/editor.js" in editor_html
        assert 'id="sourceResizeHandle"' in editor_html
        assert 'role="separator"' in editor_html
        assert "--source-pane-height: 118px" in editor_css
        assert "grid-template-rows: minmax(160px, 1fr) 7px var(--source-pane-height)" in editor_css
        assert not (assets / "editor.js").exists()
        assert "LaTeXSnipperMathfieldInput.configure(mathfield, accept)" in editor_js
        assert 'new URL("./vendor/fonts", import.meta.url).href' in editor_js
        assert 'new URL("./vendor/fonts", window.location.href).href' not in editor_js
        assert "LaTeXSnipperMathfieldInput.setDefaultFontStyle" not in editor_js
        assert "LaTeXSnipperMathfieldInput.normalizeLatex" in editor_js
        assert "normalizeLatex" not in taskpane_js
        assert 'from "https://latexsnipper-editor-shared.officeplugin.local/vendor/mathlive.min.mjs"' in taskpane_js
        assert 'from "./vendor/mathlive.min.mjs"' not in taskpane_js
        assert '"https://latexsnipper-editor-shared.officeplugin.local/vendor/fonts"' in taskpane_js
        assert 'new URL("./vendor/fonts", window.location.href).href' not in taskpane_js
        assert "normalizeAlphabetLimitedFontCommands" not in taskpane_js
        assert "rewriteAlphabetLimitedContent" not in taskpane_js
        assert "translateMathAlphabetCharacter" not in taskpane_js
        assert "String.fromCodePoint" not in taskpane_js
        assert "scheduleSourceSync" in editor_js
        assert "sourceResizeHandle.setPointerCapture(event.pointerId)" in editor_js
        assert "new ResizeObserver(() => setSourcePaneHeight(sourcePaneHeight))" in editor_js
        assert 'event.key === "ArrowUp"' in editor_js
        assert 'event.key === "ArrowDown"' in editor_js
        assert "requestIdleCallback(syncSourceNow" in editor_js
        assert "cancelIdleCallback(sourceSyncHandle)" in editor_js
        assert "const latex = currentLatex();" in editor_js
        current_latex = editor_js.split("function currentLatex()", 1)[1].split(
            "function mathfieldLatex()",
            1,
        )[0]
        assert "return latexSource.value.trim();" in current_latex
        assert 'getValue("latex-expanded")' not in current_latex
        sync_source = editor_js.split("function syncSourceNow()", 1)[1].split(
            "function scheduleSourceSync()",
            1,
        )[0]
        assert "latexSource.value = mathfieldLatex();" in sync_source
        assert "sourceAuthoritative = true;" in sync_source
        assert "function cancelSourceSync()" in editor_js
        set_latex = editor_js.split("function setLatex(latex)", 1)[1].split(
            "function isMathMlSource",
            1,
        )[0]
        assert "cancelSourceSync();" in set_latex
        assert "latexSource.value = source;" in set_latex
        assert "syncSourceNow();" not in set_latex
        accept_method = editor_js.split("function accept()", 1)[1].split(
            "function hideVirtualKeyboard()",
            1,
        )[0]
        assert "if (!sourceAuthoritative) {" in accept_method
        assert "syncSourceNow();" in accept_method
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

    editor_js = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "editor.js"
    ).read_text(encoding="utf-8")

    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        editor_html = (assets / "editor.html").read_text(encoding="utf-8")

        assert "matrix-templates.js" in editor_html
        assert "LaTeXSnipperMatrixTemplates.insert(mathfield, env, rows, cols)" in editor_js
        assert "LaTeXSnipperMathfieldInput.insertTemplate(mathfield, latex)" in editor_js
        assert 'button.addEventListener("pointerdown", event => event.preventDefault())' in editor_js
        assert '["identity", "diagonal"].includes(env)' in editor_js
        assert '" square"' in editor_js
        editor_css = (assets / "editor.css").read_text(encoding="utf-8")
        assert ".matrix-row.square" in editor_css


def test_office_settings_expose_complete_formula_font_styles() -> None:
    expected_styles = (
        "TeX",
        "RomanUpright",
        "Bold",
        "BoldUpright",
        "BoldItalic",
        "Italic",
        "SansSerif",
        "SansSerifBold",
        "SansSerifItalic",
        "SansSerifBoldItalic",
        "Typewriter",
        "Calligraphic",
        "Script",
        "Fraktur",
        "Blackboard",
    )
    for host_name in ("WordAddIn", "PowerPointAddIn"):
        assets = PLUGIN / "hosts" / host_name / "EditorAssets"
        settings_html = (assets / "settings.html").read_text(encoding="utf-8")
        settings_js = (assets / "settings.js").read_text(encoding="utf-8")

        assert "const FONT_STYLE_VALUES = Object.freeze" in settings_js
        assert "FONT_STYLE_VALUES.includes(payload?.formulaFontStyle)" in settings_js
        for style in expected_styles:
            assert f'<option value="{style}"' in settings_html
            assert f'"{style}"' in settings_js

    word_settings = (PLUGIN / "hosts" / "WordAddIn" / "EditorAssets" / "settings.js").read_text(
        encoding="utf-8",
    )
    for label in (
        "粗体符号",
        "粗体字母",
        "粗斜体",
        "无衬线",
        "无衬线粗体",
        "无衬线斜体",
        "无衬线粗斜体",
        "等宽",
        "Bold Symbol",
        "Bold Upright",
        "Bold Italic",
        "Sans Serif",
        "Sans Serif Bold",
        "Sans Serif Italic",
        "Sans Serif Bold Italic",
        "Typewriter",
        "花体",
        "手写体",
        "哥特体",
        "黑板粗体",
        "Calligraphic",
        "Script",
        "Fraktur",
        "Blackboard Bold",
    ):
        assert label in word_settings


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
    assert "System32\\WindowsPowerShell\\v1.0\\Modules" in build_text
    assert "Microsoft.PowerShell.Security.psd1" in build_text
    assert "PKI\\PKI.psd1" in build_text
    assert "New-PSDrive -Name Cert -PSProvider Certificate" in build_text
    assert build_text.index('"MSBuild\\Current\\Bin\\MSBuild.exe"') < build_text.index(
        '"MSBuild\\Current\\Bin\\amd64\\MSBuild.exe"'
    )

    native_build_script = PLUGIN / "tools" / "Build-NativeOleHandler.ps1"
    native_build_text = native_build_script.read_text(encoding="utf-8")
    assert native_build_script.is_file()
    assert 'Where-Object { $_.Name -match "^v\\d+$" }' in native_build_text
    assert 'foreach ($platform in @("x64", "Win32"))' in native_build_text
    assert "/p:PlatformToolset=" in native_build_text

def test_ole_objects_are_registered_as_static_display_objects() -> None:
    setup_text = (PLUGIN / "installer" / "setup.iss").read_text(encoding="utf-8")
    native_text = (PLUGIN / "hosts" / "OleFormulaObjectNative" / "src" / "FormulaOleObject.cpp").read_text(encoding="utf-8")
    presentation_text = (PLUGIN / "hosts" / "OleFormulaObjectNative" / "src" / "Presentation.cpp").read_text(encoding="utf-8")
    payload_text = (PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Abstractions" / "OleFormulaPayloadJson.cs").read_text(encoding="utf-8")
    force_clean_text = (PLUGIN / "tools" / "ForceClean.ps1").read_text(encoding="utf-8")
    word_adapter_text = read_word_adapter_sources()

    assert 'Source: "..\\release\\InstallerAssets\\MathJax-3.2.2\\*"' in setup_text
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
    assert "return TRUE;" in native_text
    assert "IsSupportedFormulaPayload" in presentation_text
    assert '["documentId"]' not in payload_text
    assert '["equationId"]' not in payload_text
    assert "HKLM:\\Software\\Classes\\CLSID\\$OleFormulaClassId" in force_clean_text
    assert "HKLM:\\Software\\WOW6432Node\\Classes\\CLSID\\$OleFormulaClassId" in force_clean_text
    assert "shapeScale = Math.Max(0.05f, Math.Min(widthScale, heightScale));" in word_adapter_text
    assert "inlineShape.LockAspectRatio = true" in word_adapter_text
    assert "heightScale = originalHeight / (float)naturalHeight" in word_adapter_text
    add_ole_method = word_adapter_text.split("private dynamic AddOleInlineShapeAtRange", 1)[1].split("private dynamic ReplaceOleInlineShape", 1)[0]
    insert_method = word_adapter_text.split("public Task InsertOleFormulaObjectAsync", 1)[1].split("public Task UpdateOleFormulaObjectAsync", 1)[0]
    assert "SaveOleNaturalSize" not in add_ole_method
    assert "SaveOleNaturalSize" not in insert_method
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
    prepare_assets_text = (PLUGIN / "tools" / "Prepare-InstallerAssets.ps1").read_text(encoding="utf-8")
    checksum_text = (PLUGIN / "tools" / "Write-InstallerChecksum.ps1").read_text(encoding="utf-8")
    assert "Build-NativeOleHandler.ps1" in installer_build_text
    assert "Prepare-InstallerAssets.ps1" in installer_build_text
    assert "Write-InstallerChecksum.ps1" in installer_build_text
    for host in ("WordAddIn", "PowerPointAddIn"):
        status_pane = (PLUGIN / "hosts" / host / f"{host.removesuffix('AddIn')}StatusTaskPaneControl.cs").read_text(encoding="utf-8")
        resolver = (PLUGIN / "hosts" / host / "InstalledAssetResolver.cs").read_text(encoding="utf-8")
        project_text = (PLUGIN / "hosts" / host / f"LaTeXSnipper.OfficePlugin.{host}.csproj").read_text(encoding="utf-8")
        assert "latexsnipper-editor-shared.officeplugin.local" in status_pane
        assert "ResolveSharedAssetsRoot()" in status_pane
        assert "SetVirtualHostNameToFolderMapping(" in status_pane
        assert 'FindSharedAssetRoot("vendor\\\\mathlive.min.mjs")' in status_pane
        assert "FindSharedAssetRoot" in resolver
        assert 'Path.Combine(parentDirectory, "EditorSharedAssets")' in resolver
        assert "EditorAssets\\vendor" not in project_text
        assert "src\\assets\\mathlive\\vendor" not in project_text
    assert "OutputDir=..\\release" in setup_text
    assert 'DestDir: "{app}\\EditorSharedAssets"' in setup_text
    assert 'DestDir: "{app}\\Word\\EditorSharedAssets"' not in setup_text
    assert 'DestDir: "{app}\\PowerPoint\\EditorSharedAssets"' not in setup_text
    assert "compute-engine.min.esm.js" in prepare_assets_text
    assert "compute-engine.LICENSE.txt" in prepare_assets_text
    assert "WindowsPowerShell\\v1.0\\powershell.exe" in installer_build_text
    assert "Get-FileHash" not in checksum_text
    assert "[System.Security.Cryptography.SHA256]::Create()" in checksum_text
    assert "call powershell " not in installer_build_text
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


def test_office_formula_metadata_com_regression_script_is_available() -> None:
    script = PLUGIN / "tools" / "Test-FormulaMetadataCom.ps1"
    text = script.read_text(encoding="utf-8")

    assert "Test-WordFormulaMetadata" in text
    assert "Test-PowerPointFormulaMetadata" in text
    assert "Word OMML ContentControl metadata save/update/delete-undo OK" in text
    assert "Word OLE AlternativeText metadata natural-size/delete-undo OK" in text
    assert "PowerPoint shape metadata long-latex/update/duplicate/delete-undo OK" in text
    assert "WordFormulaMetadataStore" in text
    assert "PowerPointFormulaMetadataStore" in text


def test_office_plugin_help_describes_current_paths() -> None:
    for host in ("WordAddIn", "PowerPointAddIn"):
        help_html = (PLUGIN / "hosts" / host / "EditorAssets" / "help.html").read_text(encoding="utf-8")
        assert "EMF+Dual vector preview" in help_html
        assert "PNG image insertion" in help_html
        assert "side pane is not an update entry point" in help_html
        assert "Press Enter in the MathLive field to start a new math row" in help_html
        assert "Press Shift+Enter to insert or update the formula" in help_html
        assert "Space inserts a mathematical thin space" in help_html
        assert "Esc does not close the editor" in help_html
        assert "Editor submissions are serialized with Office commands" in help_html
        assert "Numbered formulas center the formula and place the number" in help_html
        assert "Fonts and Macro Commands" in help_html
        assert "common fonts used in academic writing" in help_html
        assert "Default fonts are saved as the corresponding LaTeX font commands" in help_html
        assert "Default font option; source command" in help_html
        assert "\\mathbb{R},\\mathbb{N}" in help_html
        assert "\\boldsymbol{\\alpha+\\nabla f}" in help_html
        assert "\\qty(\\frac{a}{b})" in help_html
        assert "\\braket{\\psi|\\phi}" in help_html
        assert "\\begin{cases}x^2" in help_html
        assert "\\cancel{x}" in help_html
        assert "\\prescript{a}{b}{X}" in help_html
        assert "managed formulas in the current selection" in help_html
        assert "multi-selection runs in batches" in help_html
        assert "reports progress in the status pane" in help_html
        assert "selecting only the number text does not delete the formula" in help_html
        assert "Format All only restores manually resized formulas to natural size" in help_html
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
    open_method = editor.split("public Task OpenAsync", 1)[1].split("private MathLiveFormulaEditorForm GetOrCreateForm", 1)[0]
    assert "MathLiveFormulaEditorForm form = GetOrCreateForm();" in open_method
    assert "form.Configure(initialFormula, updateMode, sessionGeneration);" in open_method
    assert "DisposeForShutdown" in editor
    assert "_activeForm = null;" in editor
    assert "public Task WarmUpAsync()" in editor_form
    assert "_warmUpTask ??= InitializeAsync();" in editor_form
    assert "public void Configure(FormulaMetadata initialFormula, bool updateMode, long sessionGeneration)" in editor_form
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
    formula_font_style = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Abstractions"
        / "FormulaFontStyle.cs"
    ).read_text(encoding="utf-8")

    for package in (
        "action",
        "amscd",
        "bbox",
        "boldsymbol",
        "braket",
        "bussproofs",
        "cancel",
        "cases",
        "centernot",
        "color",
        "colortbl",
        "configmacros",
        "empheq",
        "enclose",
        "extpfeil",
        "gensymb",
        "html",
        "mathtools",
        "mhchem",
        "physics",
        "setoptions",
        "tagformat",
        "textcomp",
        "textmacros",
        "unicode",
        "upgreek",
        "verb",
    ):
        assert f"'[tex]/{package}'" in script_builder
        assert f"'{package}'" in script_builder
    assert "'[tex]/noerrors'" not in script_builder
    assert "'[tex]/noundefined'" not in script_builder
    assert "'[tex]/colorv2'" not in script_builder
    assert "'[tex]/require'" not in script_builder
    assert "preprocessTexSource" in script_builder
    assert "normalizeMathLiveLatex" not in script_builder
    assert ".replace(/\\\\bm" not in script_builder
    expected_font_styles = (
        "TeX",
        "RomanUpright",
        "Bold",
        "BoldUpright",
        "BoldItalic",
        "Italic",
        "SansSerif",
        "SansSerifBold",
        "SansSerifItalic",
        "SansSerifBoldItalic",
        "Typewriter",
        "Calligraphic",
        "Script",
        "Fraktur",
        "Blackboard",
    )
    for font_style in expected_font_styles:
        assert font_style in formula_font_style
    for font_style, command in {
        "RomanUpright": "\\\\mathrm",
        "Bold": "\\\\boldsymbol",
        "BoldUpright": "\\\\mathbf",
        "BoldItalic": "\\\\mathbfit",
        "Italic": "\\\\mathit",
        "SansSerif": "\\\\mathsf",
        "SansSerifBold": "\\\\mathbfsf",
        "SansSerifItalic": "\\\\mathsfit",
        "SansSerifBoldItalic": "\\\\mathbfsfit",
        "Typewriter": "\\\\mathtt",
        "Calligraphic": "\\\\mathcal",
        "Script": "\\\\mathscr",
        "Fraktur": "\\\\mathfrak",
        "Blackboard": "\\\\mathbb",
    }.items():
        assert f'FormulaFontStyle.{font_style} => "{command}{{" + latex + "}}"' in normalizer
    assert "NormalizeLatex(string latex)" in normalizer
    assert "HasFontStyleFormatting(string latex)" in normalizer
    assert "Regex.Replace(latex ?? string.Empty" in normalizer
    assert "NormalizeAlphabetLimitedFontCommands" not in normalizer
    assert "AlphabetLimitedFontStyleCommands" not in normalizer
    assert "TranslateMathAlphabetCharacter" not in normalizer
    assert "DoubleStruckUpper" not in normalizer
    assert "ScriptUpper" not in normalizer
    assert "FrakturUpper" not in normalizer
    assert "FromCodePoint" not in normalizer
    assert "ApplyAlphabetLimitedDefaultFontStyle" not in normalizer
    assert 'FormulaFontStyle.Bold => "\\\\boldsymbol{" + latex + "}"' in normalizer
    assert 'FormulaFontStyle.Bold => "\\\\bm{" + latex + "}"' not in normalizer
    for command in (
        "\\\\mathrm",
        "\\\\mathbf",
        "\\\\boldsymbol",
        "\\\\mathbfit",
        "\\\\mathit",
        "\\\\mathsf",
        "\\\\mathbfsf",
        "\\\\mathsfit",
        "\\\\mathbfsfit",
        "\\\\mathtt",
        "\\\\mathcal",
        "\\\\mathscr",
        "\\\\mathfrak",
        "\\\\mathbb",
    ):
        assert f'"{command}"' in normalizer
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
        assert "..\\..\\..\\src\\assets\\mathlive\\vendor\\**\\*" not in project
        assert "EditorAssets\\vendor" not in project
        assert "..\\..\\src\\LaTeXSnipper.OfficePlugin.Editor\\EditorAssets\\**\\*" in project
        assert "EditorSharedAssets\\%(RecursiveDir)%(Filename)%(Extension)" in project


def test_editor_does_not_load_formula_color_or_font_metadata() -> None:
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
    assert '["fontColor"]' not in editor_form
    assert '["fontStyle"]' not in editor_form
    assert "function setDefaultColor(mathfield, fontColor)" in shared_input
    assert "mathfield.style.color = color" in shared_input
    editor = (
        PLUGIN
        / "src"
        / "LaTeXSnipper.OfficePlugin.Editor"
        / "EditorAssets"
        / "editor.js"
    ).read_text(encoding="utf-8")
    assert "setDefaultColor(" not in editor


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
    assert 'StartsWith("<?xml"' not in word_controller
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


def test_powerpoint_edit_target_and_replacement_are_explicit() -> None:
    power_point_root = PLUGIN / "hosts" / "PowerPointAddIn"
    power_point_controller = (power_point_root / "PowerPointPluginController.cs").read_text(encoding="utf-8")
    power_point_adapter = (power_point_root / "DynamicPowerPointApplicationAdapter.cs").read_text(encoding="utf-8")

    assert "UpdateFormulaImageAsync" in power_point_controller
    assert "UpdateOleFormulaObjectAsync" in power_point_controller
    assert "FindFormulaShapeById(target.Presentation" in power_point_adapter
    assert "PowerPointFormulaEditTarget? _editorTarget" in power_point_controller
    assert "dynamic replacement = CreatePictureAt" in power_point_adapter
    assert "dynamic replacement = CreateOleObjectAt" in power_point_adapter
    assert "CommitReplacement(shape, replacement, oldImagePath)" in power_point_adapter
    commit_replacement = power_point_adapter.split("private static void CommitReplacement", 1)[1].split(
        "private static void TryDeleteShape",
        1,
    )[0]
    assert commit_replacement.index("original.Delete();") < commit_replacement.index("CleanupImageFilePath(originalImagePath)")
    assert "CleanupImageFile(replacement);" in commit_replacement
    assert "TryDeleteShape(replacement);" in commit_replacement


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
    controller = (host / "PowerPointPluginController.cs").read_text(encoding="utf-8")

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
    assert "BatchFormulaOperationSize = 5" in commands
    assert "PostBatchProgress(\"BatchConvertingStatus\"" in convert_method
    assert "_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId)" in convert_method
    assert "if (await ReplaceEntryAsync(entry, WithRenderEngine(entry.Metadata, target), entry.Scale, cancellationToken))" in convert_method
    assert "ConvertedWithSkippedStatus" in commands
    assert "EnsureUniqueShapeIdentities(shapes)" in adapter
    assert "CountFormulaShapesById" in adapter
    assert "public bool ContainsFormula(string equationId)" in adapter
    assert "WithNewIdentity(current, documentId)" in adapter
    assert "PowerPointFormulaMetadataStore.ApplyToShape(formulaShape, metadata, naturalWidth, naturalHeight)" in adapter
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
    assert "MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle" in commands
    format_method = commands.split("private async Task FormatAsync", 1)[1].split(
        "private async Task ReplaceEntryAsync",
        1,
    )[0]
    assert "PostBatchProgress(\"BatchFormattingStatus\"" in format_method
    assert "_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId)" in format_method
    assert "if (await ReplaceEntryAsync(entry, metadata, scale: 1, cancellationToken))" in format_method
    assert "FormattedWithSkippedStatus" in commands
    replace_method = commands.split("private async Task<bool> ReplaceEntryAsync", 1)[1].split(
        "private void PostChangedCount",
        1,
    )[0]
    assert replace_method.count("_powerPointAdapter.ContainsFormula(entry.Metadata.Identity.EquationId)") == 2
    assert "return false;" in replace_method
    assert "entry.Metadata.FontStyle" not in commands
    assert "entry.Metadata.FontColor" not in commands
    default_formatting = controller.split("private static string ApplyDefaultSourceFormatting", 1)[1].split(
        "private static FormulaMetadata WithRenderEngine",
        1,
    )[0]
    assert "MathLiveLatexStyleNormalizer.HasColorFormatting(formatted)" in default_formatting
    assert "MathLiveLatexStyleNormalizer.HasFontStyleFormatting(latex)" in default_formatting
    assert "string formatted = MathLiveLatexStyleNormalizer.HasFontStyleFormatting(latex)" in default_formatting
    assert 'return "\\\\color{" + fontColor + "}{" + formatted + "}";' in default_formatting
    assert "NoFormattingNeededStatus" in commands
    accept_editor_method = controller.split(
        "public async Task AcceptEditorFormulaAsync",
        1,
    )[1].split("private async Task ConvertAndInsertAsync", 1)[0]
    assert "_statusSink.SetCurrentFormula(" not in accept_editor_method
    assert "CompleteEditorSession(accepted.SessionGeneration, target)" in accept_editor_method
    assert "MathLiveLatexStyleNormalizer.NormalizeLatex(latex.Trim())" in controller
    assert "LoadFromShape" in metadata
    assert 'shape.AlternativeText = "LaTeXSnipper formula "' in metadata
    for tag in (
        "LatexChunkCountTag",
        "LatexByteLengthTag",
        "RenderEngineTag",
        "FontScaleTag",
    ):
        assert tag in metadata
    assert "FontColorTag" not in metadata
    assert "FontStyleTag" not in metadata
    assert "LoadFromAlternativeText" not in metadata
    assert "Encoding.UTF8.GetBytes" in metadata
    assert 'valueByte.ToString("X2"' in metadata
    assert "ReadEncodedText(shape)" in metadata
    assert "ReadRequiredEnumTag" in metadata
    assert "ReadEnumTag" not in metadata
    assert "metadata.FontColor" not in metadata
    assert "metadata.FontStyle" not in metadata
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


def test_word_loads_current_font_and_color_metadata() -> None:
    word_controller = (
        PLUGIN / "hosts" / "WordAddIn" / "WordPluginController.cs"
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
    assert "SwitchEditorTargetAsync(target, cancellationToken)" in word_load
    assert '["fontStyle"]' not in editor_form
    assert '["fontColor"]' not in editor_form
    assert "mathfield.__latexSnipperDefaultFontStyle = style" in shared_input
    assert "mathfield.applyStyle(style);" in shared_input


def test_word_formatting_skips_default_formulas_and_inline_conversion_removes_wrapper() -> None:
    host = PLUGIN / "hosts" / "WordAddIn"
    controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")
    commands = (host / "WordPluginController.DocumentCommands.cs").read_text(encoding="utf-8")
    adapter = read_word_adapter_sources()
    default_formatting = controller.split("internal static string ApplyDefaultSourceFormatting", 1)[1].split(
        "private static bool IsDisplay",
        1,
    )[0]
    assert "MathLiveLatexStyleNormalizer.HasColorFormatting(formatted)" in default_formatting
    assert "MathLiveLatexStyleNormalizer.HasFontStyleFormatting(latex)" in default_formatting
    assert "string formatted = MathLiveLatexStyleNormalizer.HasFontStyleFormatting(latex)" in default_formatting
    assert 'return "\\\\color{" + fontColor + "}{" + formatted + "}";' in default_formatting
    assert "NeedsFormatting(formula, settings)" in commands
    assert "_wordAdapter.HasCustomFormulaScale(metadata)" in commands
    assert "MathLiveLatexStyleNormalizer.ApplyFormattingFontStyle" in commands
    assert "metadata.FontStyle" not in commands
    assert "metadata.FontColor" not in commands
    assert "settings.FormulaFontStyle" in commands
    assert "settings.FormulaFontScale" in commands
    assert "PrepareRenderedFormulaAsync" in commands
    assert "ResetManagedEquationFormattingAsync(formatted" not in commands
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
    assert '"Cambria Math", "Segoe UI Symbol", "Microsoft YaHei", "SimSun", "Segoe UI"' in vector_renderer
    assert 'element.Attribute("data-variant")?.Value' in vector_renderer
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
    assert "includeChapter," in settings_js
    assert "includeSection," in settings_js
    assert "hideChapterBoundary," in settings_js
    assert "hideSectionBoundary," in settings_js
    assert "numberSeparator," in settings_js
    assert "percentToScale" in settings_js
    assert "resetToWhite" in settings_js
    adapter = read_word_adapter_sources()
    controller = (host / "WordPluginController.cs").read_text(encoding="utf-8")
    assert "WordPluginSettings.Load().UseSystemFormulaColor" not in adapter
    assert "backend == FormulaInsertionBackend.Ole || !settings.UseSystemFormulaColor" not in controller


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


def test_mathlive_editor_assets_are_shared_at_install_root() -> None:
    resolver = (
        PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "MathLiveAssetResolver.cs"
    ).read_text(encoding="utf-8")
    shared_assets = PLUGIN / "src" / "LaTeXSnipper.OfficePlugin.Editor" / "EditorAssets"
    editor_js = (shared_assets / "editor.js").read_text(encoding="utf-8")

    assert "FindCopiedAssetRoot(baseDirectory, copiedFolderName, assetFile)" in resolver
    assert "Directory.GetParent(current)?.FullName" in resolver
    assert (shared_assets / "symbol-library.js").is_file()
    assert (shared_assets / "matrix-templates.js").is_file()
    assert (shared_assets / "mathfield-input.js").is_file()
    assert (shared_assets / "editor.js").is_file()
    assert 'import { MathfieldElement } from "./vendor/mathlive.min.mjs";' in editor_js


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


def test_word_numbering_uses_seq_fields_and_bookmarks() -> None:
    lifecycle = (
        PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.FormulaLifecycle.cs"
    ).read_text(encoding="utf-8")
    numbering = (
        PLUGIN / "hosts" / "WordAddIn" / "WordEquationNumbering.cs"
    ).read_text(encoding="utf-8")
    omml_builder = (
        PLUGIN / "hosts" / "WordAddIn" / "WordOmmlDocumentBuilder.cs"
    ).read_text(encoding="utf-8")

    assert 'SequenceName = "LaTeXSnipperEquation"' in numbering
    assert "public const string SequenceFieldCode" not in numbering
    assert '" \\\\# \\"" + numberPicture + "\\""' in numbering
    assert "BuildNumberPicture(prefix, enclosure)" in numbering
    assert "QuoteNumberPictureLiteral(left) + \"0\" + QuoteNumberPictureLiteral(right)" in numbering
    assert "BuildNumberFormatSwitch" not in numbering
    assert "WordNumberFormat" not in numbering
    assert "InsertEquationNumberAtRange" in lifecycle
    assert "WordEquationNumbering.BuildSequenceFieldCode" in lifecycle
    assert "WordEquationNumbering.GetLeftEnclosure(enclosure)" in lifecycle
    assert "WordEquationNumbering.GetRightEnclosure(enclosure)" in lifecycle
    assert "BuildSequenceFieldCode(resetSequence, prefix, enclosure)" in lifecycle
    assert "BuildSequenceFieldCode(resetSequence, format" not in lifecycle
    left_numbered_ole = lifecycle.split(
        "if (placement == WordNumberPlacement.Left)",
        1,
    )[1].split("else", 1)[0]
    assert "InsertEquationNumberAtRange" not in left_numbered_ole
    assert 'InsertTextAtRange(cursor, "\\t");' in left_numbered_ole
    numbered_ole = lifecycle.split(
        "private dynamic InsertNumberedOleInlineShape(",
        1,
    )[1].split("private dynamic AddOleInlineShapeAtRange", 1)[0]
    assert "int leftNumberPosition = GetRangeStart(cursor);" in numbered_ole
    left_number_after_ole = numbered_ole.split(
        "dynamic inlineShape = AddOleInlineShapeAtRange(cursor, metadata, presentation);",
        1,
    )[1].split("else", 1)[0]
    assert "CreateDocumentRange(leftNumberPosition, leftNumberPosition)" in left_number_after_ole
    assert "addBookmark: false" in left_number_after_ole
    assert "AddOrReplaceEquationBookmark(metadata.Identity.EquationId, numberRange);" in numbered_ole
    assert "private dynamic ReplaceEquationNumberAtRange(" not in lifecycle
    prepare_number = lifecycle.split(
        "private bool TryPrepareEquationNumberField(",
        1,
    )[1].split("private void RefreshLaTeXSnipperSequenceFields", 1)[0]
    refresh_number = lifecycle.split(
        "private void RefreshLaTeXSnipperSequenceFields",
        1,
    )[1].split("private void UpdatePreparedEquationNumberRange", 1)[0]
    update_number = lifecycle.split(
        "private void UpdatePreparedEquationNumberRange",
        1,
    )[1].split("private Dictionary<string, object> BuildEquationSequenceFieldMap", 1)[0]
    assert "numberRange.Delete();" not in prepare_number
    assert "sequenceFields.TryGetValue(metadata.Identity.EquationId" in prepare_number
    assert "numberRange.Document.Fields" not in lifecycle
    assert "field.Code.Text = WordEquationNumbering.BuildSequenceFieldCode" in prepare_number
    assert "field.Update()" not in prepare_number
    assert "field.Update()" in refresh_number
    assert "dynamic updated = field.Result.Duplicate;" in update_number
    assert "AddOrReplaceEquationBookmark(metadata.Identity.EquationId, updated);" in update_number
    assert "return false;" in prepare_number
    assert "BuildEquationSequenceFieldMap(document, formulas)" in (PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.Numbering.cs").read_text(
        encoding="utf-8",
    )
    numbering = (PLUGIN / "hosts" / "WordAddIn" / "DynamicWordApplicationAdapter.Numbering.cs").read_text(
        encoding="utf-8",
    )
    assert "document.Fields.Update()" not in numbering
    assert "UpdateEquationReferenceFields(document)" in numbering
    assert '"REF " + WordEquationNumbering.BookmarkPrefix' in numbering
    assert "var preparedFields = new List<(NumberedFormulaEntry Formula, double FormulaHeight)>();" in numbering
    assert "preparedFields.Add((formula, formulaHeight));" in numbering
    assert "RefreshLaTeXSnipperSequenceFields(document);" in numbering
    assert "refreshedSequenceFields.TryGetValue(formula.EquationId" in numbering
    assert "UpdatePreparedEquationNumberRange(formula.Metadata, refreshedField, formulaHeight);" in numbering
    assert "dynamic fields = document.Fields;" in lifecycle.split(
        "private Dictionary<string, object> BuildEquationSequenceFieldMap",
        1,
    )[1].split("private bool TryFindEquationNumberRangeById", 1)[0]
    assert "new SequenceFieldEntry(" not in lifecycle
    assert "TryFindEquationNumberRangeById(formula.EquationId" in lifecycle
    assert "TryFindSequenceFieldInRange(" not in lifecycle
    assert "RangesTouchOrOverlap(" in lifecycle
    assert "leftStart <= rightEnd && rightStart <= leftEnd" in read_word_adapter_sources()
    assert "BuildRangeKey(" not in lifecycle
    auto_insert = lifecycle.split(
        "private dynamic InsertEquationNumberAtRange(",
        1,
    )[1].split("else", 1)[0]
    assert "InsertTextAtRange(range, WordEquationNumbering.GetLeftEnclosure(enclosure) + prefix)" not in auto_insert
    assert "InsertTextAtRange(range, WordEquationNumbering.GetRightEnclosure(enclosure))" not in auto_insert
    assert "AddOrReplaceEquationBookmark" in lifecycle
    assert "document.Bookmarks.Add(bookmarkName, range)" in lifecycle
    assert "FindEquationNumberRangeById" in lifecycle
    assert "ExpandEquationNumberRange" not in lifecycle
    assert "TryFindEnclosedEquationNumberBounds" not in lifecycle
    assert "ExpandUnenclosedEquationNumberRange" not in lifecycle
    assert "ContentControls.Add(WdContentControlRichText)" not in lifecycle.split(
        "private dynamic InsertEquationNumberAtRange",
        1,
    )[1].split("private double ReadManagedEquationFontSize", 1)[0]
    assert "<w:fldSimple" not in omml_builder
    assert "BuildEquationNumberRuns" in omml_builder
    assert "WordEquationNumberState? numberState" not in omml_builder
    assert "Automatic equation numbering requires a concrete Word number state." not in omml_builder
    assert "BuildAutomaticNumberField" not in omml_builder
    assert "<w:r><w:t>1</w:t></w:r>" not in omml_builder
    assert "metadata.NumberingMode == NumberingMode.Automatic" in omml_builder
    automatic_number_branch = omml_builder.split(
        "if (metadata.NumberingMode == NumberingMode.Automatic)",
        1,
    )[1].split("string numberBody", 1)[0]
    assert "return string.Empty;" in automatic_number_branch


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
    assert '<w15:appearance w15:val=\\"hidden\\"/>' not in builder
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
    assert "InsertManagedEquationNumber(" in insert_method
    assert "ReplaceParagraphWithNumberedFormula(" not in insert_method
    assert "ShowContentControlChrome((dynamic)equationControl)" in lifecycle
    insert_command = controller.split("private async Task InsertAndRenumberIfNeededAsync", 1)[1].split(
        "private Task<FormulaMetadata> CreateMetadataFromDraftAsync",
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

    assert "NumberingDocumentEntry" not in operations
    assert "IndexedFormulaObject" not in read_word_adapter_sources()
    assert "document.Fields.Update()" not in numbering
    assert "UpdateEquationReferenceFields(document)" in numbering
    assert "TryLoadAutomaticFormulaMetadata(" in numbering
    timeline_method = numbering.split("private List<NumberingTimelineEntry> LoadNumberingTimelineEntriesBeforePosition", 1)[1].split(
        "private static void UpdateEquationReferenceFields",
        1,
    )[0]
    assert "TryLoadAutomaticFormulaMetadata(control, equationId, RenderEngineKind.Omml" in timeline_method
    assert "TryLoadAutomaticFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg" in timeline_method
    assert "LoadFormulaMetadata(control, equationId, RenderEngineKind.Omml)" not in timeline_method
    assert "LoadFormulaMetadata(inlineShape, equationId, RenderEngineKind.MathJaxSvg)" not in timeline_method
    assert "skippedMetadata++;" in numbering
    assert "skippedNumbering++;" in numbering
    assert "new WordRenumberResult(count, skippedMetadata, skippedNumbering)" in numbering
    assert "WordEquationNumbering.BuildSequenceFieldCode" in read_word_adapter_sources()
    assert "document.InlineShapes" in numbering
    assert "LoadFormulaMetadataById(equationId)" not in numbering
    assert "SaveFormulaMetadata(formula.FormulaObject, renumbered)" not in numbering

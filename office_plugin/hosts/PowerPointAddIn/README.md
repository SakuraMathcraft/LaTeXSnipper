# PowerPointAddIn Host

This folder contains the reusable PowerPoint host workflow core. The VSTO shell in `hosts/PowerPointVstoAddIn` keeps Office startup and Ribbon plumbing thin, then delegates insertion commands to `PowerPointPluginController`.

Responsibilities:

- Register a persistent LaTeXSnipper Ribbon in PowerPoint.
- Insert compatibility formula images rendered from LaTeX through the shared Bridge conversion endpoint.
- Store LaTeXSnipper metadata on inserted PowerPoint shapes.
- Keep host startup, Ribbon callbacks, and PowerPoint automation separate from conversion and controller logic.
- Keep PowerPoint free of Word-only numbering commands.

Feature boundary:

- Formulas are inserted as high-DPI PNG images cropped to the formula bounds. The image renderer trims transparent padding before insertion so the slide object size matches the visible formula.
- PowerPoint has no inline/display distinction — all formulas are display images on slides. The Ribbon has a single "Insert Formula" button.
- Numbering is not supported for PowerPoint. Automatic numbering and Renumber All are out of scope.
- OLE object insertion should be added only after the Word OLE identity model is stable.

First implementation step:

Implemented first:

1. `LaTeXSnipper.OfficePlugin.PowerPointAddIn.csproj` builds the reusable PowerPoint host core.
2. `PowerPointPluginController` converts LaTeX to PNG through the shared Bridge client.
3. `DynamicPowerPointApplicationAdapter` inserts the rendered PNG into the active slide.
4. `PowerPointFormulaMetadataStore` writes durable metadata to PowerPoint shape tags.
5. `PowerPointStatusTaskPaneControl` is a WebView2-based task pane with MathLive formula editor, ported from the Word host.
6. `PowerPointRibbonXml` with placeholder-based localization and full Ribbon groups: Formula (Insert + Screenshot OCR), Edit (Load Selected + Delete Selected), Tools (Status Pane + Settings + Help).
7. `PowerPointRibbonCallbacks` with serial command execution and OCR cancellation support.
8. `IPowerPointApplicationAdapter` supports InsertFormulaImage, LoadSelectedFormula, and DeleteSelectedFormula.
9. `PowerPointVstoAddIn` VSTO shell creates the WebView2 task pane and delegates to the shared core.

Next implementation steps:

1. Add OLE object insertion only after the Word OLE object identity model is stable.
2. Keep improving load/update/delete behavior through the formula editor.

## Registration

PowerPoint registration is wired through `tools/Register-PowerPointVstoAddIn.ps1`
and the combined `tools/Register-OfficeVstoAddIns.ps1` installer entry point.
The reusable host core is loaded through the VSTO shell in
`hosts/PowerPointVstoAddIn`.

# WordAddIn Host

This folder contains the Word-side host core for the native VSTO add-in.

Responsibilities:

- Register a persistent LaTeXSnipper Ribbon in Word.
- Dispatch Ribbon commands to shared contracts in `src/`.
- Insert and update Word OMML formulas.
- Insert, load, update, delete, and renumber LaTeXSnipper OLE formula objects.
- Keep formula metadata attached to the Word object, not to transient UI state.

Current implementation:

- `Ribbon/WordRibbon.xml` defines the persistent LaTeXSnipper Ribbon tab.
- `WordRibbonCallbacks` exposes the Ribbon callback methods that the generated VSTO `ThisAddIn` layer should delegate to.
- `WordPluginController` owns the first workflow: open editor, call the Bridge for OMML, then insert editable Word OOXML.
- `WordOmmlDocumentBuilder` builds Flat OPC OOXML with LaTeXSnipper content-control tags.
- `DynamicWordApplicationAdapter` isolates Word COM automation behind a small adapter so core workflow tests do not need Office installed.
- `MathLiveFormulaEditor` hosts the offline MathLive editor assets in WebView2 and returns insert/update drafts to the Word workflow.

VSTO shell:

The thin VSTO project now lives in `hosts/WordVstoAddIn`. Keep VSTO-generated startup and registration details there; keep workflow code here.

Next implementation step:

1. Validate insert, load/update, and delete against a real Word document with the desktop Bridge running.
2. Add Word equation numbering and renumbering on top of the managed formula metadata.
3. Move the same editor/session contracts into PowerPoint image insertion.

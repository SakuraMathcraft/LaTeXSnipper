# Windows Native Office Plugin Target Architecture

`office_plugin` is the active LaTeXSnipper Office architecture. It targets Microsoft 365 Apps, Office 2016, Office 2019, Office 2021, and Office 2024 on Windows desktop. Release artifacts must distinguish 64-bit Office from 32-bit Office and may be produced as Inno Setup EXE or MSI installers.

## Product Goals

- Persistent native Ribbon in Word and PowerPoint.
- No web manifest, sideload catalog, tenant deployment requirement, or localhost HTTPS static site.
- Default insertion through LaTeXSnipper OLE formula objects in both Word and PowerPoint.
- User-selectable insertion backend in settings: OLE by default, with Word OMML and PowerPoint PNG image insertion available only as explicit alternatives.
- OLE formulas must be embedded in the document, clear when scaled, managed through Ribbon/editor commands, and self-contained after saving and reopening the Office file.
- The OLE path must not depend on the desktop Bridge for TeX conversion. Bridge remains for screenshot recognition, client connection, Word OMML, and PowerPoint PNG image insertion.
- Per-formula metadata is stored with the embedded object: LaTeX source, display mode, numbering mode, render options, object identity, schema version, and renderer version.

## Non-Negotiable OLE Rules

- OLE is the default insert and update backend for new formulas.
- The OLE object is a true Office embedded object, not a pasted bitmap, grouped shape, hidden task pane state, or VSTO-only wrapper.
- OLE rendering uses a vector-first MathJax pipeline, but SVG is only an intermediate renderer output. Office presentation must be an OLE object view, preferably EMF or direct GDI/vector drawing through OLE view interfaces.
- A formula must remain sharp under Office zoom, presentation scaling, printing, PDF export, and high-DPI displays.
- Office may still send OLE activation verbs while handling embedded objects. The native OLE handler treats those verbs as no-op display activation; editing is entered through the host Ribbon "load selected" command and the shared editor.
- Editing an OLE object must preserve the user's object scale and must not replace unrelated Office content.
- Formula source and metadata must travel with the document. Loading or editing must not require transient task pane state.
- Numbering state belongs to the formula object or the host-side document wrapper around it, never to the editor UI alone.
- Do not add fallback branches for historical broken formats. If an old experimental object format exists, migrate it through one explicit migration path or leave it unsupported with a clear message.

## Modules

| Layer | Responsibility |
|---|---|
| VSTO host shell | Word and PowerPoint startup, Ribbon registration, Office lifetime hooks |
| Host workflow core | Editor command handling, backend selection, insertion/update/delete workflows |
| OLE object handler | Native in-process COM/OLE handler, object persistence, no-op activation, redraw |
| MathJax renderer | LaTeX to intermediate SVG and metrics without requiring Bridge conversion |
| OLE presentation renderer | Intermediate vector output to Office-safe EMF/GDI presentation |
| Rendering pipeline | Engine-neutral render requests, metrics, vector payloads, presentation cache keys, timeout handling |
| Bridge client | Screenshot recognition, desktop-client connection, Word OMML, and PowerPoint PNG image insertion |
| Editor session | Formula editor state and command surface |
| Installer | VSTO/OLE registration, Office bitness handling, runtime checks, uninstall cleanup |

## Backend Selection

Insertion mode is a user setting shared by Word and PowerPoint where the host supports it:

| Backend | Default | Word | PowerPoint | Bridge required | Purpose |
|---|---:|---:|---:|---:|---|
| OLE MathJax | Yes | Yes | Yes | No | Durable editable formula object |
| Word OMML | No | Yes | No | Yes | Native Word compatibility path |
| PowerPoint PNG image | No | No | Yes | Yes | Explicit image insertion backend |

The UI must make OLE the normal path. Alternative backends are advanced compatibility settings, not separate primary workflows. Switching the default affects newly inserted formulas only; it must not rewrite existing objects unless the user explicitly converts selected formulas.

## OLE Object Model

The LaTeXSnipper formula object is implemented as a native in-process COM/OLE handler.

Required COM/OLE behavior:

- Register a stable `CLSID` and `ProgID`, for example `LaTeXSnipper.Formula`.
- Register `InprocServer32`, friendly display name, default icon, ProgID, and static display OLE metadata required by Office object insertion.
- Implement the OLE persistence interfaces needed for embedded object save and reopen.
- Implement activation verbs as no-op success returns. The host add-ins own editing through Ribbon load/update commands.
- Implement redraw so Office can request a fresh presentation after edit, zoom, print, export, or theme changes.
- Provide separate 32-bit and 64-bit native handler builds so both Office bitnesses can activate the object.

Stored object payload:

```text
{
  "schemaVersion": 1,
  "equationId": "...",
  "latex": "...",
  "displayMode": "Inline|Display",
  "numberingMode": "None|Automatic|Manual",
  "numberText": "...",
  "renderer": {
    "engine": "MathJax",
    "version": "...",
    "settings": { ... }
  },
  "layout": {
    "widthPoints": 0,
    "heightPoints": 0,
    "baselinePoints": 0
  }
}
```

The object may cache rendered output, but the cache is derived data. The LaTeX source and metadata are authoritative.

## MathJax Rendering And OLE Presentation

MathJax is the default TeX layout engine because it supports complex TeX syntax better than lightweight renderers. The renderer must run locally and must not require Bridge conversion.

MathJax SVG output is an internal vector intermediate representation. It is not the Office insertion format. The OLE object must expose itself to Word and PowerPoint as a real embedded object with an Office-compatible presentation view.

Rendering contract:

```text
input:  { latex, displayMode, targetDpi, theme, fontScale, rendererOptions }
output: { intermediateSvg, widthPoints, heightPoints, baselinePoints, warnings, rendererVersion }
```

Implementation rules:

- Use MathJax TeX input with SVG output as the layout and vector intermediate.
- Convert the intermediate vector output into an Office-safe OLE presentation. Enhanced Metafile is the preferred cached presentation for Office 2016 compatibility, printing, PDF export, and zooming.
- Implement OLE drawing so Office can request a presentation through the embedded object. `IViewObject::Draw`/GDI-compatible rendering and cached `CF_ENHMETAFILE` are the target shape, not SVG or PNG insertion.
- Raster caches may be used only as temporary preview caches when a UI preview requires them; they must be regenerated from vector output and must not be inserted into Office as formula content.
- Cache by normalized LaTeX, display mode, renderer options, theme, and renderer version.
- Put hard timeouts around rendering and Office insertion/update calls so a bad TeX expression or stuck Office automation call cannot freeze the document indefinitely.
- Return warnings for unsupported macros instead of silently inserting broken output.

MiKTeX is not the default rendering dependency. A TeX distribution can provide strong package compatibility, but it is large, slow to cold-start, hard to sandbox, and fragile across user machines. It may be added later as an explicit advanced renderer for users who need full TeX package support. The default OLE path remains MathJax to vector presentation because it is local, bundled, predictable, and does not require a separate TeX installation.

## Word Workflow

1. Ribbon is loaded by the VSTO shell.
2. The VSTO shell creates a native status task pane for progress, current formula context, and non-blocking errors.
3. Ribbon insert commands provide separate inline, display, and numbered formula entry points.
4. The controller reads the user's insertion backend setting. OLE is selected by default.
5. For OLE, the host creates a LaTeXSnipper OLE object with the formula metadata and inserts the embedded object at the current selection.
6. The OLE server renders LaTeX through MathJax, converts the result to an Office-safe vector presentation, and exposes that presentation to Word through the embedded object.
7. The host stores Word-specific wrapper metadata only when needed for selection, numbering, and document-wide renumbering.
8. Numbered formulas attach their number to the OLE formula through a clean Word wrapper, such as a borderless table or content controls. The number wrapper must not corrupt the embedded object.

Managed formula load and delete must resolve the selected LaTeXSnipper object first, then operate through the saved metadata. Loading an existing formula opens the editor in update mode, and confirming the editor updates the selected formula in place. If the user only changes numbering or wrapper settings, the workflow must not rerun TeX rendering.

## PowerPoint Workflow

PowerPoint uses the same OLE object backend by default. New PowerPoint formula insertion must not use pasted formula images as the primary implementation.

1. Ribbon is loaded by the VSTO shell.
2. The controller reads the user's insertion backend setting. OLE is selected by default.
3. For OLE, the host creates a LaTeXSnipper OLE object and inserts it as an embedded object on the current slide.
4. The OLE object owns source persistence, EMF/GDI presentation, and redraw. Editing is routed through Ribbon load/update commands.
5. PowerPoint shape metadata is used only to find and manage selected LaTeXSnipper objects.

PowerPoint document-wide automatic numbering remains out of scope unless the host can prove stable slide-order semantics. Manual numbering can be stored in the OLE object, but broad renumbering must not be presented as supported until the implementation is reliable.

## Bridge Contract

The desktop Bridge remains available at:

```text
http://127.0.0.1:28765/
```

The Bridge is used for screenshot recognition, client status, and explicit compatibility backends. It must not be required for the default OLE TeX rendering path.

The following environment variables are development overrides only:

```text
LATEXSNIPPER_OFFICE_BRIDGE_URL
LATEXSNIPPER_OFFICE_BRIDGE_TOKEN
```

Word OMML conversion uses:

```text
POST /convert/latex
payload: { latex, display: true, targets: ["omml"] }
result:  { latex, display, warnings, omml }
```

This endpoint is not part of the OLE object's required render path.

## Localization

Ribbon labels, tooltips, dialog buttons, settings, and user-facing errors must go through a host-local text provider. The first implementation uses current UI culture to return English or Chinese text. New commands should add text keys instead of hard-coded visible strings.

## Installer Requirements

- Detect installed Office bitness for VSTO registration.
- Install/register Word and PowerPoint VSTO plugins.
- Install/register the native LaTeXSnipper OLE formula object handler.
- Register OLE under both 32-bit and 64-bit COM views when needed so 32-bit and 64-bit Office can activate the handler.
- Keep OLE registration independent from the desktop LaTeXSnipper client registry keys.
- Check VSTO Runtime and WebView2 Runtime only when required by the selected host/editor implementation.
- Remove VSTO, OLE, shortcut, and temporary registration state during uninstall.
- Uninstall must not remove the desktop LaTeXSnipper client registration or user data.

## Pitfalls To Avoid

- Do not implement OLE by inserting a PNG and storing metadata beside it. That recreates the current PowerPoint limitation.
- Do not implement OLE by inserting SVG as a normal Office picture. SVG is only an internal MathJax output and is not reliable enough across older Office versions.
- Do not make Bridge conversion mandatory for OLE. Users must be able to insert and edit typed TeX formulas with the local OLE renderer.
- Do not put formula identity only in Word content controls or PowerPoint shape tags. The embedded object must carry its own identity.
- Do not replace an object during update if in-place update is possible. Replacement breaks selection, layout, and host metadata.
- Do not let Office zoom determine formula quality. Store source metadata and expose EMF/GDI vector presentation computed from renderer metrics.
- Do not let Word numbering tables modify the OLE object's visual bounds.
- Do not rely on a single Office bitness registration path. The installer must support both COM registry views.
- Do not expose PowerPoint automatic renumbering until slide order and multi-selection behavior are deterministic.

## Implementation Order

1. Define OLE metadata schema and rendering contract.
2. Build the MathJax SVG intermediate renderer with metrics, cache keys, and timeouts.
3. Build SVG-to-EMF or direct GDI/vector OLE presentation generation.
4. Build the out-of-proc COM/OLE local server skeleton and registration.
5. Insert, save, reopen, and redraw a simple embedded OLE formula in Word.
6. Add Ribbon-driven load/update through the shared LaTeXSnipper editor.
7. Add Word numbering wrappers around OLE formulas without rerendering for number-only changes.
8. Insert, save, reopen, and redraw OLE formulas in PowerPoint.
9. Add settings to switch between OLE and explicit compatibility backends.
10. Update installer registration and uninstall cleanup for 32-bit and 64-bit Office.
11. Keep Word OMML and PowerPoint PNG image paths isolated behind backend settings.

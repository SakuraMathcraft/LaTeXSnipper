# Word macOS Office.js Add-in MVP Design

## Summary

Build a new Word Office.js add-in for LaTeXSnipper in an isolated
`office_web_addin/` tree. The add-in targets Word for macOS first, while
remaining compatible with Word for Windows and Word for the web where Office.js
supports the required APIs. The existing Windows VSTO/COM/OLE plugin in
`office_plugin/` remains the primary native Windows integration and must not be
reworked for this effort.

The MVP focuses on the Word formula workflow: edit LaTeX, render a local formula
preview, insert a managed formula as an image, reload a selected managed formula,
replace it after editing, and use the LaTeXSnipper desktop Bridge for screenshot
OCR. Native OLE objects, Word OMML insertion, automatic numbering, and
cross-references are explicitly deferred because they require platform-specific
Office capabilities that are outside a safe Office.js MVP.

## Goals

- Provide a Word for macOS add-in based on Office.js, not VSTO, COM, or OLE.
- Preserve strict platform isolation: no new macOS Office.js code inside
  `office_plugin/`, and no changes that weaken the current Windows VSTO plugin.
- Give macOS users the main Windows Word plugin workflow: create, insert, reload,
  edit, replace, and delete LaTeXSnipper-managed formulas.
- Keep formula editing and rendering usable without the desktop Bridge when the
  user is entering LaTeX manually.
- Use the existing LaTeXSnipper desktop Bridge only for OCR and optional local
  desktop integration.
- Make the metadata model forward-compatible with later OMML, numbering, and
  richer Windows feature parity.
- Document distribution clearly for Windows, macOS, and Linux users.

## Non-Goals For MVP

- No VSTO, COM, OLE, ATL, registry registration, or native in-process Office
  handler on macOS.
- No Word OMML insertion in the MVP. OMML is a follow-up after cross-platform
  MathML-to-OMML conversion and Word Office.js replacement behavior are proven.
- No automatic equation numbering, chapter/section numbering, or cross-reference
  fields in the MVP.
- No PowerPoint support in the MVP. PowerPoint can share the same core later,
  but the first implementation is Word-only.
- No AppSource submission in the MVP. The MVP ships a sideloadable manifest and
  documents the path to formal deployment.

## Windows Feature Parity Scope

The MVP targets workflow parity with the Windows Word VSTO plugin, not binary or
implementation parity. Office.js cannot host the Windows OLE object handler or
load VSTO components on macOS, so parity is defined around what the user can do
from Word.

| Windows Word VSTO capability | MVP status | Notes |
| --- | --- | --- |
| Open LaTeXSnipper controls inside Word | In MVP | Implemented as an Office.js task pane instead of a VSTO ribbon/task pane. |
| Create a formula from LaTeX | In MVP | MathLive editor plus local MathJax rendering. |
| Insert a managed formula | In MVP | Inserted as a managed SVG or PNG image, not OLE or OMML. |
| Load selected formula for editing | In MVP | Uses image marker plus document-level metadata store. |
| Update selected formula | In MVP | Replaces the selected managed image while preserving identity. |
| Delete selected managed formula | In MVP | Removes the selected managed image and leaves metadata cleanup best-effort. |
| Screenshot OCR from Word | In MVP | Calls the LaTeXSnipper desktop Bridge when available. |
| Status and connection feedback | In MVP | Presented in the task pane. |
| Native OLE formula object | Deferred | Not possible through Office.js on macOS. |
| Native Word OMML formula insertion | Deferred | Requires cross-platform OMML generation and replacement validation. |
| Automatic numbering and references | Deferred | Requires a separate Word field/content-control design. |
| OLE/OMML conversion | Deferred | Depends on the deferred OLE and OMML work. |
| Restore natural size document-wide | Deferred | Can be built after image metadata and replacement are stable. |

This scope keeps the first macOS add-in useful while leaving a clear path toward
richer parity without weakening the platform boundary.

## Official Platform Constraints

Microsoft's Office Add-ins platform supports Office.js add-ins across Office on
the web, Windows, Mac, and iPad. COM and VSTO add-ins run only in Office on
Windows. Therefore, the macOS integration must be a web add-in loaded by Word,
not a port of the current VSTO add-in.

Mac development and early user testing use manifest sideloading. Production
distribution can later use AppSource or Microsoft 365 centralized deployment.
Linux has no Microsoft Word desktop app, so Linux support means Word for the web
in a browser.

## Proposed Directory Layout

```text
office_web_addin/
  README.md
  package.json
  tsconfig.json
  vite.config.ts
  manifest/
    word-dev.xml
    word-release.xml
  src/
    app/
      taskpane.html
      taskpane.ts
      taskpane.css
    bridge/
      bridgeClient.ts
      bridgeTypes.ts
    core/
      formulaMetadata.ts
      formulaRenderer.ts
      formulaStore.ts
      ids.ts
      result.ts
    office/
      officeErrors.ts
      officeHost.ts
      wordAdapter.ts
    assets/
      symbols/
  tests/
    unit/
```

The repository currently has no root JavaScript/TypeScript build system. The
Office.js add-in should therefore own its frontend toolchain inside
`office_web_addin/`. Vite and TypeScript are sufficient for the MVP and keep the
new web add-in isolated from the Python app and Windows Office plugin projects.

## Platform Isolation Invariants

- `office_plugin/` remains Windows-native and keeps its existing VSTO, COM, OLE,
  installer, and release model.
- `office_web_addin/` owns all Office.js manifests, TypeScript source, frontend
  assets, tests, and web packaging.
- Shared concepts may be copied or reimplemented only across explicit data
  contracts such as formula metadata JSON and Bridge HTTP endpoints.
- Shared desktop Bridge changes must remain backward-compatible with the current
  Windows VSTO Bridge client.
- Root project metadata should not be changed unless it is required to expose a
  top-level documentation or release command for the new add-in.

## Architecture

### Task Pane App

The task pane is the user-facing Word add-in surface. It contains:

- a MathLive-powered formula editor;
- a LaTeX source field for direct editing;
- a MathJax-rendered preview;
- insert, update, load selected, delete selected, and reset controls;
- OCR controls that call the desktop Bridge when available;
- a compact status area for host capability, Bridge connection, and errors.

The task pane should use macOS-friendly interaction patterns: persistent pane UI,
clear keyboard focus behavior, native-feeling command labels, and no modal-heavy
workflow for the common edit/insert path.

### Formula Renderer

The renderer converts normalized LaTeX to SVG for insertion and preview. The MVP
should render in the add-in frontend so manual formula insertion does not depend
on the desktop app being open. PNG export can be added if Word image coercion or
host behavior requires it, but SVG is the preferred insertion format because it
preserves crisp formula output.

Rendering output includes:

- SVG markup or base64 payload for Word insertion;
- natural width and height estimates;
- a render fingerprint for later replacement checks;
- user-facing render errors.

### Word Adapter

`wordAdapter.ts` is the only module that directly talks to Office.js Word APIs.
It exposes a small host boundary:

- `insertFormula(metadata, renderResult)`;
- `loadSelectedFormula()`;
- `replaceSelectedFormula(metadata, renderResult)`;
- `deleteSelectedFormula()`;
- `getHostCapabilities()`;
- `openSideloadDiagnostics()`.

The adapter is responsible for converting between Office.js selection APIs and
the add-in's formula model. Other modules should not import `Word` API types
directly unless they are test doubles.

### Formula Store

Word picture metadata is too small and fragile for full formula JSON, so the
MVP uses a two-layer model:

1. The inserted picture stores a short LaTeXSnipper marker such as
   `latexsnipper-eq-<equationId>` in available alt text/title fields.
2. The full formula payload is stored in a document-level store keyed by
   `equationId`.

The payload schema mirrors the durable parts of the Windows plugin metadata:

```json
{
  "schemaVersion": 1,
  "documentId": "string",
  "equationId": "string",
  "latex": "string",
  "displayMode": "inline|display",
  "renderKind": "svg",
  "fontColor": "#000000",
  "fontScale": 1,
  "naturalWidthPoints": 0,
  "naturalHeightPoints": 0,
  "createdAt": "iso-8601",
  "updatedAt": "iso-8601"
}
```

The preferred document-level store is Office document settings or custom XML,
depending on what proves reliable across Word for Mac, Word for Windows, and
Word for the web during implementation. If a host cannot store full metadata
reliably, the add-in may fall back to compact JSON in alt text, but this is a
compatibility fallback rather than the primary design.

### Bridge Client

The Bridge client calls the existing local LaTeXSnipper desktop Bridge for:

- health check;
- configuration or pairing status;
- screenshot OCR start;
- OCR status;
- OCR cancellation.

Manual formula editing and insertion must work without the Bridge. OCR controls
should be disabled or show a clear local-status error when the Bridge is not
available.

The existing Bridge binds to localhost and uses bearer-token authorization. To
support Office.js pages, the Bridge must later allow configured Office.js origins
while remaining localhost-only and preserving the current Windows VSTO behavior.

## User Workflows

### Insert New Formula

1. User opens the LaTeXSnipper task pane in Word.
2. User enters LaTeX in MathLive or the source field.
3. Add-in renders SVG preview locally.
4. User chooses inline or display style.
5. Add-in inserts an image at the Word selection.
6. Add-in writes marker metadata to the image and full metadata to the document
   store.

### Edit Existing Formula

1. User selects a LaTeXSnipper-managed formula image in Word.
2. User clicks load selected.
3. Add-in reads the image marker, loads full metadata, and populates the editor.
4. User edits the formula.
5. Add-in renders the replacement and replaces the selected image while
   preserving equation identity.

### OCR From Screenshot

1. User clicks OCR in the task pane.
2. Add-in checks Bridge availability and authorization.
3. Bridge triggers the desktop screenshot recognition workflow.
4. Recognized LaTeX is returned to the task pane editor.
5. User reviews and inserts or updates the formula.

## Distribution Model

### Windows

Windows keeps the existing native package:

- `OfficePluginSetup-<version>.exe` for the VSTO/COM/OLE plugin;
- full native feature set remains in `office_plugin/`.

The Office.js add-in can also run on Word for Windows as a cross-platform option,
but it is not intended to replace the native Windows plugin during the MVP.

### macOS

macOS uses the Office.js add-in:

- early builds ship a `word-dev.xml` or release manifest through GitHub Releases;
- users sideload the manifest into Word for Mac during MVP testing;
- OCR requires the LaTeXSnipper macOS desktop app with the Office Bridge enabled.

### Linux

Linux has no supported Microsoft Word desktop app. Linux users can use the add-in
only through Word for the web. Manual formula editing and insertion should work
where Word for the web supports the required Office.js APIs. OCR through a local
Linux desktop Bridge is best-effort and depends on browser localhost access,
CORS, and user security settings.

### Future Production Deployment

After the MVP is stable, distribution can move to:

- Microsoft AppSource for individual users;
- Microsoft 365 centralized deployment for organizations;
- a versioned GitHub Release manifest for sideload users.

## Error Handling

The add-in should classify errors into:

- host capability errors, such as unsupported Word API or image insertion;
- selection errors, such as no selected managed formula;
- render errors, such as invalid LaTeX or MathJax failure;
- metadata errors, such as missing document payload for a selected marker;
- Bridge errors, such as unavailable Bridge, unauthorized token, OCR failure, or
  cancellation.

Errors should appear in the task pane status area with enough detail to guide
recovery, while technical details remain available in the browser console during
development.

## Testing Strategy

Unit tests should cover:

- metadata serialization and migration;
- equation ID generation and marker parsing;
- render input normalization;
- Bridge response parsing and error mapping;
- Word adapter behavior through Office.js test doubles.

Manual verification for MVP must cover:

- Word for Mac sideload loads the task pane;
- a new formula can be inserted at the cursor;
- a selected managed formula can be loaded and replaced;
- manual insertion works when the desktop Bridge is not running;
- OCR button reports a clear unavailable state when Bridge is off;
- OCR fills the editor when Bridge is on and authorized;
- existing Windows VSTO plugin files and build scripts remain untouched.

## Implementation Phases

### Phase 1: Scaffold And Host Load

Create `office_web_addin/`, manifest files, Vite/TypeScript build, task pane
shell, Office initialization, and Word sideload documentation.

### Phase 2: Formula Editing And Rendering

Add MathLive editing, LaTeX source synchronization, MathJax SVG rendering,
preview, and render error handling.

### Phase 3: Word Insertion And Metadata

Implement image insertion, formula metadata schema, document-level storage,
marker parsing, load selected, replace selected, and delete selected.

### Phase 4: Bridge OCR

Add Bridge client, localhost health checks, OCR start/status/cancel, and the
minimal compatible Bridge CORS/auth changes needed for Office.js.

### Phase 5: Packaging And Verification

Document Windows/macOS/Linux usage, add build/test scripts, verify Word for Mac
sideload behavior, and confirm `office_plugin/` remains isolated.

## Open Technical Decisions

- Exact Office.js metadata store: document settings versus custom XML should be
  chosen during implementation based on reliability in Word for Mac and Word for
  the web.
- Exact insertion payload: SVG should be attempted first; PNG fallback should be
  added if required by Word host behavior.
- Bridge pairing UX: the MVP may start with manual token/config discovery, but a
  smoother pairing flow should be designed before public release.
- AppSource readiness: icon assets, privacy text, source hosting, CDN strategy,
  and manifest validation are outside MVP but should shape release manifests.

## Acceptance Criteria

- A new isolated `office_web_addin/` project exists for the Word Office.js add-in.
- The add-in can be sideloaded into Word for macOS from a manifest.
- The task pane loads and initializes Office.js in Word.
- Users can enter LaTeX, preview it, and insert a managed formula image.
- Users can select a managed formula, load its LaTeX metadata, edit it, and
  replace the formula.
- Manual formula editing and insertion work without the LaTeXSnipper desktop app.
- OCR integration works through the local Bridge when the desktop app is running
  and authorized.
- Unsupported Bridge or host states are reported in the task pane without
  crashing.
- `office_plugin/` remains Windows-specific and is not required for the new
  macOS Office.js add-in.
- Documentation explains Windows, macOS, and Linux usage and distribution.

# Office Add-in Design

## Purpose

The Office add-in is planned as a separately installed companion for LaTeXSnipper. Its goal is to provide an AxMath-like equation editing and insertion experience in Word and PowerPoint, while reusing LaTeXSnipper's recognition, preview, conversion, and model infrastructure through a small local bridge.

The add-in must not become a second OCR runtime. Office hosts should handle editing, insertion, numbering, document integration, Office-version adaptation, and user onboarding. The desktop application remains responsible for screenshot capture, MathCraft OCR, external-model OCR, model downloads, dependency management, and LaTeX conversion.

The desktop application's visible UI should remain mostly unchanged. The only planned main-window/settings change is a single Office integration enablement control placed next to startup behavior settings. Installation, compatibility checks, manifest registration, certificates, and Office-specific troubleshooting belong to the add-in installer and add-in UI.

## Product Goals

1. Native-feeling formula editing inside Word and PowerPoint.
2. Import the next LaTeXSnipper global screenshot recognition result into the Office editor.
3. Fast insertion of LaTeX formulas into Word and PowerPoint.
4. Equation numbering suitable for academic writing and slides.
5. A clean module boundary that keeps Office-specific code isolated from the existing desktop UI.
6. A fallback path for Office hosts that cannot insert editable equations.
7. Independent add-in installation and rollback without changing the desktop application install.
8. Fault isolation: Office/WebView failures must not affect core LaTeXSnipper recognition.

## Non-Goals for the First Version

1. Replacing the desktop application.
2. Running MathCraft OCR inside the Office WebView.
3. Full Office Store publication workflow.
4. Cross-device sync of equation libraries.
5. Perfect bidirectional editing of every existing Office equation.
6. Native editable equations in PowerPoint if Office.js cannot support the required operation reliably.
7. Triggering a Word-window-only screenshot from the add-in.

## High-Level Architecture

```text
Word / PowerPoint Ribbon and lightweight task pane
  |
  | opens
  v
Office equation editor dialog
  |
  | HTTPS/HTTP loopback JSON API, localhost only
  v
LaTeXSnipper local Office bridge
  |
  +-- capture controller
  +-- MathCraft / external OCR model wrapper
  +-- formula conversion service
  +-- numbering/session service
  +-- diagnostics and version handshake
```

The add-in is a web application loaded by Office. It talks to the desktop app through a local loopback bridge such as `http://127.0.0.1:<port>`. The bridge is started by the desktop app only when Office integration is enabled.

This keeps heavyweight Python, ONNX Runtime, CUDA, MathCraft model cache, and screen-capture permissions out of the Office host.

The task pane is not the primary editing surface in the formal product. It should stay lightweight:

- Connection state.
- Open editor.
- Insert/update quick actions.
- Recent recognition status.
- Diagnostics and repair hints.

The primary formula editor should run in an Office dialog so it feels closer to AxMath/MathType: larger canvas, MathLive visual input, direct TeX source editing, templates, OCR import, and explicit Insert/Update actions.

The add-in package is installed separately from the desktop app. The installer owns:

- Word and PowerPoint manifest deployment.
- Windows and macOS Office sideload mechanisms.
- Local development certificate or production hosting configuration.
- Office desktop version checks.
- Office Web compatibility warnings.
- Repair and uninstall actions.

## Repository Layout

```text
office_addin/
  installer/
    windows/
    macos/
  package.json
  manifest.word.xml
  manifest.powerpoint.xml
  src/
    dialog/
      EditorDialog.ts
      editorDialog.html
    taskpane/
      App.ts
      TaskPaneStatus.ts
    office/
      host.ts
      wordInsert.ts
      powerpointInsert.ts
      numbering.ts
    services/
      bridgeClient.ts
      equationSession.ts
      latexNormalize.ts
    styles/
      taskpane.css

src/integration/office/
  __init__.py
  bridge_server.py
  bridge_auth.py
  bridge_contracts.py
  capture_actions.py
  conversion_service.py
  numbering_service.py
  recognition_bus.py
```

The `office_addin/` folder owns Office.js and task-pane code. The `src/integration/office/` package owns the desktop-side bridge. Existing desktop modules should not import from `office_addin/`.

The desktop app may include bridge code, but it should not include the Office add-in installer workflow inside the main UI.

## Desktop Bridge

The bridge should be implemented as a small localhost HTTP server.

Required properties:

- Bind only to `127.0.0.1`.
- Use a random port unless the user pins one in settings.
- Require a short-lived bearer token or session token.
- Return structured JSON errors.
- Never expose filesystem paths unless required for diagnostics.
- Disable the bridge by default unless Office integration is enabled.
- Keep bridge startup independent from Office add-in installation.

Recommended endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Version, protocol, feature flags, active desktop state. |
| `GET` | `/config` | Return the current bridge URL, protocol, feature flags, and token for the local add-in session. |
| `POST` | `/recognition/subscribe-next` | Register that an Office editor wants the next global recognition result. |
| `POST` | `/recognition/poll` | Poll for the pending recognition result until it is delivered or cancelled. |
| `POST` | `/recognition/cancel` | Cancel a pending Office recognition subscription. |
| `POST` | `/recognize/image` | Recognize an image supplied by the add-in, if this is needed later. |
| `POST` | `/convert/latex` | Convert LaTeX to OMML, MathML, SVG, PNG, and normalized LaTeX. |
| `POST` | `/equations/number/next` | Allocate the next equation number for the active document/session. |
| `POST` | `/equations/number/reset` | Reset numbering state for a document/session. |
| `POST` | `/diagnostics` | Collect bridge and Office integration diagnostics. |

Example conversion request:

```json
{
  "latex": "\\int_0^1 x^2\\,dx",
  "display": true,
  "targets": ["omml", "svg", "png"]
}
```

Example conversion response:

```json
{
  "ok": true,
  "result": {
    "latex": "\\int_0^1 x^2\\,dx",
    "omml": "<m:oMathPara>...</m:oMathPara>",
    "svg": "<svg ...>...</svg>",
    "png_base64": "...",
    "warnings": []
  }
}
```

## Conversion Strategy

The bridge should reuse the existing export layer:

- `exporting.formula_converters.latex_to_omml`
- `exporting.formula_converters.latex_to_mathml`
- `exporting.formula_converters.latex_to_svg_code`
- `exporting.formula_format_helpers.normalize_latex_for_export`

The Office bridge should wrap these functions in a dedicated `conversion_service.py` so Office behavior does not leak into the general export API.

Word insertion should create a LaTeXSnipper equation object, not a disposable OMML fragment:

1. LaTeX -> MathML.
2. MathML -> OMML.
3. Wrap OMML in a Word content control tagged with a LaTeXSnipper equation ID.
4. Insert through Word OOXML APIs.
5. Save the original LaTeX source in document settings keyed by that equation ID.
6. Save insertion mode, numbering metadata, and converter version next to the LaTeX source.
7. Do not return MathML from the OMML path. If real OMML cannot be produced, fail clearly.

PowerPoint insertion should start with visual formulas:

1. LaTeX -> SVG, with transparent or theme-aware background.
2. Insert the SVG or PNG as a picture.
3. Insert the equation number as a separate text box.
4. Grouping can be added later if Office.js support is reliable enough.

PowerPoint native editable equations should be treated as a later research item, not an MVP requirement.

The product target is not merely "insert visible math". The target is an AxMath-like object model: formulas carry editable LaTeX source and can be reopened in the add-in editor. Word uses content controls and document settings for this metadata foundation. PowerPoint needs a separate shape metadata strategy before it can be considered equivalent.

The editor must never depend on Word's native OMML editor as the source of truth. Word renders the native equation, while LaTeXSnipper owns the editable TeX source and regenerates OMML on update.

## Word Insert Model

Word should support three insertion modes:

| Mode | Output | Use case |
| --- | --- | --- |
| Inline | OMML inside the current paragraph | Small formulas in text. |
| Display | Centered OMML paragraph | Standalone equations. |
| Numbered display | Formula + right-aligned number | Academic writing. |

Numbered display should be implemented with a stable Word structure. Preferred layout:

```text
borderless 1-row table
  left cell: editable OMML equation, centered
  right cell: equation number, right aligned
```

This is less fragile than trying to maintain tab stops across different Word templates.

The insertion adapter must treat each numbered formula as an atomic object:

1. Create a row-level content control tagged `latexsnipper-equation-row:<id>`.
2. Create an equation content control tagged `latexsnipper-equation:<id>`.
3. Create a number content control tagged `latexsnipper-equation-number:<id>`.
4. Insert a paragraph boundary after each object so consecutive insertions cannot nest into the previous table/control.
5. Store the equation source and numbering metadata in document settings.

Renumbering must scan tagged LaTeXSnipper number controls and update only those controls. It must not rewrite the whole document body OOXML because that is fragile and can disturb unrelated content.

The add-in should store document-level numbering settings through Office document settings where possible:

```json
{
  "latexsnipper.equationNumbering": {
    "style": "plain",
    "next": 7,
    "prefix": "",
    "suffix": "",
    "chapter": ""
  }
}
```

## PowerPoint Insert Model

PowerPoint should support:

| Mode | Output |
| --- | --- |
| Inline-like | SVG/PNG placed at cursor or slide center. |
| Display | SVG/PNG centered on slide. |
| Numbered display | SVG/PNG formula plus number text box. |

PowerPoint layout should be slide-aware:

- Default formula width: 55%-70% of slide width.
- Default vertical placement: center or below selected object.
- Number text box aligned to the formula baseline or bottom-right edge.
- Keep insertion deterministic so repeated commands do not shift existing content unpredictably.

## Equation Editor

The primary editor should be an Office dialog independent from Word and PowerPoint insertion adapters. The task pane can open the dialog and display connection state, but it should not be the long-term main editing surface.

Core editor responsibilities:

- MathLive formula input with synchronized LaTeX text view.
- Live preview.
- Common symbol palette.
- Matrix/cases/aligned templates.
- Recognition result import.
- Recent formulas.
- Insert inline, insert display, insert numbered display.
- Update selected LaTeXSnipper equation.
- Import pending global OCR result from LaTeXSnipper.

The editor should not directly call Office APIs. It should emit a normalized `EquationDraft` object:

```ts
type EquationDraft = {
  latex: string;
  display: boolean;
  numbering: "none" | "auto" | "manual";
  manualNumber?: string;
};
```

Host-specific adapters handle insertion:

- `wordInsert.ts`
- `powerpointInsert.ts`

The MathLive editor should reuse the desktop workbench's interaction policy where possible:

- Arrow keys should route to MathLive navigation commands.
- The virtual keyboard should be explicitly toggleable.
- LaTeX should remain visible for direct editing and debugging.
- MathLive-specific behavior should stay in an editor adapter module rather than leaking into insertion adapters.

## Recognition Flow

The recognition flow should reuse the desktop application's global recognition path, but the Office add-in should not directly request a screenshot overlay tied to Word. The correct interaction is a subscription to the next global recognition result:

```text
Office add-in button
  -> bridgeClient.subscribeNextRecognition()
  -> add-in enters "waiting for next LaTeXSnipper recognition" state
  -> user presses the normal LaTeXSnipper global screenshot hotkey
  -> desktop app captures any screen region, not only the Word window
  -> selected image is recognized by the current preferred model
  -> desktop bridge publishes the result to the pending Office subscription
  -> add-in editor receives LaTeX and fills the draft
  -> user reviews and inserts/updates the Word formula
```

The add-in should not implement its own screenshot overlay in the first version. Office host screenshot permissions differ by platform and are less reliable than the existing desktop path.

The add-in may provide an Office-local shortcut for entering the waiting state, but the actual screenshot trigger remains the desktop application's global shortcut. This keeps recognition consistent across Word, PowerPoint, browsers, PDFs, and other applications.

Subscription rules:

- Only one pending Office recognition subscriber should be active per document/window.
- The user must be able to cancel waiting.
- A timeout should return the editor to idle state without inserting anything.
- Results should fill the editor only; auto-insert should be an explicit user preference, disabled by default.
- If LaTeXSnipper is not running or Office integration is disabled, the add-in should show a clear reconnect action.

## Numbering Rules

MVP numbering:

- Plain sequence: `(1)`, `(2)`, `(3)`.
- Manual override for a single insertion.
- Reset command.
- Renumber tagged LaTeXSnipper equations in document order.

Later numbering:

- Chapter-aware: `(2.1)`, `(2.2)`.
- Section-aware Word document scanning.
- Existing-number detection and renumbering.
- Cross-reference insertion.

The first version should avoid rewriting untagged user content. It may renumber only formulas created by LaTeXSnipper because those objects carry stable tags and metadata.

Renumbering requirements:

- Scan document order, not session insertion history.
- Ignore deleted formulas automatically because their content controls no longer exist.
- Update document settings so the next inserted auto number follows the current document maximum.
- Preserve manual-number formulas unless the user explicitly chooses to normalize them.

## Security Model

The Office bridge must be treated as a local privileged API because it can trigger screenshots and OCR.

Required controls:

1. Localhost-only binding.
2. Per-session token.
3. Explicit user setting to enable Office integration.
4. Clear status in settings: disabled, enabled, port, connected add-ins.
5. Reject requests without `Origin`/token validation when possible.
6. No unauthenticated recognition subscription or recognition polling endpoints.

The add-in should show a clear connection state:

- Desktop app not found.
- Bridge disabled.
- Token expired.
- Connected.
- Recognition running.

Connection behavior must be deterministic:

- `Connect` always calls `/config` first and refreshes the token.
- If `/config` succeeds, the add-in immediately retries `/health` with the refreshed token.
- Insert, update, convert, and recognition controls stay disabled until a token is available.
- A successful `/health` without a token must not be reported as fully connected.

## Desktop UI Boundary

The desktop application's settings should expose only one compact option near startup behavior:

```text
[ ] Enable Office add-in bridge
```

Optional secondary text can show:

```text
Office bridge: disabled / listening on 127.0.0.1:<port>
```

The main program should not include Office install wizards, manifest registration, certificate repair, or Office-version troubleshooting pages. Those belong to the add-in installer and task pane UI.

The desktop-side behavior is:

1. If disabled, no bridge server is started.
2. If enabled, start the localhost bridge after the application runtime is ready.
3. Generate or load a local token.
4. Allow the add-in to connect and request conversion/recognition.
5. Stop the bridge when the app exits.

The setting should not affect MathCraft OCR, screenshot recognition, external models, PDF recognition, or normal startup when Office integration is not used.

## Packaging

The first internal build can use sideloaded manifests.

Release packaging should keep Office assets separate from the desktop installers:

- `office_addin/dist/` for task-pane static assets.
- Manifest files generated per environment.
- The Office add-in should have its own installer or setup package.
- The desktop installer should not auto-install the add-in without user action.

The user-facing installer flow can later provide:

1. Detect Windows/macOS and Office desktop capabilities.
2. Install or register Word and PowerPoint manifests.
3. Validate task-pane hosting and local certificate requirements.
4. Explain Office Web limitations when localhost bridge access is unavailable.
5. Launch or prompt the desktop app to enable the Office bridge.
6. Provide repair and uninstall actions.

The add-in installer should be versioned independently. The bridge protocol version controls compatibility between the add-in and desktop app.

## Testing Plan

Unit tests:

- Bridge contract validation.
- Token validation.
- LaTeX normalization.
- Conversion service target selection.
- Numbering state transitions.

Integration tests:

- Bridge `/health`.
- `/convert/latex` returns OMML or SVG fallback.
- Recognition subscription and polling endpoints reject unauthenticated requests.
- Word adapter builds valid OOXML from conversion output.
- PowerPoint adapter builds deterministic SVG/PNG insertion commands.

Manual Office tests:

- Word desktop on Windows: inline formula, display formula, numbered display formula.
- PowerPoint desktop on Windows: SVG/PNG formula insertion and numbered display.
- Word desktop on macOS: inline formula, display formula, numbered display formula.
- PowerPoint desktop on macOS: SVG/PNG formula insertion and numbered display.
- Older Office desktop builds: show clear unsupported-version messaging.
- Word/PPT with desktop app closed: add-in shows bridge unavailable.
- Desktop bridge enabled but token invalid: add-in shows reconnect required.
- Recognition from screenshot: result appears in editor and inserts correctly.

Future cross-platform tests:

- Word for macOS.
- PowerPoint for macOS.
- Office Web, only if localhost bridge policy allows the workflow.

## Implementation Phases

### Phase 0: Design Branch

- Create the `office-addin` branch.
- Add this design document.
- Do not change desktop runtime behavior.

### Phase 1: Desktop Bridge Skeleton

- Add `src/integration/office/bridge_server.py`.
- Add `/health` and authenticated error handling.
- Keep the bridge disabled by default.
- Add tests for bridge lifecycle and token rejection.

### Phase 2: Conversion API

- Add `/convert/latex`.
- Reuse existing formula converters.
- Add explicit OMML/SVG/PNG target selection.
- Verify Word can consume the returned OOXML wrapper.

### Phase 3: Office Task Pane MVP

- Add Office.js task pane scaffold.
- Implement editor, preview, bridge status, and insert buttons.
- Implement Word insertion first.
- Keep PowerPoint insertion image-based.
- Add Word and PowerPoint Ribbon tabs with task-pane entry buttons.

This phase is a prototype only. Before the formal plugin release, the task pane should be reduced to status and entry points, and the editor should move to an Office dialog.

### Phase 4: Stable Connection and Word Object Model

- Fix `Connect` so it always refreshes `/config` and token state.
- Disable functional commands when bridge token is missing.
- Make development scripts print UTF-8 text reliably on Windows terminals.
- Insert numbered formulas as non-nesting tagged objects.
- Store LaTeX source, display mode, numbering mode, number value, and converter version per equation ID.
- Replace whole-body OOXML renumbering with tagged content-control updates.

### Phase 5: Dialog Editor

- Add an Office dialog for the formula editor.
- Keep MathLive visual editing and TeX source editing synchronized.
- Move insert/update/numbering choices into the dialog.
- Keep the task pane as connection status, editor launcher, and diagnostics.
- Support loading the selected LaTeXSnipper equation into the dialog.

### Phase 6: Recognition Subscription

- Add `/recognition/subscribe-next`, `/recognition/poll`, and `/recognition/cancel`.
- Route the next desktop global screenshot recognition result to the pending Office editor.
- Fill the editor but do not auto-insert by default.
- Add explicit waiting/cancel states.

### Phase 7: Numbering Polish

- Add document/session numbering state.
- Implement Word numbered display insertion and document-order renumbering.
- Implement PowerPoint numbered visual insertion.

### Phase 8: Polish

- Add formula templates and symbol palette.
- Add recent formulas.
- Add diagnostics.
- Add user manual section.
- Split the MathLive bundle if the production add-in payload needs to stay smaller.

### Phase 9: Independent Add-in Installer

- Add Windows add-in setup flow.
- Add macOS add-in setup flow.
- Add manifest repair and uninstall actions.
- Add Office version/protocol diagnostics.
- Keep installer logic out of the desktop main UI.

## Open Questions

1. Should Word editable equations require OMML success, or should SVG fallback be allowed silently?
2. Should numbering state live only in Office document settings, or also in LaTeXSnipper's config for recovery?
3. Should PowerPoint equations be inserted as SVG by default, with PNG fallback only when SVG fails?
4. Should the bridge support only the currently running desktop app, or should it auto-launch LaTeXSnipper from the add-in?
5. Should the Office add-in share the same MathJax/MathLive assets as the desktop app or carry its own pinned copy?
6. How should the add-in installer hand the local bridge token to the task pane without exposing it unnecessarily?
7. Should the bridge token be per-user persistent, per-session, or rotated when Office integration is disabled and re-enabled?

## References

- Microsoft Word Office Open XML add-in guidance: https://learn.microsoft.com/en-us/office/dev/add-ins/word/create-better-add-ins-for-word-with-office-open-xml
- Word JavaScript API reference: https://learn.microsoft.com/en-us/javascript/api/word
- PowerPoint JavaScript API reference: https://learn.microsoft.com/en-us/javascript/api/powerpoint
- Office add-in sideloading: https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing
- Office add-in document settings: https://learn.microsoft.com/en-us/office/dev/add-ins/develop/persisting-add-in-state-and-settings

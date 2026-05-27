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
6. Independent add-in installation and rollback without changing the desktop application install.
7. Fault isolation: Office/WebView failures must not affect core LaTeXSnipper recognition.

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
Word / PowerPoint Ribbon
  |
  +-- "Editor" button → Office Dialog (premium equation editor)
  |     |
  |     +-- MathLive visual input + LaTeX source (bidirectional sync)
  |     +-- SVG native rendering preview (via bridge /convert/latex)
  |     +-- Symbol palette + template insertion
  |     +-- Keyboard-driven editing (arrow keys, shortcuts)
  |     +-- messageParent() → task pane handles insertion
  |
  +-- Insert / Numbered / OCR / Renumber / Help buttons → Ribbon commands
  |     |
  |     +-- Compact MathLive editor in task pane (quick insert)
  |     +-- Connection status, bridge health
  |     +-- Load / Update / Renumber via ribbon (not sidebar buttons)
  |
  v
LaTeXSnipper local Office bridge (localhost HTTP, bearer token)
  |
  +-- POST /convert/latex    → OMML + SVG + MathML + PNG
  +-- POST /recognize/screenshot
  +-- POST /recognition/status
  +-- GET  /health, /config
  +-- capture controller (desktop-side screenshot hotkey)
  +-- MathCraft / external OCR model wrapper
  +-- formula conversion service (reuses exporting.formula_converters)
```

The add-in is a web application loaded by Office. It talks to the desktop app through a local loopback bridge (`http://127.0.0.1:<port>`). The bridge is started by the desktop app only when Office integration is enabled. Heavyweight Python, ONNX Runtime, CUDA, MathCraft model cache, and screen-capture permissions stay out of the Office host.

### Two-Editor Model

The add-in provides **two editing surfaces** that serve different workflows:

| Surface | Location | Purpose |
|---|---|---|
| **Task Pane Editor** | Office task pane (right sidebar, ~300px) | Quick formula entry, instant insert. Always visible. Suitable for simple formulas. |
| **Dialog Editor** | Office dialog window (resizable, ~800x600) | Premium editing experience. SVG live preview, symbol palette, templates. The MathType/AxMath equivalent. |

Both editors share a `MathLiveCore` module (MathLive initialization, virtual keyboard, LaTeX sync, arrow-key routing). Neither duplicates the other's logic.

The task pane is the **control hub**: it owns the bridge connection, manages document settings, and executes all Word/PPT insertion. The dialog editor is a **pure editing surface** — it emits `EquationDraft` messages via `Office.context.ui.messageParent()` and the task pane handles the rest.

### Installer

The add-in package is installed separately from the desktop app. The installer owns:

- Word and PowerPoint manifest deployment.
- Automatic localhost SSL certificate generation and system trust injection.
- Persistent Word trusted-add-in catalog registration (registry-based on Windows).
- Office desktop version checks.
- Office Web compatibility warnings.
- Repair and uninstall actions.

## Repository Layout

```text
office_addin/
  installer/
    windows/
      setup.ps1              # Auto-cert trust + registry catalog registration
      uninstall.ps1
    macos/
  package.json
  manifest.word.xml
  manifest.powerpoint.xml
  src/
    dialog/
      editorDialog.html      # Office dialog host page
      editorDialog.ts        # Dialog editor logic (MathLive + SVG preview + symbols)
      previewRender.ts       # SVG rendering pipeline (bridge /convert/latex → DOM)
    taskpane/
      App.ts                 # Task pane control hub (bridge, dialog opener, insertion)
      mathliveEditor.ts      # MathLiveCore — shared by task pane and dialog editors
    office/
      host.ts                # Office host detection and capability adapter
      wordInsert.ts           # Word OOXML insertion adapter
      powerpointInsert.ts     # PowerPoint image insertion adapter
      numbering.ts            # Equation numbering state machine
    services/
      bridgeClient.ts         # HTTP bridge client (convert, OCR, health, config)
      equationSession.ts      # Document settings persistence (source, numbering, token)
      latexNormalize.ts       # LaTeX normalization before bridge conversion
      ribbonCommands.ts       # Ribbon command queue via OfficeRuntime.storage
    styles/
      taskpane.css
      dialog.css

src/integration/office/
  __init__.py
  bridge_server.py            # Localhost HTTP server (GET /health, /config, POST routing)
  bridge_auth.py              # Bearer token generation and HMAC verification
  bridge_contracts.py         # JSON envelope, error types, body parsing
  conversion_service.py       # LaTeX → OMML/MathML/SVG/PNG via exporting.*
  dev_server.py               # CLI dev launcher
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

1. Create an equation content control tagged `latexsnipper-eq-<id>`.
2. Create a number content control tagged `latexsnipper-eqn-<id>` (unique tag per equation, not a shared generic tag).
3. Insert a paragraph boundary after each display equation so consecutive insertions cannot nest into the previous table.
4. Store the equation source and numbering metadata in document settings.

Renumbering scans body OOXML for all `latexsnipper-eqn-` prefixed tags, extracts the equation IDs, filters to auto-numbered equations only, then updates each via `ContentControl.insertText`. Manual-numbered equations are identified by checking the saved `EquationSourceRecord.numbering` field and are skipped.

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

### Two-Editor Model

The add-in provides two editing surfaces. They serve different workflows and coexist — the dialog is not a replacement for the task pane editor.

| | Task Pane Editor | Dialog Editor |
|---|---|---|
| **Location** | Office task pane (right sidebar, ~300px) | Office dialog window (resizable, default 820×620) |
| **Purpose** | Quick formula entry, instant insert | Premium editing: MathType/AxMath equivalent |
| **MathLive** | Yes (compact) | Yes (full canvas, center stage) |
| **LaTeX source** | Textarea below MathLive | Collapsible panel below MathLive |
| **Symbol palette** | No | Yes — persistent left panel (always visible) |
| **Templates** | No | Yes — persistent right panel (always visible) |
| **Keyboard driven** | Ctrl+Enter to insert | Full keyboard navigation + shortcuts |
| **Entry** | Always visible in task pane | Ribbon "Editor" button, task pane button, double-click equation |

### Shared Module: MathLiveCore

Both editors instantiate the same `MathLiveCore` class (defined in `src/taskpane/mathliveEditor.ts`). This module owns:

- `MathfieldElement` creation and configuration (fonts, keyboard policy, smartFence, defaultMode)
- Virtual keyboard lifecycle (`window.mathVirtualKeyboard` container, geometry changes, visibility toggle)
- Bidirectional LaTeX sync between the mathfield and a `<textarea>`
- Arrow-key routing to MathLive navigation commands (`moveToPreviousChar`, `moveToNextChar`, `moveUp`, `moveDown`)
- Theme token passthrough (`data-theme` attribute)

Neither editor duplicates MathLive initialization logic. The dialog and task pane each create one `MathLiveCore` instance bound to their own DOM host.

### Dialog Editor Layout

The dialog uses a three-column layout with persistent side panels, following the AxMath/MathType pattern where symbols and templates are always visible — no auto-collapsing dropdowns.

```
┌──────┬──────────────────────────────┬──────────┐
│Symbol│                              │Template  │
│Panel │   MathLive Editor            │Panel     │
│(left)│   (center, full height)      │(right)   │
│      │                              │          │
│ α β  │   MathLive renders formulas  │ Fraction │
│ γ δ  │   natively. No separate      │ Sup/Sub  │
│ π σ  │   SVG preview needed —       │ Integral │
│ ± ×  │   what you see is what       │ Matrix   │
│ ≤ ≥  │   MathLive displays.         │ Cases    │
│ → ⇒  │                              │ Aligned  │
├──────┴──────────────────────────────┴──────────┤
│  ▸ LaTeX Source (collapsible, defaults closed)  │
├────────────────────────────────────────────────┤
│  □ Display  □ Auto Number  [____]  [Insert]    │
└────────────────────────────────────────────────┘
```

The symbol panel (left, ~180px) and template panel (right, ~170px) are always visible. Clicking a symbol or template inserts the LaTeX directly at the MathLive cursor — no dropdown, no auto-collapse. MathLive occupies the full center area and handles all formula rendering.

### Native Formula Rendering (Inserted Equations)

MathLive handles all **editing-time** rendering — the dialog has no separate preview panel. The "native rendering" goal applies to **inserted equations in the Word document**:

1. Insert: LaTeX → Bridge `/convert/latex` → OMML → Word content control → Word renders the equation natively via its built-in OMML engine.
2. Double-click: Word detects selection on a `latexsnipper-equation:<id>` tagged content control → loads the stored LaTeX source → opens Dialog editor in Update mode → user edits → Update replaces the OMML in-place.

This gives the AxMath experience: equations look native in the document, and double-click reopens them for LaTeX-based editing. The original TeX source is always preserved in document settings.

### Symbol Palette and Templates

Reference the desktop workbench's `LaTeXSnippetPanel` (`src/editor/latex_snippet_panel.py`). The dialog editor provides **persistent side panels** (not dropdowns):

**Symbol Panel (left, 180px, always visible, scrollable):**
- Greek lowercase (α–ω, 20 symbols)
- Greek uppercase (Γ–Ω, 10 symbols)
- Operators (±, ×, ÷, ·, ∂, ∇, ∫, ∑, ∏, √, ∞, etc.)
- Relations (≤, ≥, ≠, ≈, ≡, ∈, ⊂, ⊆, etc.)
- Arrows & Misc (→, ⇒, ∀, ∃, ¬, ∧, ∨, etc.)

**Template Panel (right, 170px, always visible, scrollable):**

| Label | LaTeX Template |
|---|---|
| Fraction | `\frac{#?}{#?}` |
| Superscript | `x^{#?}` |
| Subscript | `x_{#?}` |
| Sub+Sup | `x_{#?}^{#?}` |
| Square root | `\sqrt{#?}` |
| Nth root | `\sqrt[#?]{#?}` |
| Sum | `\sum_{n=1}^{\infty} #?` |
| Product | `\prod_{n=1}^{\infty} #?` |
| Integral | `\int_{a}^{b} #?\,dx` |
| Matrix 2×2 | `\begin{bmatrix} #? & #? \\ #? & #? \end{bmatrix}` |
| Cases | `\begin{cases} #? & \text{if } #? \\ #? & \text{otherwise} \end{cases}` |
| Aligned | `\begin{aligned} #? &= #? \\ #? &= #? \end{aligned}` |

The `#?` markers are placeholder positions. When a template is inserted:
- If the user has a text selection, it fills the first `#?`.
- Remaining `#?` positions guide the user on where to type next.

### Double-Click to Edit

A LaTeXSnipper equation in Word is an OMML content control tagged with `latexsnipper-eq-{id}`. When the user selects such an equation:

1. Word fires `DocumentSelectionChanged`.
2. Task pane's selection tracker (`installSelectionTracking` in `App.ts`) inspects the selected or parent content control tag.
3. `equationIdFromTag()` extracts the equation ID from the `latexsnipper-eq-` or `latexsnipper-eqn-` tag.
4. If found → task pane reads the stored LaTeX source from document settings via `loadEquationSource(id)`.
5. Task pane opens the Dialog editor with the LaTeX pre-loaded and the equation ID attached.
6. Dialog editor enters "Update mode": the Insert button label changes to "Update", and the dialog header shows "Editing equation (X)".
7. On Update, the task pane rebuilds a complete tagged equation container. For numbered equations it inserts through a paragraph outside the old table, then removes the old table after insertion succeeds.

This flow provides the MathType-like "double click to re-edit" experience while keeping the editor dialog stateless (it doesn't need to know about Word APIs).

Future enhancement: detect double-click via `DocumentSelectionChanged` timing (two rapid selections on the same equation ID within ~500ms), or via a Word content control event if Office.js exposes one.

### Dialog ↔ Task Pane Communication

The dialog is a **pure editing surface**. It never calls Office insertion APIs directly. All communication goes through `Office.context.ui.messageParent()`.

**Task Pane → Dialog (on open):**
```ts
type DialogOpenArgs = {
  mode: "insert" | "update";
  latex?: string;          // Pre-fill editor (for update or "numbered" launch)
  equationId?: string;     // Required for update mode
  bridgeUrl: string;
  bridgeToken: string;
};
```

**Dialog → Task Pane (user actions):**
```ts
type DialogMessage =
  | { type: "insert"; draft: EquationDraft; equationId?: string }
  | { type: "ocr-start" }
  | { type: "ocr-cancel" }
  | { type: "close" };
```

Task pane handlers:
- `insert` → calls `insertEquationIntoWord(draft, conversion)` or `insertEquationIntoPowerPoint(draft, client)`. For update mode (`equationId` present), replaces the existing content control instead of inserting new.
- `ocr-start` → calls `bridgeClient.recognizeScreenshot()`, sends result back via `dialog.messageChild()`.
- `close` → invokes `event.completed()` so Office allows the dialog to close.

**Task Pane → Dialog (async responses):**
```ts
type TaskPaneMessage =
  | { type: "ocr-result"; latex: string }
  | { type: "ocr-error"; message: string };
```

### Keyboard-Driven Editing

The dialog editor should support keyboard-only workflows equivalent to typing raw LaTeX. Key bindings:

| Shortcut | Action |
|---|---|
| Arrow keys | Navigate within MathLive (routed to `moveToPreviousChar`, etc.) |
| `Ctrl+Enter` | Insert equation (inline or display based on current mode) |
| `Ctrl+S` | Toggle display mode |
| `Ctrl+Shift+S` | Start screenshot OCR |
| `Ctrl+K` | Toggle virtual keyboard |
| `Ctrl+L` | Jump focus to LaTeX source panel |
| `Escape` | Close dialog (prompt if unsaved changes) |

These shortcuts work within the Office dialog's DOM context. They do not conflict with Word's own shortcuts because the dialog runs in a separate WebView instance.

The desktop workbench's arrow-key routing implementation (`routeArrowKeyToMathfield` in `src/assets/mathlive/app.js`) is the direct reference for the Office dialog's keyboard behavior.

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
- Renumber auto-numbered equations in document order, preserving manual numbers.

Later numbering:

- Chapter-aware: `(2.1)`, `(2.2)`.
- Section-aware Word document scanning.
- Existing-number detection and renumbering.
- Cross-reference insertion.

The first version should avoid rewriting untagged user content. It may renumber only formulas created by LaTeXSnipper because those objects carry stable tags and metadata.

Renumbering requirements:

- Scan document order (based on body OOXML position), not session insertion history.
- Ignore deleted formulas automatically because their content controls no longer exist.
- Skip manually-numbered equations (`numbering: "manual"`) — only auto-numbered equations are renumbered.
- Each number CC carries a unique tag `latexsnipper-eqn-{uuid}`, allowing precise targeting via `getByTag` without body OOXML replacement.

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
- `/convert/latex` returns editable OMML for Word insertion.
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

### Phase 0: Design Branch ✅

- Create the `office-addin` branch.
- Add this design document.
- Do not change desktop runtime behavior.

### Phase 1: Desktop Bridge Skeleton ✅

- Add `src/integration/office/bridge_server.py`.
- Add `/health` and authenticated error handling.
- Keep the bridge disabled by default.
- Add tests for bridge lifecycle and token rejection.

### Phase 2: Conversion API ✅

- Add `/convert/latex`.
- Reuse existing formula converters.
- Add explicit OMML/SVG/PNG target selection.
- Verify Word can consume the returned OOXML wrapper.

### Phase 3: Office Task Pane MVP ✅

- Add Office.js task pane scaffold with MathLive editor.
- Implement bridge auto-discovery, health check, and token refresh.
- Implement Word OOXML insertion (inline, display, numbered display).
- Keep PowerPoint insertion image-based.
- Add Word and PowerPoint Ribbon tabs with command buttons.
- Ribbon commands communicate with task pane via `OfficeRuntime.storage` queue.

The task pane editor stays as the quick-insert surface. The dialog editor (Phase 5) is an additional premium editing surface — not a replacement.

### Phase 4: Stable Connection and Word Object Model ✅

- Fix `Connect` so it always refreshes `/config` and token state.
- Disable functional commands when bridge token is missing.
- Make development scripts print UTF-8 text reliably on Windows terminals.
- Insert numbered formulas as non-nesting tagged objects with content controls.
- Store LaTeX source, display mode, numbering mode, number value, and converter version per equation ID in document settings.
- Replace whole-body OOXML renumbering with tagged content-control updates.
- Selection tracking for LaTeXSnipper equation detection in Word.

### Phase 5: Dialog Editor (current)

#### Phase 5a: MathLiveCore Extraction ✅

- Refactor `mathliveEditor.ts` into a shared `MathLiveCore` class.
- Task pane and dialog each create their own `MathLiveCore` instance.
- No behavior change for task pane — pure refactor.

#### Phase 5b: Dialog Shell + Persistent Panels ✅

- Create `src/dialog/editorDialog.html` and `editorDialog.ts`.
- Open dialog via `Office.context.ui.displayDialogAsync()`.
- Three-column layout: symbol panel (left, 180px) + MathLive center + template panel (right, 170px).
- Both side panels are persistent (always visible, scrollable) — not auto-collapsing dropdowns.
- Implement Task Pane ↔ Dialog message protocol (`messageParent` / `DialogMessageReceived`).
- Task pane handles Insert/Update actions, dialog is a pure editing surface.

#### Phase 5c: Load & Update ✅

The equation editing lifecycle: inserted OMML equations can be reloaded into the editor for revision.

- Detect LaTeXSnipper equation selection in Word via `DocumentSelectionChanged`.
- Load: extract equation ID from the selected or parent content control tag, load LaTeX source from document settings, open Dialog editor in Update mode.
- Update: rebuild the complete tagged OOXML container through `Word.run`; numbered formulas use an external paragraph anchor so table replacement is atomic from the user's perspective.
- Numbered equation CCs use unique tags (`latexsnipper-eqn-{uuid}`) for direct lookup.
- All update paths use `buildEquationOoxml` so edited formulas remain LaTeXSnipper equations.

#### Phase 5d: Keyboard-Driven Editing ✅

- Arrow keys → MathLive navigation (routed via `executeCommand` in capture phase).
- `Escape` → close dialog with unsaved-changes prompt.
- No JS-level keyboard shortcuts (Office host intercepts Ctrl+Shift combinations before they reach the WebView).

### Phase 6: Recognition Subscription

- Add `/recognition/subscribe-next`, `/recognition/poll`, and `/recognition/cancel`.
- Route the next desktop global screenshot recognition result to the pending Office editor.
- Fill the editor but do not auto-insert by default.
- Add explicit waiting/cancel states in both task pane and dialog editor.

### Phase 7: Numbering ✅

- Auto/manual numbering with persistent state in document settings.
- Numbered display equations use a borderless 3-cell table with unique tags.
- Renumber scans body OOXML for `latexsnipper-eqn-` tags, filters to auto-numbered only via `loadEquationSource`, updates in document order.
- Manual-numbered equations are completely ignored during renumber.
- The `Auto Numbered` ribbon button adds auto-numbering to the selected equation (not a new insert).
- Switching numbering type (none/auto/manual) during update triggers full OOXML rebuild when the structure changes.

### Phase 8: Polish

- Add recent formulas list (stored in document settings, last N entries).
- Add diagnostics page (bridge reachability, protocol version, token validity, feature flags).
- Add user manual section in the add-in or a help pane.
- Split the MathLive bundle if the production add-in payload needs to stay smaller.
- Office version compatibility warning for older Office builds.

### Phase 9: Independent Add-in Installer

The installer must deliver a single-click setup experience: users run one PowerShell script and the add-in appears in Word, persisted across restarts.

**Windows installer (`installer/windows/setup.ps1`):**

1. **SSL Certificate** — Generate self-signed certificate for `localhost`, install to system Trusted Root Certification Authorities. This resolves `NET::ERR_CERT_AUTHORITY_INVALID` in Word's WebView2.
2. **Static deployment** — Copy `office_addin/dist/` to `%APPDATA%\LaTeXSnipper\office_addin\`. The manifest URL points to this local path.
3. **Shared folder** — Share the deployment directory and register in Word's trusted catalog via registry:
   - `HKCU\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs` — add the shared folder path.
   - Also probe `15.0` (Office 2016) and `16.0` (Office 2019/365/2024).
4. **Manifest registration** — Register `manifest.word.xml` and `manifest.powerpoint.xml` in the shared folder catalog.
5. **Office version detection** — Check installed Office version; warn if below minimum (WordApi 1.1+).
6. **Desktop bridge integration** — Optionally prompt user to enable "Office 插件" in LaTeXSnipper settings if bridge isn't already running.

**macOS installer (`installer/macos/`):**

1. Certificate trust via `security add-trusted-cert`.
2. Manifest sideloading via Office add-in dev settings or catalog manifest.
3. AppleScript or shell to detect Office installation.

**Uninstall (`installer/windows/uninstall.ps1`):**

1. Remove registry entries for trusted catalogs.
2. Remove shared folder registration.
3. Optionally remove certificate from Trusted Root CA.
4. Delete deployed static files.

The installer is versioned independently and does not bundle the desktop application. Bridge protocol version compatibility is checked at add-in startup (via `/health`).

## Open Questions

### Resolved

1. Word insertion requires valid editable OMML. The editor shows SVG as live preview, but Insert fails clearly if OMML is not available.
2. ~~Should the task pane editor be removed when the dialog is built?~~ → No. Both editors coexist. Task pane = quick insert, Dialog = premium editing.
3. ~~Should the Office add-in share the same MathJax/MathLive assets as the desktop app or carry its own pinned copy?~~ → The add-in loads MathLive from CDN (`cdn.jsdelivr.net`). SVG preview uses bridge conversion, not MathJax, so no MathJax dependency in the add-in.

### Open

1. Should numbering state live only in Office document settings, or also in LaTeXSnipper's config for recovery across sessions?
2. Should PowerPoint equations remain PNG-based, and can PowerPoint shapes store LaTeX source metadata for re-editing (similar to Word content controls)?
3. Should the bridge auto-launch LaTeXSnipper from the add-in if the bridge is not reachable, or should the user always start the desktop app manually?
4. Should the bridge token be per-user persistent, per-session, or rotated when Office integration is disabled and re-enabled? Current implementation uses per-session tokens.
5. How should the add-in handle Word for Web (Office Online)? The localhost bridge is unreachable from a browser-based Office host. Show a clear "desktop-only" message, or provide a cloud relay option?
6. Double-click detection: should the add-in rely on rapid `DocumentSelectionChanged` timing, or is there a reliable Office.js content control click event? The current prototype uses selection tracking with debounce, which works for selection but doesn't distinguish single-click from double-click.
7. Should the dialog editor support multiple concurrent editor windows (one per equation), or enforce a single dialog at a time? Single dialog is simpler and consistent with MathType's behavior.
8. How should the installer handle Office Click-to-Run vs MSI vs Microsoft Store versions — do they all share the same WEF registry path? Testing needed across Office distribution channels.

## References

- Microsoft Word Office Open XML add-in guidance: https://learn.microsoft.com/en-us/office/dev/add-ins/word/create-better-add-ins-for-word-with-office-open-xml
- Word JavaScript API reference: https://learn.microsoft.com/en-us/javascript/api/word
- PowerPoint JavaScript API reference: https://learn.microsoft.com/en-us/javascript/api/powerpoint
- Office add-in sideloading: https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing
- Office add-in document settings: https://learn.microsoft.com/en-us/office/dev/add-ins/develop/persisting-add-in-state-and-settings

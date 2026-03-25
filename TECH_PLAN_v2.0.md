# LaTeXSnipper 2.0 Technical Plan

## Vision

LaTeXSnipper 2.0 will evolve from a screenshot-based formula recognizer into a desktop mathematical workbench centered on three capabilities:

1. Recognition
2. Editing
3. Computation

The product goal is not to become a full Mathematica replacement. The goal is to deliver a lightweight, local-first, math-focused desktop tool with:

- high-efficiency formula capture
- high-quality structured formula editing
- immediate symbolic or numeric evaluation for common expressions
- strong LaTeX interoperability


## Product Positioning

### 1.0 Series

The current product is optimized for:

- screenshot recognition
- LaTeX preview
- history/favorites/export
- dependency-guided local inference

### 2.0 Series

The next major version should be optimized for:

- screenshot recognition entry
- direct structured editing with MathLive
- expression evaluation with Compute Engine
- round-trip conversion between LaTeX, rendered math, and MathJSON


## Core Direction

2.0 should be built as a clear three-layer architecture:

1. Recognition Layer
2. Editing Layer
3. Compute Layer

The current recognition pipeline stays, but it becomes only one input source into the new editor/workbench.


## Functional Scope

### A. Recognition

Keep existing capabilities:

- screenshot capture
- pix2text-based recognition
- PDF-related recognition flow
- recognition result preview

Recognition output should feed directly into the 2.0 editor window instead of being treated as the final destination.

### B. Editing

Use MathLive `math-field` as the primary formula editor.

Target capabilities:

- structured formula editing
- keyboard-based editing
- built-in Math Virtual Keyboard
- template insertion
- cursor-aware navigation across fractions, roots, matrices, scripts, etc.
- LaTeX import/export

### C. Computation

Use `@cortex-js/compute-engine`.

Target capabilities:

- parse LaTeX into an internal expression tree
- expose MathJSON
- evaluate expressions
- simplify expressions
- numeric evaluation
- show rendered results

Example target flow:

```js
const expr = ce.parse("\\sqrt{6\\sum_{n=1}^{\\infty} \\frac{1}{n^2}}");
expr.evaluateAsync().then(result => console.info(result));
```

This should be supported in the embedded editor page, then synchronized back to the desktop UI.


## Technology Selection

### Editor Engine

- MathLive
- Official docs: `https://mathlive.io/mathfield/`
- GitHub: `https://github.com/arnog/mathlive`

Why:

- mature math-field component
- built-in virtual keyboard
- good LaTeX support
- suitable for embedding in a web view

### Compute Engine

- `@cortex-js/compute-engine`
- Docs: `https://mathlive.io/compute-engine/`
- MathJSON docs: `https://mathlive.io/math-json/`

Why:

- native integration path with MathLive ecosystem
- supports parsing, simplification, evaluation, and MathJSON output
- lower integration risk than mixing unrelated math stacks

### Desktop Integration

- PyQt6
- `QWebEngineView`
- `QWebChannel`

Why:

- existing app stack already uses PyQt6 and WebEngine
- no need to introduce Electron/Tauri for the 2.0 desktop workbench
- low migration risk for current codebase


## Non-Goals for 2.0

The following should explicitly not be treated as 2.0 baseline goals:

- full notebook system
- Mathematica-class symbolic coverage
- plotting engine
- CAS-grade theorem or proof tooling
- programming language integration
- cloud execution or remote compute

These can be future roadmap items, not 2.0 blockers.


## High-Level Architecture

### Desktop Side

Python is responsible for:

- application shell
- capture flow
- model loading and recognition
- persistence
- history/favorites
- export/import
- window management
- desktop commands and settings

### Web Editor Side

Embedded web UI is responsible for:

- MathLive editor
- virtual keyboard
- front-end rendering
- Compute Engine session
- MathJSON generation
- lightweight editor commands

### Bridge Layer

Bridge responsibilities:

- send recognized LaTeX into editor
- request current LaTeX from editor
- request MathJSON from editor
- request computed result from editor
- insert editor content back into current main editor
- update desktop-side history/favorites


## Proposed Project Structure

2.0 should introduce a dedicated editor domain instead of mixing everything into `main.py`.

Recommended structure:

```text
src/
  main.py
  settings_window.py
  updater.py
  deps_bootstrap.py

  backend/
    capture_overlay.py
    model.py
    model_factory.py
    torch_runtime.py
    platform/
    ...

  editor/
    __init__.py
    workbench_window.py
    workbench_bridge.py
    workbench_state.py
    workbench_actions.py
    workbench_history.py
    workbench_export.py

  ui/
    dialogs/
    widgets/
    themes/

  assets/
    mathlive/
      index.html
      app.js
      app.css
      vendor/
        mathlive/
        compute-engine/
```


## Module Responsibilities

### `src/main.py`

Must remain the application entry and main workflow coordinator.

Should not continue to accumulate editor-specific business logic.

Keep in `main.py`:

- startup
- tray
- recognition entry
- top-level window flow
- integration with workbench launch

Move out of `main.py`:

- formula editor internals
- compute logic
- MathLive bridge logic
- workbench state machine

### `src/editor/workbench_window.py`

Owns the 2.0 workbench window.

Responsibilities:

- create `QWebEngineView`
- load local MathLive page
- manage toolbar and right-side panels
- connect window actions to bridge

### `src/editor/workbench_bridge.py`

Owns Python <-> JS communication.

Responsibilities:

- `setLatex()`
- `getLatex()`
- `getMathJson()`
- `evaluate()`
- `simplify()`
- `getRenderedSnapshot()` if needed later

### `src/editor/workbench_state.py`

Owns editor session state.

Responsibilities:

- current latex
- current mathjson
- current computed result
- dirty state
- source marker

Possible source markers:

- manual_input
- screenshot_recognition
- pdf_recognition
- history_restore
- favorite_restore

### `src/editor/workbench_history.py`

Owns workbench-specific history operations.

Responsibilities:

- persist editor sessions if needed
- convert current editor result to history item
- integrate with existing history model without polluting `main.py`

### `src/editor/workbench_export.py`

Owns export logic from the new workbench.

Responsibilities:

- export LaTeX
- export MathJSON
- export plain text result
- export rendered SVG or HTML snapshot later if needed


## Web Assets Design

### `assets/mathlive/index.html`

Minimal host page for:

- `math-field`
- result panel
- MathJSON panel
- action hooks exposed to Python

### `assets/mathlive/app.js`

Owns:

- `MathfieldElement` setup
- virtual keyboard configuration
- compute engine setup
- action methods
- bridge callbacks

### `assets/mathlive/app.css`

Owns:

- editor layout
- theme tokens
- virtual keyboard theme overrides if necessary
- rendered result panel


## Bridge Contract

The bridge contract must be explicit and versioned informally by method name. Avoid ad-hoc `runJavaScript()` calls scattered through the app.

### Python -> JS

- `setLatex(latex: string)`
- `focusMathField()`
- `insertAtCursor(latex: string)`
- `clearEditor()`
- `evaluateExpression()`
- `simplifyExpression()`
- `numericEvaluate()`

### JS -> Python

- `onLatexChanged(latex: string)`
- `onMathJsonChanged(mathjson: string)`
- `onEvaluationResult(latex: string, mathjson: string, rendered: string)`
- `onEditorReady()`
- `onComputeError(message: string)`


## Data Model

Use a normalized workbench payload structure:

```json
{
  "source": "manual_input",
  "latex": "\\frac{1}{2}",
  "mathjson": ["Divide", 1, 2],
  "result_latex": "\\frac{1}{2}",
  "mode": "formula",
  "timestamp": "2026-03-25T10:00:00"
}
```

This structure should be used for:

- bridge payloads
- history persistence
- favorites persistence if a workbench item is saved


## UI Layout Recommendation

The 2.0 workbench should open as a separate window, not be forced into the existing main layout first.

Recommended layout:

- left: editable MathLive panel
- right-top: rendered result
- right-bottom: MathJSON / evaluation result / diagnostics
- bottom toolbar: actions

Bottom toolbar actions:

- Load Recognized Result
- Evaluate
- Simplify
- Numeric
- Copy LaTeX
- Copy MathJSON
- Insert Back to Main Editor


## Theme Strategy

The embedded web page must follow the desktop theme.

Desktop passes theme mode to web page:

- light
- dark

The web page should expose CSS variables for:

- background
- panel background
- border
- text
- muted text
- accent

This must be kept separate from PyQt theme helpers, but synchronized by a small bridge event.


## Packaging Strategy

MathLive and Compute Engine resources should be packaged locally inside the app.

Do not depend on CDN for runtime.

Requirements:

- fully offline editor
- deterministic versioning
- stable packaging with PyInstaller

Plan:

- vendor MathLive assets into `src/assets/mathlive/vendor/`
- vendor Compute Engine assets into the same domain
- load via local `qrc` or file path strategy already used by current app assets


## Versioning Strategy

2.0 should introduce a clear internal feature gate during development.

Suggested config flag:

- `enable_workbench_v2`

Purpose:

- allow staged rollout
- keep current editor path alive during initial implementation
- reduce risk during migration

Once stable, remove the old editor path.


## Milestones

### Milestone 1: Embedded Editor MVP

Goal:

- open a separate workbench window
- load local MathLive page
- edit formulas using `math-field`
- show virtual keyboard
- round-trip LaTeX with Python

Acceptance criteria:

- recognized LaTeX can be pushed into the editor
- edited LaTeX can be sent back to Python
- dark/light themes both work

### Milestone 2: Compute MVP

Goal:

- initialize Compute Engine
- parse current LaTeX
- display MathJSON
- support `evaluate`, `simplify`, and numeric evaluation

Acceptance criteria:

- common algebraic expressions evaluate successfully
- invalid expressions fail gracefully
- result rendering remains stable

### Milestone 3: Main Workflow Integration

Goal:

- integrate screenshot result -> workbench
- integrate workbench -> main editor
- persist workbench results into history/favorites when requested

Acceptance criteria:

- capture result can open directly in workbench
- workbench result can be inserted into the main editor
- history/favorites keep the new payload format

### Milestone 4: Editor Replacement

Goal:

- replace the current lightweight formula edit dialog with the new workbench entry

Acceptance criteria:

- all edit-entry paths can reach the new workbench
- old editor path is removable without feature regression


## Risk Assessment

### Low Risk

- embedding MathLive into `QWebEngineView`
- LaTeX round-trip
- virtual keyboard integration

### Medium Risk

- desktop/web theme synchronization
- robust bridge lifecycle
- offline resource packaging

### Medium-High Risk

- compute capability expectation management
- expression coverage edge cases
- keeping result rendering and evaluation semantics intuitive


## Engineering Rules for 2.0

To avoid another monolith, these rules should be followed:

1. Do not grow `main.py` with editor internals.
2. Every workbench feature must land in `src/editor/`.
3. Python only coordinates; JS owns math editing behavior.
4. Bridge API must be centralized.
5. All packaged web assets must be local and version-pinned.
6. New history/favorites payloads must be explicit structured objects, not implicit legacy lists.


## Recommended First Implementation Task

The first concrete 2.0 task should be:

Build a standalone `WorkbenchWindow` that loads a local MathLive page and supports:

- `setLatex()`
- `getLatex()`
- virtual keyboard
- theme sync

This is the smallest step that de-risks the full direction.


## Final Decision

LaTeXSnipper 2.0 should proceed with:

- MathLive `math-field`
- Math Virtual Keyboard
- Compute Engine
- MathJSON export
- PyQt `QWebEngineView + QWebChannel` integration

This is technically feasible, aligned with the current stack, and significantly more maintainable than building a native formula editor from scratch.

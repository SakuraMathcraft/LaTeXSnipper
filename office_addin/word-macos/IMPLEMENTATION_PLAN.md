# Word macOS Office.js MVP Implementation Plan

**Goal:** Evolve the Word for macOS Office.js MVP from a plain-text prototype
into a realistic formula task pane with MathJax SVG preview and image-based
visual formula insertion while remaining Office.js-safe.

**Architecture:** Static Office.js add-in under `office_addin/word-macos/`.
GitHub Pages preview output is generated under `docs/word-macos/`. Core behavior
lives in small browser ES modules with Node built-in tests.

**Tech Stack:** Office.js, browser ES modules, HTML, CSS, Node `node:test`.

## File Map

- `office_addin/word-macos/DESIGN.md`: design, feature boundary, parity table.
- `office_addin/word-macos/IMPLEMENTATION_PLAN.md`: this implementation plan.
- `office_addin/word-macos/README.md`: local dev, Pages preview, sideload usage.
- `office_addin/word-macos/package.json`: local dev, build, and test scripts.
- `office_addin/word-macos/manifest/word-dev.xml`: local Word task pane manifest.
- `office_addin/word-macos/scripts/build-pages.mjs`: GitHub Pages static build.
- `office_addin/word-macos/src/taskpane.html`: task pane markup.
- `office_addin/word-macos/src/taskpane.css`: macOS-oriented styling.
- `office_addin/word-macos/src/taskpane.js`: UI state, shortcuts, status wiring.
- `office_addin/word-macos/src/latex.js`: LaTeX normalization and inline format.
- `office_addin/word-macos/src/shortcuts.js`: macOS shortcut detection.
- `office_addin/word-macos/src/office/wordInsert.js`: insertion abstraction.
- `office_addin/word-macos/src/formula/formulaModel.js`: formula model helpers.
- `office_addin/word-macos/src/editor/mathEditor.js`: editor availability state.
- `office_addin/word-macos/src/render/mathjaxRenderer.js`: MathJax SVG rendering
  and visual formula HTML.
- `office_addin/word-macos/test/*.test.mjs`: Node tests.

## Phase 1 Tasks

### Task 1: Add tests for the expanded MVP

- [x] Test LaTeX normalization.
- [x] Test inline insertion fallback text.
- [x] Test display insertion fallback text.
- [x] Test numbered display fallback text with manual number.
- [x] Test numbered display placeholder number.
- [x] Test Command + Enter insertion shortcut.
- [x] Test Command + K clear shortcut.
- [x] Test Escape dismiss shortcut.
- [x] Test formula model mode normalization.
- [x] Test MathLive editor fallback boundary for the deferred editor.
- [x] Test GitHub Pages build output.
- [x] Test release manifest SourceLocation remains the fork Pages URL.
- [x] Test task pane source does not make OCR Bridge network requests.
- [x] Test MathJax SVG rendering fallback.
- [x] Test SVG image HTML formatting.
- [x] Test visual insertion through Office.js HTML coercion.
- [x] Test text fallback when visual insertion fails.

### Task 2: Add Office.js-safe insertion abstraction

- [x] Add `src/office/wordInsert.js`.
- [x] Support `insertFormula({ latex, mode, manualNumber })`.
- [x] Keep inline fallback as `\( ... \)`.
- [x] Add display fallback as `\[ ... \]`.
- [x] Add numbered fallback as `\[ ... \]    (number)`.
- [x] Keep Word insertion text-based through `setSelectedDataAsync`.
- [x] Avoid claiming native editable Word equation support.

### Task 3: Add future-facing formula model

- [x] Add `src/formula/formulaModel.js`.
- [x] Normalize LaTeX and manual number.
- [x] Normalize supported modes.
- [x] Generate formula ids.
- [x] Store createdAt and updatedAt timestamps.
- [x] Avoid implementing document metadata, selected load, update, or delete.

### Task 4: Add MathLive fallback boundary

- [x] Add `src/editor/mathEditor.js`.
- [x] Report `Math editor unavailable; using LaTeX source` when MathLive is not
  available.
- [x] Do not vendor MathLive assets in this phase.
- [x] Keep textarea as the source of truth.

### Task 5: Upgrade task pane UI

- [x] Add header with LaTeXSnipper and host status.
- [x] Add formula preview area.
- [x] Add LaTeX source textarea.
- [x] Add inline, display, and numbered mode controls.
- [x] Add manual number field.
- [x] Add Insert Inline, Insert Display, Insert Numbered, and Clear buttons.
- [x] Keep OCR Bridge visible but disabled.
- [x] Add concise operation statuses.
- [x] Use macOS-style layout, spacing, rounded controls, focus states, and
  light/dark mode variables.

### Task 6: Keep GitHub Pages preview working

- [x] Build to `docs/word-macos/`.
- [x] Copy `taskpane.html`, `taskpane.css`, and `taskpane.js`.
- [x] Copy required ES modules under `editor/`, `formula/`, and `office/`.
- [x] Copy required MathJax render module under `render/`.
- [x] Generate `manifest/LaTeXSnipperWordAddin.xml`.
- [x] Keep release manifest SourceLocation at:

```text
https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html
```

### Task 7: Documentation

- [x] Update README with local dev, build, Pages preview, manifest, and sideload
  instructions.
- [x] Update DESIGN with current implementation, Windows/macOS parity mapping,
  and deferred features.
- [x] Update this implementation plan with completed Phase 1 tasks.

### Task 8: Add MathJax visual formula insertion

- [x] Add static MathJax script loading to `src/taskpane.html`.
- [x] Render task pane preview through MathJax SVG when available.
- [x] Add `src/render/mathjaxRenderer.js`.
- [x] Convert MathJax SVG to an image data URI.
- [x] Generate inline, display, and numbered visual HTML.
- [x] Extend `src/office/wordInsert.js` with visual insertion.
- [x] Use Office.js HTML coercion for visual insertion.
- [x] Fall back to text insertion if MathJax rendering or HTML insertion fails.
- [x] Keep text fallback formatting for inline, display, and numbered modes.
- [x] Document visual insertion as image-based, not Word-native OMML.

## Deferred Work

- Real Word-native editable OMML insertion.
- Full MathLive editor assets.
- PNG managed formula insertion.
- Managed formula identity in the document.
- Selected formula load, update, and delete.
- Real OCR Bridge.
- Desktop Bridge integration.
- OLE / OMML conversion.
- Automatic renumbering and references.
- Settings window.
- AppSource packaging.

## Validation

Run before considering the phase complete:

```bash
npm test --prefix office_addin/word-macos
npm run build --prefix office_addin/word-macos
test -f docs/word-macos/taskpane.html
test -f docs/word-macos/taskpane.js
test -f docs/word-macos/taskpane.css
test -f docs/word-macos/manifest/LaTeXSnipperWordAddin.xml
xmllint --noout docs/word-macos/manifest/LaTeXSnipperWordAddin.xml
```

Also run JavaScript syntax checks for changed modules:

```bash
node --check office_addin/word-macos/src/taskpane.js
node --check office_addin/word-macos/src/office/wordInsert.js
node --check office_addin/word-macos/src/formula/formulaModel.js
node --check office_addin/word-macos/src/editor/mathEditor.js
node --check office_addin/word-macos/src/shortcuts.js
node --check office_addin/word-macos/scripts/build-pages.mjs
```

# Word macOS Office.js MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scoped Word for macOS Office.js task pane MVP that inserts manual LaTeX as plain inline text.

**Architecture:** Static Office.js add-in under `office_addin/word-macos/`. Core behavior lives in small ES modules with Node built-in tests; the task pane is plain HTML/CSS/JavaScript and has no root build dependency.

**Tech Stack:** Office.js, browser ES modules, HTML, CSS, Node `node:test`.

---

## File Map

- `office_addin/word-macos/DESIGN.md`: scoped MVP design and feature boundary.
- `office_addin/word-macos/IMPLEMENTATION_PLAN.md`: this implementation plan.
- `office_addin/word-macos/README.md`: sideload usage and platform notes.
- `office_addin/word-macos/package.json`: local test script only.
- `office_addin/word-macos/manifest/word-dev.xml`: Word task pane manifest for local sideload testing.
- `office_addin/word-macos/src/taskpane.html`: task pane markup.
- `office_addin/word-macos/src/taskpane.css`: compact macOS-oriented styling.
- `office_addin/word-macos/src/taskpane.js`: UI and Office.js integration.
- `office_addin/word-macos/src/latex.js`: LaTeX normalization and inline text formatting.
- `office_addin/word-macos/src/shortcuts.js`: macOS shortcut detection.
- `office_addin/word-macos/test/latex.test.mjs`: LaTeX formatting tests.
- `office_addin/word-macos/test/shortcuts.test.mjs`: shortcut tests.

## Tasks

### Task 1: Add failing core tests

**Files:**
- Create: `office_addin/word-macos/package.json`
- Create: `office_addin/word-macos/test/latex.test.mjs`
- Create: `office_addin/word-macos/test/shortcuts.test.mjs`

- [ ] Add a local `npm test` script that runs Node's built-in test runner.
- [ ] Test `formatInlineFormula("x^2")` returns `"\\( x^2 \\)"`.
- [ ] Test whitespace is trimmed before formatting.
- [ ] Test empty input is rejected.
- [ ] Test Command + Enter is detected as insert.
- [ ] Test Command + K is detected as clear.
- [ ] Run `npm test --prefix office_addin/word-macos` and confirm tests fail because implementation modules do not exist yet.

### Task 2: Implement core behavior

**Files:**
- Create: `office_addin/word-macos/src/latex.js`
- Create: `office_addin/word-macos/src/shortcuts.js`

- [ ] Implement `normalizeLatexInput(value)`.
- [ ] Implement `formatInlineFormula(value)`.
- [ ] Implement `shouldInsertFormulaShortcut(event)`.
- [ ] Implement `shouldClearInputShortcut(event)`.
- [ ] Run `npm test --prefix office_addin/word-macos` and confirm tests pass.

### Task 3: Add static Office task pane

**Files:**
- Create: `office_addin/word-macos/src/taskpane.html`
- Create: `office_addin/word-macos/src/taskpane.css`
- Create: `office_addin/word-macos/src/taskpane.js`

- [ ] Add the task pane HTML with manual LaTeX textarea, Insert Formula button,
  Clear button, Bridge placeholder, OCR placeholder, and status area.
- [ ] Add task pane styling with stable button sizes and compact layout.
- [ ] Wire Insert Formula to `Office.context.document.setSelectedDataAsync` with
  text coercion.
- [ ] Wire Clear button and Command + K.
- [ ] Wire Command + Enter to insert.
- [ ] Keep OCR controls disabled and placeholder-only.
- [ ] Run `npm test --prefix office_addin/word-macos`.

### Task 4: Add Word manifest and docs

**Files:**
- Create: `office_addin/word-macos/manifest/word-dev.xml`
- Create: `office_addin/word-macos/README.md`

- [ ] Add a Word task pane development manifest pointing to the local task pane URL.
- [ ] Document macOS sideload assumptions and local HTTPS serving requirement.
- [ ] Document Windows and Linux usage boundaries.
- [ ] Document explicitly deferred features.

### Task 5: Verify isolation

**Files:**
- Inspect only.

- [ ] Run `git status --short`.
- [ ] Confirm all new files are under `office_addin/word-macos/`.
- [ ] Confirm no files under `office_plugin/` changed.
- [ ] Confirm no root dependency/build config changed.
- [ ] Run `npm test --prefix office_addin/word-macos`.

# Word macOS Office.js MVP Design

## Scope

This MVP is intentionally small. It creates a Word for macOS Office.js task pane
that accepts manual LaTeX, inserts the LaTeX as plain text at the current Word
cursor, and exposes placeholder status for future OCR Bridge work.

All new implementation files live under `office_addin/word-macos/`. The existing
Windows VSTO plugin in `office_plugin/`, the desktop app, OCR modules,
screenshot modules, Bridge server, packaging, installer, CI/release workflows,
and root dependency/build configuration are out of scope.

## MVP Features

- Word for macOS Office.js task pane.
- Manual LaTeX input.
- Insert Formula button.
- Clear button.
- macOS shortcuts:
  - Command + Enter inserts the formula.
  - Command + K clears the input.
- Inserted content is plain text at the current Word cursor in inline LaTeX
  form:

```text
\( ... \)
```

- OCR Bridge placeholder UI/status only:
  - Bridge not connected.
  - OCR coming soon.

## Deferred Features

- MathLive editor.
- MathJax rendering or preview.
- SVG/PNG managed formula insertion.
- Image markers.
- Document-level metadata store.
- Editable formula identity.
- Selected formula loading.
- Updating or deleting selected managed formulas.
- Real OCR Bridge calls.
- Desktop Bridge integration.
- Bridge HTTP endpoint changes.
- OMML generation.
- OLE/OMML conversion.
- Automatic numbering and references.
- Document-wide formula restore.

## Parity Table

| Capability | MVP status | Notes |
| --- | --- | --- |
| Open LaTeXSnipper controls inside Word | In MVP | Implemented as an Office.js task pane. |
| Manual LaTeX input | In MVP | Plain textarea input. |
| Insert formula as text | In MVP / partially aligned | Inserts `\( ... \)` plain text, not managed image/OMML/OLE. |
| Clear input | In MVP | Button and Command + K shortcut. |
| Status feedback | In MVP | Static Bridge/OCR placeholder status plus operation status. |
| macOS Command shortcuts | In MVP | Command + Enter and Command + K. |
| MathLive editor | Deferred / planned | Future editor upgrade. |
| MathJax preview | Deferred / planned | Future render preview. |
| SVG/PNG managed formula insertion | Deferred / planned | Future managed formula mode. |
| Editable formula identity | Deferred / planned | Requires markers and metadata. |
| Selected formula loading | Deferred / planned | Requires managed formula identity. |
| Update selected formula | Deferred / planned | Requires managed formula identity. |
| Delete selected formula | Deferred / planned | Requires managed formula identity. |
| Screenshot OCR from Word | Deferred / planned | Placeholder only in MVP. |
| Desktop Bridge communication | Deferred / planned | No HTTP calls in MVP. |
| OMML insertion | Deferred / planned | Future Word-native output. |
| OLE/OMML conversion | Deferred / planned | Future Windows/native parity work. |
| Automatic numbering and references | Deferred / planned | Future Word document feature. |

## Architecture

The MVP is a static Office.js add-in:

- `manifest/word-dev.xml` declares a Word task pane command.
- `src/taskpane.html` loads Office.js and the local task pane script.
- `src/taskpane.js` wires the UI to Office.js.
- `src/latex.js` owns LaTeX input normalization and inline text formatting.
- `src/shortcuts.js` owns macOS shortcut detection.
- `src/taskpane.css` provides a compact macOS-oriented task pane layout.

There is no build step for the MVP. The files are plain HTML, CSS, and ES
modules so the add-in can be served by any static HTTPS server during sideload
testing. Tests use Node's built-in test runner and do not require root project
dependency changes.

## Data Flow

1. User types LaTeX into the textarea.
2. Insert Formula calls `formatInlineFormula(input)`.
3. The task pane uses `Office.context.document.setSelectedDataAsync` with text
   coercion to insert the result at the current Word selection.
4. Clear empties the textarea and resets operation status.

## Error Handling

- Empty input reports a task pane status message and does not call Word.
- Office.js insertion failure reports the returned Office error message.
- If Office.js is unavailable, the task pane remains visible and reports that it
  is waiting for Word.
- OCR controls are disabled for the MVP and show "OCR coming soon".

## Distribution

MVP distribution is manifest sideload only:

- macOS: sideload the Word manifest and serve this directory through a local
  HTTPS static server.
- Windows: users should continue using the existing VSTO plugin for full native
  features; this Office.js MVP may load as a lightweight cross-platform option.
- Linux: there is no desktop Word; any usage is through Word for the web, subject
  to Office.js and browser constraints.

## Acceptance Criteria

- New files are only under `office_addin/word-macos/`.
- No existing Windows VSTO, desktop, OCR, Bridge, packaging, installer, CI, or
  root dependency/build files are modified.
- The task pane has manual LaTeX input, Insert Formula, Clear, and placeholder
  Bridge/OCR status.
- Command + Enter inserts formatted inline LaTeX text.
- Command + K clears the input.
- Inserted text uses the form `\( ... \)`.
- Unit tests cover LaTeX formatting and shortcut detection.

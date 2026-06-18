# Word macOS Office.js MVP Design

## Scope

The macOS add-in is an Office.js task pane for Word. It moves the first MVP
closer to the Windows Word plugin's feature intent while staying inside
Office.js-safe behavior.

The goal is feature parity with Windows, native-feeling interaction on macOS,
and Office.js-safe implementation. The goal is not a pixel-for-pixel Windows
VSTO UI clone.

All source changes for this phase live under `office_addin/word-macos/`, with
generated GitHub Pages preview files under `docs/word-macos/`. The existing
Windows VSTO plugin in `office_plugin/`, the desktop app, OCR modules,
screenshot modules, Bridge server, packaging, installer, CI/release workflows,
and root dependency/build configuration remain out of scope.

## Implemented Phase 1 Features

- Word for macOS Office.js task pane.
- Header with LaTeXSnipper title and Word ready / Office.js unavailable status.
- Manual LaTeX source textarea.
- MathJax SVG formula preview loaded from a static CDN.
- Visual formula insertion as an SVG image through Office.js HTML coercion.
- Inline formula mode.
- Display formula mode.
- Numbered display formula mode.
- Manual number field.
- Insert Inline, Insert Display, Insert Numbered, and Clear actions.
- macOS shortcuts:
  - Command + Enter inserts using the selected mode.
  - Command + K clears input.
  - Escape blurs the active control and returns status to Ready.
- Operation status:
  - Ready.
  - Inserting...
  - Inserted at cursor.
  - concise error messages.
- OCR Bridge placeholder:
  - Bridge: Not connected.
  - OCR: Coming soon.
  - disabled OCR button.

## Office.js Visual Insertion

This phase renders LaTeX to SVG using MathJax, wraps the SVG as an image, and
inserts the image with Office.js HTML coercion. It does not claim full
Word-native editable equation support.

| Mode | Inserted visual output |
| --- | --- |
| Inline | Inline SVG image |
| Display | Centered SVG image block |
| Numbered | Centered SVG image with manual number or `#` |

The insertion behavior is isolated behind:

```text
src/office/wordInsert.js
```

If SVG rendering or HTML image insertion fails, the add-in falls back to plain
text:

```text
\( ... \)
\[ ... \]
\[ ... \]    (#)
```

Future OOXML or OMML insertion can replace the image path there without
rewriting the task pane UI.

## macOS Interaction And Visual Style

The task pane uses a single-column structure with calm spacing, rounded native
controls, subtle borders, keyboard focus states, and light/dark mode variables.
It uses a macOS-first system font stack:

```css
-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif
```

Windows concepts are translated into macOS Office.js equivalents:

| Windows concept | macOS Office.js equivalent |
| --- | --- |
| Ribbon command | Task pane action button |
| Native OLE / OMML path | Future insertion abstraction |
| Screenshot OCR entry | Disabled Bridge placeholder |
| Dense VSTO settings/actions | Compact task pane sections |
| Managed formula identity | Future model and metadata work |

## MathJax Strategy

The task pane loads MathJax from:

```text
https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js
```

This keeps the GitHub Pages preview static and avoids root build dependency
changes. If MathJax is blocked or unavailable, the UI reports:

```text
MathJax unavailable; using text fallback
```

MathLive editing can still be added later as static assets if size, licensing,
loading, and GitHub Pages compatibility are acceptable. The LaTeX textarea
remains the source of truth.

## Formula Model

`src/formula/formulaModel.js` defines a small future-facing formula model:

- generated formula id
- normalized LaTeX
- mode
- manual number
- createdAt / updatedAt timestamps

This does not implement selected formula load, update, delete, or document-wide
metadata yet.

## Deferred Features

- MathLive editor assets.
- PNG managed formula insertion.
- Image markers.
- Document-level metadata store.
- Editable formula identity in the document.
- Selected formula loading.
- Updating or deleting selected managed formulas.
- Real OCR Bridge calls.
- Desktop Bridge integration.
- Bridge HTTP endpoint changes.
- Word-native editable OMML insertion.
- OLE/OMML conversion.
- Automatic numbering and references.
- Settings window.
- AppSource packaging.
- Document-wide formula restore.

## Parity Table

| Capability | Phase 1 status | Notes |
| --- | --- | --- |
| Open LaTeXSnipper controls inside Word | In MVP | Implemented as an Office.js task pane. |
| Manual LaTeX input | In MVP | Plain textarea input. |
| Formula preview | In MVP | MathJax SVG preview with text fallback. |
| Insert inline formula | In MVP / partial | Inserts SVG image through Office.js HTML, not OMML. |
| Insert display formula | In MVP / partial | Inserts centered SVG image through Office.js HTML, not OMML. |
| Numbered display UI | In MVP / partial | Manual number with image insertion, no automatic renumbering. |
| Clear input | In MVP | Button and Command + K shortcut. |
| Status feedback | In MVP | Host, editor, operation, and Bridge placeholder status. |
| macOS Command shortcuts | In MVP | Command + Enter, Command + K, Escape. |
| MathLive editor | Deferred / planned | Static asset strategy still pending. |
| MathJax preview | In MVP | Uses static CDN and SVG output. |
| SVG image insertion | In MVP / partial | Image-based visual formula, not managed editable equation. |
| PNG managed formula insertion | Deferred / planned | Future managed formula mode. |
| Editable formula identity | Deferred / planned | Requires markers and metadata. |
| Selected formula loading | Deferred / planned | Requires managed formula identity. |
| Update selected formula | Deferred / planned | Requires managed formula identity. |
| Delete selected formula | Deferred / planned | Requires managed formula identity. |
| Screenshot OCR from Word | Deferred / planned | Placeholder only in this phase. |
| Desktop Bridge communication | Deferred / planned | No network calls in this phase. |
| OMML insertion | Deferred / planned | Future Word-native output. |
| OLE/OMML conversion | Deferred / planned | Windows/native parity work, not direct macOS port. |
| Automatic numbering and references | Deferred / planned | Future Word document feature. |

## Architecture

The add-in is a static Office.js add-in:

- `manifest/word-dev.xml` declares the local development task pane.
- `src/taskpane.html` loads Office.js and browser ES modules.
- `src/taskpane.js` wires UI state, shortcuts, status, and insertion calls.
- `src/office/wordInsert.js` owns Office.js-safe insertion formatting and Word
  insertion.
- `src/formula/formulaModel.js` owns normalized formula metadata.
- `src/editor/mathEditor.js` owns editor availability and fallback status.
- `src/render/mathjaxRenderer.js` owns MathJax SVG rendering and image HTML.
- `src/latex.js` owns LaTeX input normalization and inline formatting.
- `src/shortcuts.js` owns macOS shortcut detection.
- `src/taskpane.css` provides the macOS-oriented task pane layout.
- `scripts/build-pages.mjs` generates static GitHub Pages output.

The files are plain HTML, CSS, and ES modules. Tests use Node's built-in test
runner and do not require root project dependency changes.

## Data Flow

1. User types LaTeX into the textarea.
2. Preview updates using MathJax SVG rendering when available.
3. User chooses Inline, Display, or Numbered mode.
4. Insert calls `createFormulaModel(...)`.
5. The task pane calls `insertFormula(..., visual: true)` from
   `src/office/wordInsert.js`.
6. The insertion module renders SVG and uses
   `Office.context.document.setSelectedDataAsync` with HTML coercion.
7. If visual insertion fails, the insertion module retries with text coercion.
8. Status changes to Inserting..., Inserted visual formula, fallback status, or
   an error message.

## Error Handling

- Empty input reports a task pane status message and does not call Word.
- Office.js insertion failure reports the returned Office error message.
- If Office.js is unavailable, the task pane remains visible and reports that it
  should be opened from Word.
- MathJax absence is reported as a concise fallback status.
- OCR controls are disabled and no Bridge request is made.

## Distribution

- Local development uses `manifest/word-dev.xml` and
  `http://localhost:3000/src/taskpane.html`.
- GitHub Pages preview is generated under `docs/word-macos/`.
- The release manifest points to:

```text
https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html
```

## Acceptance Criteria

- Source changes stay under `office_addin/word-macos/`.
- Generated preview changes stay under `docs/word-macos/`.
- No existing Windows VSTO, desktop, OCR, Bridge, packaging, installer, CI, or
  root dependency/build files are modified.
- The task pane supports manual LaTeX input, preview, inline/display/numbered
  modes, Clear, disabled OCR placeholder, and status feedback.
- Command + Enter inserts using the selected mode.
- Command + K clears the input.
- Escape dismisses transient focus/status.
- Unit tests cover LaTeX normalization, insertion fallback formatting, visual
  insertion fallback, MathJax rendering fallback, shortcuts, build output,
  release manifest URL, and no OCR Bridge network request.

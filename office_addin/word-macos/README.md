# LaTeXSnipper Word macOS Add-in MVP

This directory contains the scoped Word for macOS Office.js MVP. It is separate
from the Windows VSTO plugin in `office_plugin/`.

Windows uses VSTO for native Office integration. Word for macOS does not support
VSTO or COM add-ins, so this add-in uses Office.js. The macOS version targets
feature parity with the Windows plugin over time, not implementation parity.

## What Is Implemented

- Word for macOS Office.js task pane.
- Manual LaTeX source input.
- Lightweight formula preview that shows the Office.js-safe text fallback.
- Inline, display, and numbered display insertion modes.
- Manual number field for numbered display fallback.
- Insert Inline, Insert Display, Insert Numbered, and Clear actions.
- macOS shortcuts:
  - Command + Enter inserts using the selected mode.
  - Command + K clears the input.
  - Escape dismisses transient focus/status.
- Status feedback:
  - Ready.
  - Inserting...
  - Inserted at cursor.
  - Office.js unavailable.
- OCR Bridge placeholder only:
  - Bridge: Not connected.
  - OCR: Coming soon.

Insertion is still plain text by design in this phase:

```text
\( ... \)
\[ ... \]
\[ ... \]    (#)
```

It does not yet insert native editable Word equations.

## Deferred

- Full MathLive editor assets.
- MathJax rendering.
- SVG/PNG managed formula insertion.
- Image markers and document-level metadata store.
- Selected formula loading, updating, or deleting.
- Real OCR Bridge calls.
- Desktop Bridge integration or Bridge endpoint changes.
- Word-native OMML insertion.
- OLE/OMML conversion.
- Automatic renumbering and references.
- Settings window.
- AppSource packaging.
- Document-wide formula restore.

## Files

```text
office_addin/word-macos/
  DESIGN.md
  IMPLEMENTATION_PLAN.md
  README.md
  package.json
  manifest/word-dev.xml
  scripts/build-pages.mjs
  src/editor/mathEditor.js
  src/formula/formulaModel.js
  src/office/wordInsert.js
  src/taskpane.html
  src/taskpane.css
  src/taskpane.js
  src/latex.js
  src/shortcuts.js
  test/*.test.mjs
```

## Local Tests

Run from the repository root:

```bash
npm test --prefix office_addin/word-macos
```

The tests use Node's built-in test runner and do not install or modify root
project dependencies.

## Local Dev Server

Run from `office_addin/word-macos/`:

```bash
npm run dev
```

The server listens on `localhost:3000` and serves the add-in directory. The task
pane is available at:

```text
http://localhost:3000/src/taskpane.html
```

The local development manifest is:

```text
office_addin/word-macos/manifest/word-dev.xml
```

It points to:

```text
http://localhost:3000/src/taskpane.html
```

For Word sideload testing, serve the directory on port `3000`, then sideload
`manifest/word-dev.xml` into Word for macOS. A typical sideload location is:

```text
~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Restart Word after copying the manifest if the add-in does not appear
immediately.

## GitHub Pages Preview Build

Run from the repository root:

```bash
npm run build --prefix office_addin/word-macos
```

The build creates the static GitHub Pages preview under:

```text
docs/word-macos/
```

Required output includes:

```text
docs/word-macos/taskpane.html
docs/word-macos/taskpane.css
docs/word-macos/taskpane.js
docs/word-macos/editor/mathEditor.js
docs/word-macos/formula/formulaModel.js
docs/word-macos/latex.js
docs/word-macos/office/wordInsert.js
docs/word-macos/shortcuts.js
docs/word-macos/manifest/LaTeXSnipperWordAddin.xml
```

The release manifest points to the fork Pages preview:

```text
https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html
```

Do not switch it to the upstream Pages URL until the release target changes.

For manual GitHub Pages preview deployment, configure GitHub Pages to publish the
repository `docs/` directory. The generated add-in files live under the Pages
path:

```text
word-macos/
```

That makes the task pane available at:

```text
https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html
```

No GitHub Actions workflow is required for the current manual preview flow.

## Using The GitHub Pages Preview

Users of the GitHub Pages preview do not need to run `npm install`,
`npm run dev`, or `npm run build`. They only need the release manifest:

```text
docs/word-macos/manifest/LaTeXSnipperWordAddin.xml
```

After the preview is published, download that manifest from the repository or
release artifact, then sideload it into Word for macOS. A typical sideload
location is:

```text
~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Restart Word after copying the manifest if the add-in does not appear
immediately.

## Platform Notes

- macOS: primary Office.js MVP target.
- Windows: the existing VSTO plugin remains the native Word integration.
- Linux: there is no Microsoft Word desktop app. Usage is limited to Word for
  the web where Office.js add-ins are supported.

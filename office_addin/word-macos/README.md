# LaTeXSnipper Word macOS Add-in MVP

This directory contains the scoped Word for macOS Office.js MVP. It is separate
from the Windows VSTO plugin in `office_plugin/`.

## What This MVP Does

- Opens a Word Office.js task pane.
- Accepts manual LaTeX input.
- Inserts the input at the current Word cursor as plain inline LaTeX text:

```text
\( ... \)
```

- Clears the input.
- Supports macOS shortcuts:
  - Command + Enter inserts the formula text.
  - Command + K clears the input.
- Shows placeholder OCR status:
  - Bridge not connected.
  - OCR coming soon.

## What This MVP Does Not Do

- No MathLive editor.
- No MathJax preview or rendering.
- No SVG/PNG managed formula insertion.
- No image marker or document-level metadata store.
- No selected formula loading, updating, or deleting.
- No real OCR Bridge calls.
- No desktop Bridge integration or Bridge endpoint changes.
- No OMML generation.
- No OLE/OMML conversion.
- No automatic numbering or references.
- No document-wide formula restore.

## Files

```text
office_addin/word-macos/
  DESIGN.md
  IMPLEMENTATION_PLAN.md
  README.md
  package.json
  manifest/word-dev.xml
  src/taskpane.html
  src/taskpane.css
  src/taskpane.js
  src/latex.js
  src/shortcuts.js
  test/latex.test.mjs
  test/shortcuts.test.mjs
```

## Local Tests

Run from the repository root:

```bash
npm test --prefix office_addin/word-macos
```

The tests use Node's built-in test runner and do not install or modify root
project dependencies.

## macOS Sideload Notes

The development manifest points to:

```text
https://localhost:3000/src/taskpane.html
```

Serve `office_addin/word-macos/` with a local HTTPS static server on port `3000`,
then sideload `manifest/word-dev.xml` into Word for Mac. A typical sideload
location is:

```text
~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Restart Word after copying the manifest if it does not appear immediately.

## Platform Notes

- macOS: primary MVP target.
- Windows: the existing VSTO plugin remains the full native Office integration.
  This Office.js MVP is a lightweight cross-platform option only.
- Linux: there is no Microsoft Word desktop app. Any usage is through Word for
  the web and depends on Office.js browser support.

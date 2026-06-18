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
  scripts/build-pages.mjs
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

## GitHub Pages Preview Build

Run from the repository root:

```bash
npm run build --prefix office_addin/word-macos
```

The build creates:

```text
office_addin/word-macos/dist/
  taskpane.html
  taskpane.css
  taskpane.js
  latex.js
  shortcuts.js
  manifest/LaTeXSnipperWordAddin.xml
```

The release manifest in `dist/manifest/LaTeXSnipperWordAddin.xml` points to the
GitHub Pages preview URL:

```text
https://galileo927.github.io/LaTeXSnipper/word-macos/taskpane.html
```

For manual GitHub Pages preview deployment, publish the generated `dist/`
contents under the Pages path:

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
office_addin/word-macos/dist/manifest/LaTeXSnipperWordAddin.xml
```

After the preview is published, download that manifest from the repository or
release artifact, then sideload it into Word for macOS. A typical sideload
location is:

```text
~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Restart Word after copying the manifest if the add-in does not appear
immediately.

## macOS Sideload Notes

The development manifest points to:

```text
http://localhost:3000/src/taskpane.html
```

For quick local static checks, use `npm run dev`. For Word sideload testing,
serve the same directory on port `3000`, then sideload `manifest/word-dev.xml`
into Word for Mac. A typical sideload location is:

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

# LaTeXSnipper Office for Mac

LaTeXSnipper Office for Mac is an Office.js add-in for Word and PowerPoint on Apple Silicon. The [DMG build](#build) produces the standalone **LaTeXSnipper Office.app** installer. The add-in uses the editor, task pane, and MathJax typography renderer from [`Office_plugin/shared`](../shared/).

See the [user manual](../../user_manual/user_manual.md#macos-版安装与注册) for installation, formula workflows, and troubleshooting.

## Independence from the desktop app

The add-in does not need the LaTeXSnipper desktop app. Editing, rendering, insertion, settings and help work on their own. **Screenshot recognition is the only exception:** it subscribes to the desktop app's next recognition result through the local [Automation API](../../docs/automation_api.md) (`next_result`, with query and cancel). If the desktop app is closed or its **自动化接口** is off, only that button reports the problem.

The add-in reads exactly one desktop file, the published discovery file `~/Library/Application Support/LaTeXSnipper/automation-api.json`. The Automation API token stays in the host and is never sent to the Office pages.

## Local host and installation

The app generates a self-signed, non-CA certificate valid for `localhost` and `127.0.0.1` in `~/Library/Application Support/LaTeXSnipper Office/`. The per-user LaunchAgent `com.mathcraft.latexsnipper.office.host` serves add-in pages over `https://localhost:28766` from login and restarts the host after a crash. Installation writes `latexsnipper-office-addin.xml` into the Word and PowerPoint `wef` folders.

The app exposes `--install`, `--uninstall`, and `--serve`. Uninstall removes the agent, the manifests, the certificate trust, and the add-in's settings. Launchd runs `--serve`, which writes `host.log` under the add-in's application support directory.

## Features

The ribbons follow the Windows ribbons group by group. Mac leaves out what Office for Mac cannot do: creating OLE objects, MathType conversion, Word format conversion and PowerPoint text-box equations.

| Host | Groups and commands |
| --- | --- |
| Word | **Formula**: Inline, Display, Numbered Formula, Screenshot OCR · **Edit**: Load Selected, Delete Selected · **Formula Parsing**: Parse Selected, Parse All · **Cross Reference**: Insert Reference · **Numbering**: Add Number, Renumber All · **Numbering Boundaries**: Chapter Separator, Section Boundary · **Formula Style**: Format Selected, Format All · **Tools**: Status Pane, Settings, Help |
| PowerPoint | **Formula**: Insert Formula, Screenshot OCR · **Edit**: Load Selected, Delete Selected · **Conversion**: To PNG, To SVG · **Formula Style**: Format Selected, Format All · **Tools**: Status Pane, Settings, Help |

Both hosts have the shared editor and preview, the status pane (Word with the display / auto number / custom number options), typography settings with JSON preset import and export, help, and screenshot recognition. The ribbon icons are [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) chosen to match the Windows `imageMso` icons, rendered to 16, 32 and 80 px by `tools/generate_icons.py`.

### Word

- Formulas are always native OMML equations; there is no insertion-format choice.
- Inline, display and numbered insertion; numbers on the right or left, with enclosure, chapter / section prefixes and separator from Settings.
- Load, edit, delete and format a selected formula or the whole document. An edit replaces only the formula's `m:oMath`: its content control, paragraph layout, number, bookmark, references and the surrounding text stay.
- Add Number, Renumber All, chapter and section boundaries, and cross-references (`REF` fields to the number bookmark).
- Parse Selected / Parse All convert delimited LaTeX (`$…$`, `\(…\)`, `$$…$$`, `\[…\]`, `\tag{…}`) in body text and table cells, cell by cell, with the Windows scanner rules. Content controls, fields, equations, pictures, hyperlinks, comments, tracked changes and code-styled paragraphs are never parsed. Unlike Windows, parsed formulas with automatic numbers are renumbered right after the parse.

### PowerPoint

- Formulas are PNG pictures by default, or SVG pictures (Settings). To PNG / To SVG convert between them.
- Insert, load, edit, delete and format the selection or the whole presentation. Edits and conversions keep the picture format, position, user scale and layer order: the new picture is inserted on the original's layer before the original is removed.
- Format resets a picture that was stretched in only one direction too (Windows compares the width only).
- There are no text-box equations on Mac. With the caret or a text selection in a text box, the text stays as it is and the formula is placed on the slide.

### Windows OLE formulas

LaTeXSnipper OLE formulas from the Windows plugin are recognized by their object type (Word: ProgID `LaTeXSnipper.Formula`, or the Windows formula tag in the picture's alternative text, because Word for Mac exports a selected OLE object as a plain picture; PowerPoint: render engine `MathJaxSvg` in the shape tags). They are kept in the file and are never loaded, replaced, deleted, converted, formatted or included in batches, also in mixed selections. The add-in tells the user to edit them with the Windows plugin. Word paragraphs that contain an embedded object are not rewritten (for example by Parse or Add Number).

## Word document contract

Word formulas use the Windows contract (`WordFormulaMetadataStore`, `WordDocumentIdentityStore`, `WordEquationNumbering`), so a formula inserted on either platform loads, edits and renumbers on the other:

| Artifact | Form |
| --- | --- |
| Formula | rich-text content control, title `LaTeXSnipper Equation`, tag `latexsnipper-eq-<equationId>\|<revision>`, content one `m:oMath` |
| Metadata | document variable `LS.E.<equationId>.<revision>` with the schema 3 JSON; a new revision on every save, old revisions are kept for undo |
| Document identity | document variable `LaTeXSnipper.DocumentId` |
| Display / numbered layout | Windows paragraph properties; numbered paragraphs get the centre and right tab stops of the text width (section or table cell) |
| Number | bookmark `LaTeXSnipperEq_<equationId>` (Word keeps the first 40 characters) over manual text or a `SEQ LaTeXSnipperEquation` field |
| Reference | field ` REF LaTeXSnipperEq_<equationId> \h ` |
| Boundaries | hidden content controls tagged `latexsnipper-number-boundary-chapter` / `-section` |

Office.js can read document variables (they are part of the document's OOXML) but cannot write them. The host writes them through Word's AppleScript interface (`host/latexsnipper_office/word_variables.py`): the page marks its document with a temporary hidden bookmark `_LSLink…`, and the script writes only plugin variable names to the document that carries it. This is why macOS asks for permission to control Word.

Differences from Windows, all inside the same file format: unequal multi-column sections use the first column's width for the number tab stops (Office.js has no layout information); deleting an automatic number removes the whole `SEQ` field rather than only its bookmarked span.

## PowerPoint contract

PNG formulas are the Windows `Image` formulas: schema 3 shape tags of `PowerPointFormulaMetadataStore` (source and typography as upper-case UTF-8 hex in 200-character chunks), alt text `LaTeXSnipper formula <equationId>`, presentation identity in the custom document property `LaTeXSnipper.DocumentId`, 300 DPI with 1.5 pt / 0.5 pt padding and a 420 pt width cap. SVG pictures carry the same tags plus the Mac-only tag `LaTeXSnipperImageFormat=Svg`; Windows ignores it and treats them as pictures it can re-render.

## Layout

| Path | Role |
| --- | --- |
| `host/latexsnipper_office/` | The app: HTTPS host, certificate, sideloading, LaunchAgent install, CoreText outlines, OMML, settings, Word document variables, Automation API relay, setup window |
| `manifest.xml` | Add-in manifest template (`{{BASE_URL}}`, `{{VERSION}}`) |
| `web/*.html` | Task pane / shared runtime, editor, settings and help pages |
| `web/app/controller.mjs` | Ribbon commands, command gate, status, editor sessions, OCR |
| `web/app/word/` | Word contract, OOXML builders and rewrites, LaTeX parser, Office.js commands |
| `web/app/powerpoint/` | PowerPoint shape tags and Office.js commands |
| `web/icons/` | Ribbon icons, rendered by `tools/generate_icons.py` from `tools/fluent-icons/` |
| `build.py` | Builds the app and DMG |
| `tests/` | Python and Node tests |

The server serves only fixed asset roots and same-origin `/api` routes that require the `X-LaTeXSnipper-Office` header; it never grants CORS.

Office for Mac behaviours the add-in works around:

- Ribbon icons are cached by URL, so the sideloaded manifest gives every icon URL a hash of the icon file (`?v=…`).
- Ribbon commands are registered before the editor bundle loads, so the first click after Office starts is not lost.
- A runtime started by a ribbon command without the pane cannot close its first dialog, so the pane is shown before any dialog opens (Windows shows the pane for every command too).
- A collapsed Word selection has no OOXML; selection checks skip it.

## Build

On macOS with Python 3.11 and Xcode command line tools:

```bash
python -m venv .venv-office
.venv-office/bin/pip install -r Office_plugin/macos/requirements-build.txt
.venv-office/bin/python -X utf8 Office_plugin/macos/build.py
```

The build writes `Office_plugin/macos/release/LaTeXSnipperOffice_<version>_macos_arm64.dmg` and its `.sha256` file. Commit both for a release. The workflow checks the SHA-256 before uploading the DMG to GitHub Releases. The version comes from the repository `VERSION` file. The app carries its own copy of the MathJax `office` resource profile (the same subset the Windows installer ships) and depends only on `requirements.txt` here.

## Tests

```bash
python -X utf8 -m pytest Office_plugin/macos/tests
cd Office_plugin/macos && npm ci && npm test
```

The Node tests cover the Word contract, the OOXML rewrites (including what must survive: neighbouring text, formatting, bookmarks, fields and section breaks), the LaTeX parser against the Windows parsing fixture, and the PowerPoint tags. They use `@xmldom/xmldom` as the DOM the browser provides in Office.

Use the [Office sample documents](tests/samples/README.md) to check whether Windows can load and update formulas saved by the macOS add-in.

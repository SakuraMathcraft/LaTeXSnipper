# LaTeXSnipper Office Add-in

Office.js add-in for Word and PowerPoint — native-feeling LaTeX equation editing, numbering, and insertion powered by the LaTeXSnipper desktop bridge.

## Workflow

1. Open the equation editor dialog from the Ribbon (Editor button) or task pane sidebar.
2. Edit with MathLive visual input, LaTeX source, and symbol palette.
3. Convert LaTeX through the desktop bridge (`POST /convert/latex` → OMML).
4. Insert as a tagged Word equation object (content control with native OMML rendering).
5. LaTeX source and numbering metadata are stored in document settings.
6. Reopen equations later for editing: Load → edit → Update in-place.

## Ribbon Commands

| Button | Action |
|---|---|
| **Editor** | Open full dialog editor with symbol panel |
| **Insert Formula** | Insert sidebar LaTeX at cursor |
| **Numbered** | Add auto-numbering to the selected equation |
| **Screenshot OCR** | Import next global LaTeXSnipper recognition result |
| **Load Selected** | Open selected equation in the dialog editor |
| **Update Selected** | Replace selected equation with sidebar content |
| **Renumber** | Renumber auto-numbered equations in document order |
| **Help** | Open built-in help documentation |

## Equation Numbering

- **Auto**: Sequential `(1)`, `(2)`, `(3)` managed by the add-in.
- **Manual**: Custom number via the `Manual #` field. Auto-number is disabled when a manual value is entered.
- **Renumber**: Updates only auto-numbered equations. Manual numbers are preserved.
- Numbered equations use a borderless 2-cell table (formula centered, number right-aligned).
- Each number content control carries a unique tag (`latexsnipper-eqn-{uuid}`) for precise targeting.

## Development

```powershell
cd office_addin
npm install
npm run dev           # Dev server on https://localhost:3000
npm run dev:word      # Sideload into Word
```

Trust the dev certificate before loading in Office:

```powershell
.\scripts\trust_vite_dev_cert.ps1 -OpenInstaller
```

Register the shared-folder catalog:

```powershell
.\scripts\register_word_catalog.ps1 -SharePath "\\YOUR-PC\office_addin"
```

Start LaTeXSnipper and enable "Office 插件" in settings before testing conversion or OCR.

## Architecture

```
Ribbon Commands
  |
  +-- Task Pane (sidebar, ~350px) — quick insert, bridge status
  +-- Dialog Editor — full editor with symbol palette + MathLive
  |
  v
LaTeXSnipper Bridge (localhost HTTP, bearer token)
  POST /convert/latex    → OMML + SVG + MathML + PNG
  POST /recognize/screenshot
  GET  /health, /config
```

- `src/taskpane/App.ts` — Task pane control hub (bridge, insertion, dialog management)
- `src/taskpane/mathliveEditor.ts` — Shared `MathLiveCore` (used by both editors)
- `src/dialog/editorDialog.ts` — Dialog editor (MathLive + complete symbol panel + structures)
- `src/office/wordInsert.ts` — Word OOXML insert / update / renumber
- `src/office/powerpointInsert.ts` — PowerPoint image insertion
- `src/services/bridgeClient.ts` — HTTP bridge client
- `src/services/equationSession.ts` — Document settings persistence

## Icons

Ribbon icons are PNG rasterized from SVG sources:

```bash
node gen_icons.mjs    # Requires sharp (npm install)
```

Outputs `icon-{name}-{16,32,80}.png` for each ribbon button.

## Document Settings

| Key | Purpose |
|---|---|
| `latexsnipper.bridgeUrl` / `bridgeToken` | Bridge connection |
| `latexsnipper.equationNumbering` | Auto-number counter |
| `latexsnipper.equationSource.{id}` | Per-equation: latex, display, numbering, numberValue |

## Packaging

- Office add-in assets live under `office_addin/`.
- Desktop bridge code lives under `src/integration/office/`.
- The add-in is installed independently from the desktop app.

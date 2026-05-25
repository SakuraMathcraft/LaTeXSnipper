# LaTeXSnipper Office Add-in

This folder contains the Office.js task pane for Word integration. The first milestone is a Word-only loop:

1. Type LaTeX in the task pane.
2. Call the LaTeXSnipper desktop Office bridge `/convert/latex` endpoint.
3. Receive OMML.
4. Insert editable Office Math into the current Word selection.

PowerPoint support will be added after the Word insertion path is stable.

## Development

```powershell
cd office_addin
npm install
npm run dev
```

Sideload `manifest.word.xml` in Word. The manifest points to:

```text
https://localhost:3000/taskpane.html
```

The task pane expects the LaTeXSnipper desktop bridge URL and token to be entered manually until the desktop UI grows an Office integration settings panel.

For the current development loop, start the bridge manually:

```powershell
E:\LaTexSnipper\office_addin\scripts\start_bridge_dev.ps1 -Port 8765 -Token dev-token
```

Then enter this in the task pane:

```text
Bridge URL: http://127.0.0.1:8765
Bridge token: dev-token
```

## Architecture

- `src/taskpane/`: task pane composition and user events.
- `src/services/`: localhost bridge client and shared service code.
- `src/office/`: Office host adapters. Word insertion logic belongs here.
- `src/styles/`: task pane styles.

The add-in does not load MathCraft OCR or local model dependencies. Recognition and conversion belong to the desktop bridge.

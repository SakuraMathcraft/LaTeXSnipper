# LaTeXSnipper Office Add-in

This folder contains the separately installed Office.js add-in for Word and PowerPoint integration. The first milestone is a Word-only loop:

1. Type LaTeX in the task pane.
2. Call the LaTeXSnipper desktop Office bridge `/convert/latex` endpoint.
3. Receive OMML.
4. Insert editable Office Math into the current Word selection.

PowerPoint support will be added after the Word insertion path is stable.

The add-in is intentionally independent from the desktop application UI. The desktop app only needs to expose a small optional localhost bridge. Add-in installation, Office version checks, manifest registration, certificates, repair, and uninstall belong to this package.

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

The task pane expects the LaTeXSnipper desktop bridge URL and token to be entered manually until the add-in installer can provision those values. The desktop UI should only grow a compact setting to enable or disable the bridge.

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

## Packaging Boundary

- Office add-in assets and installers live under `office_addin/`.
- Desktop bridge code lives under `src/integration/office/`.
- The main application should not contain Office installation wizards.
- Windows/macOS Office-specific setup should be handled by this package.

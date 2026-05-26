# LaTeXSnipper Office Add-in

This folder contains the separately installed Office.js add-in for Word and PowerPoint integration. The first milestone is a Word-only loop:

1. Type LaTeX in the task pane.
2. Call the LaTeXSnipper desktop Office bridge `/convert/latex` endpoint.
3. Receive OMML.
4. Insert editable Office Math into the current Word selection.

PowerPoint support will be added after the Word insertion path is stable.

The add-in is intentionally independent from the desktop application UI. The desktop app only needs to expose a small optional localhost bridge. Add-in installation, Office version checks, manifest registration, certificates, repair, and uninstall belong to this package.

The formula editor uses MathLive and keeps a synchronized LaTeX text view for debugging and manual edits. The keyboard routing logic mirrors the desktop math workbench: arrow keys are forwarded to MathLive navigation commands, and the virtual keyboard can be toggled from the task pane.

Word and PowerPoint both expose a `LaTeXSnipper` Ribbon tab through separate manifests:

- `manifest.word.xml`
- `manifest.powerpoint.xml`

The Ribbon uses Office add-in commands. Editor opens the task pane; Insert, Screenshot OCR, edit-selected, update-selected, and renumber publish commands that the task pane executes.

Word insertion creates a tagged LaTeXSnipper equation object: the visible formula is OMML, while the original LaTeX source is saved in Office document settings. This is the foundation for the later edit-selected-formula flow.

## Development

```powershell
cd office_addin
npm install
npm run dev
```

The manifest points to:

```text
https://localhost:3000/taskpane.html
```

Trust the local development certificate before opening the add-in in Word:

```powershell
E:\LaTexSnipper\office_addin\scripts\trust_vite_dev_cert.ps1 -OpenInstaller
```

Install the generated certificate for the current user into `Trusted Root Certification Authorities`, confirm the Windows security prompt, then restart Word. A browser warning such as `NET::ERR_CERT_AUTHORITY_INVALID` means Word/WebView2 will reject the add-in.

Register the shared-folder catalog for Word:

```powershell
E:\LaTexSnipper\office_addin\scripts\register_word_catalog.ps1 -SharePath "\\DESKTOP-V3G05D9\office_addin"
```

Use the UNC path shown in the Windows folder sharing dialog. Close all Office apps after registration. Reopen Word and load the add-in from the Office add-ins entry, usually one of:

- `Insert -> Add-ins / My Add-ins -> Shared Folder`
- `Developer -> Add-ins`

Do not use `Developer -> XML Expansion Pack`; that is not the Office.js Web Add-in loader.

The task pane auto-discovers the local LaTeXSnipper bridge from `http://127.0.0.1:8765/config`, so the bridge URL and token should not be typed by users during normal testing.

Start LaTeXSnipper itself and enable `Office 插件` in settings before testing conversion or Screenshot OCR. The add-in discovers the local bridge and token automatically.

For the current development loop, sideload Word with:

```powershell
npm run dev:word
```

This starts the Vite dev server when needed, checks whether the active bridge supports Screenshot OCR, and sideloads Word.

The ribbon icon source is `public/assets/ribbon-icons.svg`; Office manifests still reference PNG assets because desktop Office ribbon images require fixed-size bitmap URLs.

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


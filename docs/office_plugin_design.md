# Windows Native Office Plugin Target Architecture

`office_plugin` is the active LaTeXSnipper Office architecture. It targets Microsoft 365 Apps, Office 2016, Office 2019, Office 2021, and Office 2024 on Windows desktop. Release artifacts must distinguish 64-bit Office from 32-bit Office and may be produced as Inno Setup EXE or MSI installers.

## Product Goals

- Persistent native Ribbon in Word and PowerPoint.
- No web manifest, sideload catalog, tenant deployment requirement, or localhost HTTPS static site.
- Word insertion through native OMML first, with LaTeXSnipper OLE formula objects added as the durable editable object model.
- PowerPoint insertion through rendered compatibility images first, with LaTeXSnipper OLE formula objects added for double-click editing and source persistence.
- Per-formula metadata stored with the document object: LaTeX source, display mode, numbering mode, render options, object identity, and schema version.
- Local rendering and conversion through the desktop Bridge, defaulting to `http://127.0.0.1:28765/`.

## Modules

| Layer | Responsibility |
|---|---|
| VSTO host shell | Word and PowerPoint startup, Ribbon registration, Office lifetime hooks |
| Host workflow core | Editor command handling, Bridge calls, insertion/update/delete workflows |
| Bridge client | HTTP boundary to the LaTeXSnipper desktop Bridge |
| Editor session | Formula editor state and command surface |
| Rendering pipeline | Engine-neutral rendering requests and results |
| OLE formula object | Durable embedded object, double-click activation, redraw, metadata persistence |
| Installer | VSTO/OLE registration, Office bitness detection, runtime checks, uninstall cleanup |

## Bridge Contract

The native plugin uses the desktop Bridge endpoint:

```text
http://127.0.0.1:28765/
```

The Word host first calls `/config` to obtain the current Bridge URL and bearer token, so normal users do not fill these values manually. The following environment variables are development overrides only:

```text
LATEXSNIPPER_OFFICE_BRIDGE_URL
LATEXSNIPPER_OFFICE_BRIDGE_TOKEN
```

The first implemented conversion flow is:

```text
POST /convert/latex
payload: { latex, display: true, targets: ["omml"] }
result:  { latex, display, warnings, omml }
```

## Word Workflow

1. Ribbon is loaded by the VSTO shell.
2. The VSTO shell creates a native status task pane for progress, current formula context, and non-blocking errors.
3. Ribbon insert commands provide separate inline, display, and numbered formula entry points.
4. Insert commands send LaTeX to the Bridge.
5. The Bridge returns OMML.
6. The Word adapter wraps OMML into Flat OPC and inserts it through Word automation.
7. The inserted content is wrapped in a Word content control tagged as `latexsnipper-eq-{equationId}`.
8. Numbered formulas also receive a number content control tagged as `latexsnipper-eqn-{equationId}` inside a borderless Word table.
9. Formula metadata is saved into Word document variables under `LaTeXSnipper.Equation.{equationId}`.

Managed formula load and delete must resolve the selected content control first, then operate through the saved metadata. Update is not a separate Ribbon command: loading an existing formula opens the editor in update mode, and confirming the editor updates the selected formula in place. Numbering comes next and must attach to native Word content or LaTeXSnipper OLE objects, not to task panes or transient UI state.

## Localization

Ribbon labels, tooltips, dialog buttons, and user-facing errors must go through a host-local text provider. The first implementation uses current UI culture to return English or Chinese text. New commands should add text keys instead of hard-coded visible strings.

## PowerPoint Workflow

PowerPoint starts with rendered image insertion through the shared Bridge/rendering contracts. Inline and display formulas should be rendered as high-DPI images and cropped to the visible formula bounds before insertion. Numbered formulas use a formula image plus number layout and are not cropped as a single image object.

PowerPoint automatic numbering is intentionally limited. A session counter may increment newly inserted numbered formulas, but PowerPoint cannot safely repair arbitrary slide order like Word document fields. Users must be able to manually fill number text for numbered formulas, and manual numbering is the supported first implementation. Renumber All and document-wide automatic numbering repair are out of scope for the first PowerPoint host.

OLE object insertion follows after the Word object identity model is stable.

## Installer Requirements

- Detect installed Office bitness and write the matching 32-bit or 64-bit registration.
- Install/register Word and PowerPoint VSTO plugins.
- Install/register the LaTeXSnipper OLE formula object.
- Check VSTO Runtime and WebView2 Runtime only when required by the selected host/editor implementation.
- Remove VSTO, OLE, shortcut, and temporary registration state during uninstall.

## Implementation Order

1. Word VSTO Ribbon persistent display.
2. Bridge OMML conversion and Word insertion.
3. Managed Word formula metadata, load, update, delete.
4. Word numbering and renumbering.
5. PowerPoint image insertion through shared contracts.
6. OLE formula object identity and persistence.
7. Double-click editing and in-place updates.
8. 32-bit/64-bit installer packaging.

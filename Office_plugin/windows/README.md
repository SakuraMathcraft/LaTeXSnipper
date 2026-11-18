# LaTeXSnipper Office Plugin for Windows

Released Windows VSTO add-in for Microsoft Word and PowerPoint. It inserts and maintains LaTeXSnipper OLE formulas and provides native Word OMML and PowerPoint PNG alternatives. Formula editing and rendering are fully local; screenshot recognition uses the desktop Automation API as an ordinary authenticated client.

OLE formulas use local MathJax layout and EMF vector presentations. Complete LaTeX source, rendering options, numbering information, and object identity are stored with each managed formula.

## Supported Office Versions

- Microsoft 365 Apps (Current or Monthly Enterprise Channel)
- Office 2024 / 2021 / 2019 (Retail or Volume License)
- Office LTSC 2024 / 2021
- 32-bit and 64-bit Windows desktop Office
- Requires .NET Framework 4.8, Visual Studio Tools for Office Runtime 10.0, and WebView2 Runtime

Office 2016 is not officially supported (requires manual .NET 4.8 and WebView2 installation).

Word OMML conversion uses the stylesheets supplied with the running Word installation. They are loaded only when conversion is requested; missing stylesheets do not prevent the add-in from starting. See [Office stylesheet troubleshooting](../../docs/faq.md#why-does-word-omml-conversion-report-a-missing-office-stylesheet).

## Features

### Word

- OLE formula insertion and update
- Native OMML formula insertion (inline, display, numbered)
- Load, update, and delete managed formulas
- Chapter/section-aware automatic numbering, references, boundaries, and Renumber All
- In-place conversion between managed OLE and OMML formulas, plus explicit conversion of selected native Word OMML formulas to LaTeXSnipper OLE
- Parsing of `$...$`, `\(...\)`, `$$...$$`, and `\[...\]` LaTeX in the selected range or main document body, including table cells
- Selected or document-wide reset to the configured formula style and natural size
- Screenshot OCR via Automation API

### PowerPoint

- OLE and PNG formula insertion
- Native inline equations at a text-box caret, using MathJax MathML and optional host-size inheritance
- Load, update, and delete managed formulas
- In-place conversion of selected managed formulas between OLE and PNG
- Selected or presentation-wide reset to the configured formula style and natural size
- User-resized formulas preserve their scale when updated
- Screenshot OCR via Automation API

### Shared

- Double-click editing and independent cross-document copies of LaTeXSnipper OLE formulas
- Native MathType insertion and conversion in both hosts, including native numbering fields for Word. With MathType selected as the insertion backend, double-click a native MathType equation or use Load Selected to edit it in LaTeXSnipper
- Reusable WebView2/MathLive formula editor
- 18-category shared symbol and formula library
- Chinese and English Ribbon, task pane, editor, settings, and help
- Status task pane with connection test and shared visual/source formula editing

## Project Layout

Desktop and Office share pinned MathJax 4.1.3 with independent resource profiles and asynchronous conversion. See [runtime maintenance and verification](../../scripts/mathjax/README.md) and the [current formula workflows and metadata](../../docs/office_plugin_formula_workflows.md).

Word and PowerPoint convert between LaTeXSnipper OLE and native MathType objects without activating MathType or calling its SDK. Word preserves the formula mode, paragraph formatting, and existing numbering fields and references. PowerPoint preserves the original display width, height, position, and layer. The MathType insertion backend uses the same package writers. Double-clicks follow the current host setting. Other backends leave native MathType activation to Office, which requires an installed MathType server.

| Path (relative to this directory) | Role |
|---|---|
| `src/LaTeXSnipper.OfficePlugin.Abstractions` | Stable contracts shared by hosts, renderer, editor, and automation client |
| `src/LaTeXSnipper.OfficePlugin.Automation` | Authenticated Automation API client and local connection-file discovery |
| `src/LaTeXSnipper.OfficePlugin.Rendering` | Engine-neutral render pipeline for MathJax intermediate rendering, OLE presentation generation, and PNG rendering |
| `src/LaTeXSnipper.OfficePlugin.Editor` | Windows formula editor session boundary |
| `../shared/EditorAssets` | Formula editor, symbol and template catalogs, and bundled browser assets |
| `../shared/mathjax` | MathJax typography adapter |
| `hosts/WordAddIn` | Word workflows: Ribbon, OLE/OMML insertion, numbering, metadata, controller |
| `hosts/WordVstoAddIn` | Thin VSTO shell loaded by Word |
| `hosts/PowerPointAddIn` | PowerPoint workflows: Ribbon, OLE/PNG insertion, metadata, controller |
| `hosts/PowerPointVstoAddIn` | Thin VSTO shell loaded by PowerPoint |
| `tests/LaTeXSnipper.OfficePlugin.MetadataSafety.Tests` | Deterministic metadata storage and identity tests |
| `tests/LaTeXSnipper.OfficePlugin.Typography.Tests` | Typography contracts, sizes, symbol assets, and OMML mapping |
| `tests/LaTeXSnipper.OfficePlugin.WordParsingE2E` | Real-Word OMML/OLE parsing, formatting, conversion, and persistence |
| `tests/LaTeXSnipper.OfficePlugin.PowerPointE2E` | Real-PowerPoint text insertion, shape round trips, and batch failure handling |
| `tests/OfficeE2E` | Optional checks against an installed MathType editing server; excluded from product assemblies |
| `tests/editor-browser` | Playwright tests of the Windows Word and PowerPoint UI with a simulated WebView2 bridge |
| `installer/` | Inno Setup installer and release build entry point |
| `tools/` | Build, installer, and code analysis entry points |
| `hosts/OleFormulaObjectNative/` | Native C++ COM/OLE in-proc handler DLL registered as the Office formula object for 32-bit and 64-bit Office |

Shared libraries target `net48;net9.0`. Office hosts target .NET Framework 4.8. The native OLE handler is built for x64 and Win32 Office.

## Build

The release build requires Visual Studio 2022 or newer with Office/SharePoint and Visual C++ ATL workloads, .NET 9 SDK, and Inno Setup 6 or newer. Run from the repository root:

```batch
Office_plugin\windows\installer\build.bat Release
```

The build reads the shared product version from the repository `VERSION` file.

Output: `Office_plugin\windows\release\LaTeXSnipperOffice_<version>_windows_x86_64.exe` and its SHA-256 file. The release workflow validates and publishes this locally built installer.

Run the installer as administrator. Close Word and PowerPoint before installation, upgrade, or removal.

## Tests

Run:

```powershell
dotnet test Office_plugin/windows/LaTeXSnipper.OfficePlugin.slnx -c Release
```

The deterministic tests validate typography, current-schema writes, copied metadata identity, corrupt metadata rejection, and document identity without starting Office. See the [shared editor build and unit tests](../shared/editor/README.md).

Word integration tests also verify that inserting, parsing, formatting, and converting formulas preserve neighboring MathType objects and existing superscript, subscript, and baseline formatting in body paragraphs and table cells, including save/reopen. Formula formatting must be confined to the target formula, its generated numbering/reference fields, or an empty typing selection; it must not reset surrounding paragraph content.

### Editor browser tests

Use the installed Microsoft Edge browser to test the editor, settings, status pane and help for both hosts. Playwright serves local assets and simulates the WebView2 bridge. From the repository root:

```powershell
npm --prefix Office_plugin/windows/tests/editor-browser ci
npm --prefix Office_plugin/windows/tests/editor-browser test
```

Use the real Office integration tests below to verify native rendering and document editing.

### Real Office integration

Build the installer or the managed solution and native handler first, then close Word and PowerPoint. Run from 64-bit PowerShell:

```powershell
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1
# Include native MathType conversion and save/reopen checks:
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -IncludeMathType
# Word conversion checks only; native-edit verification additionally requires MathType:
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Ole -WordMathTypeOnly
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Ole -WordMathTypeOnly -WordMathTypeNativeEdit
# PowerPoint conversion checks only; native-edit verification additionally requires MathType:
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType -PowerPointMathTypeNativeEdit
# Word OMML only, without temporary OLE registration:
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Omml
# PowerPoint batch failure and retry only, without OLE:
Office_plugin\windows\tests\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Batch
```

The unified runner defaults to Release binaries, Word OMML/OLE, and the full PowerPoint suite. Use `-Configuration Debug`, `-WordBackend Ole`, or `-HostScope` to select a smaller run. Evidence goes to a unique temporary directory, or `-OutputDirectory`. OLE runs require 64-bit Click-to-Run Office and temporarily register the built handler under HKCU; valid existing user registration is refused; original values are restored, and the runner removes only the roots it creates. The plugin installer itself registers the OLE handler under HKLM.

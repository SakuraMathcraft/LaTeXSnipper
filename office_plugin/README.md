# LaTeXSnipper Office Plugin

Released Windows VSTO add-in for Microsoft Word and PowerPoint. It inserts and maintains LaTeXSnipper OLE formulas and provides native Word OMML and PowerPoint PNG alternatives. Formula editing and rendering are fully local; screenshot recognition uses the desktop Automation API as an ordinary authenticated client.

OLE formulas use local MathJax layout and EMF vector presentations. Complete LaTeX source, rendering options, numbering information, and object identity are stored with each managed formula.

## Supported Office Versions

- Microsoft 365 Apps (Current or Monthly Enterprise Channel)
- Office 2024 / 2021 / 2019 (Retail or Volume License)
- Office LTSC 2024 / 2021
- 32-bit and 64-bit Windows desktop Office
- Requires .NET Framework 4.8 and WebView2 Runtime

Office 2016 is not officially supported (requires manual .NET 4.8 and WebView2 installation).

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
- Conversion between LaTeXSnipper OLE and native MathType objects without MathType installed; Word numbered formulas are excluded. MathType is required for native double-click editing
- Reusable WebView2/MathLive formula editor
- 18-category shared symbol and formula library
- Chinese and English Ribbon, task pane, editor, settings, and help
- Status task pane with connection test and shared visual/source formula editing

## Project Layout

Desktop and Office share pinned MathJax 4.1.3 with independent resource profiles and asynchronous conversion. See [runtime maintenance and verification](../tools/mathjax/README.md) and the [current formula workflows and metadata](../docs/office_plugin_formula_workflows.md).

Word and PowerPoint convert between LaTeXSnipper OLE and native MathType objects without activating MathType or calling its SDK. PowerPoint preserves the original display width, height, position and layer directly. Double-click editing of native MathType objects requires MathType. Conversion has not yet been verified in a clean Office environment without MathType.

| Path | Role |
|---|---|
| `src/LaTeXSnipper.OfficePlugin.Abstractions` | Stable contracts shared by hosts, renderer, editor, and automation client |
| `src/LaTeXSnipper.OfficePlugin.Automation` | Authenticated Automation API client and local connection-file discovery |
| `src/LaTeXSnipper.OfficePlugin.Rendering` | Engine-neutral render pipeline for MathJax intermediate rendering, OLE presentation generation, and PNG rendering |
| `src/LaTeXSnipper.OfficePlugin.Editor` | Formula editor session boundary |
| `hosts/WordAddIn` | Word workflows: Ribbon, OLE/OMML insertion, numbering, metadata, controller |
| `hosts/WordVstoAddIn` | Thin VSTO shell loaded by Word |
| `hosts/PowerPointAddIn` | PowerPoint workflows: Ribbon, OLE/PNG insertion, metadata, controller |
| `hosts/PowerPointVstoAddIn` | Thin VSTO shell loaded by PowerPoint |
| `tests/LaTeXSnipper.OfficePlugin.MetadataSafety.Tests` | Deterministic metadata storage and identity tests |
| `tests/LaTeXSnipper.OfficePlugin.Typography.Tests` | Typography contracts, sizes, symbol assets, and OMML mapping |
| `tests/LaTeXSnipper.OfficePlugin.WordParsingE2E` | Real-Word OMML/OLE parsing, formatting, conversion, and persistence |
| `tests/LaTeXSnipper.OfficePlugin.PowerPointE2E` | Real-PowerPoint text insertion, shape round trips, and batch failure handling |
| `tests/OfficeE2E` | Optional checks against an installed MathType editing server; excluded from product assemblies |
| `installer/` | Inno Setup installer and release build entry point |
| `tools/` | Build, installer, metadata, and Word parsing test entry points |
| `hosts/OleFormulaObjectNative/` | Native C++ COM/OLE in-proc handler DLL registered as the Office formula object for 32-bit and 64-bit Office |

Shared libraries target `net48;net9.0`. Office hosts target .NET Framework 4.8. The native OLE handler is built for x64 and Win32 Office.

## Build

The release build requires Visual Studio 2022 or newer with Office/SharePoint and Visual C++ ATL workloads, .NET 9 SDK, and Inno Setup 6 or newer. Run from the repository root:

```batch
office_plugin\installer\build.bat Release
```

The build reads the shared product version from the repository `VERSION` file.

Output: `office_plugin\release\LaTeXSnipperOffice_<version>_amd64.exe` and its SHA-256 file. The release workflow validates and publishes this locally built installer.

Run the installer as administrator. Close Word and PowerPoint before installation, upgrade, or removal.

## Tests

Run:

```powershell
dotnet test office_plugin/LaTeXSnipper.OfficePlugin.slnx -c Release
```

The deterministic tests validate typography, current-schema writes, copied metadata identity, corrupt metadata rejection, and document identity without starting Office. Shared editor tests are documented in [tools/office-editor](../tools/office-editor/README.md).

### Real Office integration

Build the installer or the managed solution and native handler first, then close Word and PowerPoint. Run from 64-bit PowerShell:

```powershell
office_plugin\tools\Test-OfficeTypographyE2E.ps1
# Include native MathType conversion and save/reopen checks:
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -IncludeMathType
# Word conversion checks only; native-edit verification additionally requires MathType:
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Ole -WordMathTypeOnly
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Ole -WordMathTypeOnly -WordMathTypeNativeEdit
# PowerPoint conversion checks only; native-edit verification additionally requires MathType:
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode MathType -PowerPointMathTypeNativeEdit
# Word OMML only, without temporary OLE registration:
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope Word -WordBackend Omml
# PowerPoint batch failure and retry only, without OLE:
office_plugin\tools\Test-OfficeTypographyE2E.ps1 -HostScope PowerPoint -PowerPointMode Batch
```

The unified runner defaults to Release binaries, Word OMML/OLE, and the full PowerPoint suite. Use `-Configuration Debug`, `-WordBackend Ole`, or `-HostScope` to select a smaller run. Evidence goes to a unique temporary directory, or `-OutputDirectory`. OLE runs require 64-bit Click-to-Run Office and temporarily register the built handler under HKCU; valid existing user registration is refused; original values are restored, and the runner removes only the roots it creates. The plugin installer itself registers the OLE handler under HKLM.

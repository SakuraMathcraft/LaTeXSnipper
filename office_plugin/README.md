# LaTeXSnipper Office Plugin

Released Windows VSTO add-in for Microsoft Word and PowerPoint. It inserts and maintains LaTeXSnipper OLE formulas, provides native Word OMML and PowerPoint PNG alternatives, and communicates with the LaTeXSnipper desktop client through the local Bridge at `127.0.0.1:28765`.

OLE formulas use local MathJax layout and EMF vector presentations. Formula source, rendering options, numbering information, and object identity are stored with each managed formula.

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
- Automatic/custom numbering, deletion, and Renumber All
- Screenshot OCR via desktop Bridge

### PowerPoint
- OLE and PNG formula insertion
- Load, update, and delete managed formulas
- User-resized OLE formulas preserve their scale when updated
- Screenshot OCR via desktop Bridge

### Shared
- Reusable WebView2/MathLive formula editor
- 18-category shared symbol and formula library
- Chinese and English Ribbon, task pane, editor, settings, and help
- Status task pane with connection test and formula preview

## Project Layout

| Path | Role |
|---|---|
| `src/LaTeXSnipper.OfficePlugin.Abstractions` | Stable contracts shared by hosts, renderer, editor, Bridge |
| `src/LaTeXSnipper.OfficePlugin.Bridge` | HTTP boundary to the desktop Bridge |
| `src/LaTeXSnipper.OfficePlugin.Rendering` | Engine-neutral render pipeline for MathJax intermediate rendering, OLE presentation generation, and PNG rendering |
| `src/LaTeXSnipper.OfficePlugin.Editor` | Formula editor session boundary |
| `hosts/WordAddIn` | Word workflows: Ribbon, OLE/OMML insertion, numbering, metadata, controller |
| `hosts/WordVstoAddIn` | Thin VSTO shell loaded by Word |
| `hosts/PowerPointAddIn` | PowerPoint workflows: Ribbon, OLE/PNG insertion, metadata, controller |
| `hosts/PowerPointVstoAddIn` | Thin VSTO shell loaded by PowerPoint |
| `installer/` | Inno Setup installer and release build entry point |
| `tools/` | VSTO build and installer cleanup support |
| `hosts/OleFormulaObjectNative/` | Native C++ COM/OLE in-proc handler DLL registered as the Office formula object for 32-bit and 64-bit Office |

Shared libraries target `net48;net9.0`. Office hosts target .NET Framework 4.8. The native OLE handler is built for x64 and Win32 Office.

## Build

The release build requires Visual Studio 2022 with Office/SharePoint and Visual C++ ATL workloads, .NET 9 SDK, and Inno Setup 6. Run from the repository root:

```batch
office_plugin\installer\build.bat 2.3.2 Release
```

Output: `office_plugin\dist\OfficePluginSetup-2.3.2.exe`

Run the installer as administrator. Close Word and PowerPoint before installation, upgrade, or removal.

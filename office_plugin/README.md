# LaTeXSnipper Native Office Plugin

Native Windows VSTO add-in for Word and PowerPoint. Communicates with the LaTeXSnipper desktop client through a local Bridge at `127.0.0.1:28765`.

## Supported Office Versions

- Microsoft 365 Apps (Current or Monthly Enterprise Channel)
- Office 2024 / 2021 / 2019 (Retail or Volume License)
- Office LTSC 2024 / 2021
- 32-bit and 64-bit Windows desktop Office
- Requires .NET Framework 4.8 and WebView2 Runtime

Office 2016 is not officially supported (requires manual .NET 4.8 and WebView2 installation).

## Features

### Word
- Native OMML formula insertion (inline, display, numbered)
- Load, update, and delete managed formulas
- Automatic numbering and Renumber All
- Screenshot OCR via desktop Bridge

### PowerPoint
- High-DPI PNG formula image insertion
- Load and delete managed formulas
- Screenshot OCR via desktop Bridge
- Inserted formulas replace the original at the same position

### Shared
- WebView2-based MathLive formula editor (task pane + standalone window)
- 16-category symbol library (Greek, structures, delimiters, calculus, linear algebra, relations, operators, arrows, sets, functions, probability, chemistry, physics, accents, misc)
- Bilingual Ribbon (Chinese / English) with placeholder localization
- Status task pane with connection test and formula preview

## Project Layout

| Path | Role |
|---|---|
| `src/LaTeXSnipper.OfficePlugin.Abstractions` | Stable contracts shared by hosts, renderer, editor, Bridge |
| `src/LaTeXSnipper.OfficePlugin.Bridge` | HTTP boundary to the desktop Bridge |
| `src/LaTeXSnipper.OfficePlugin.Rendering` | Engine-neutral render pipeline (reserved for future OLE renderer) |
| `src/LaTeXSnipper.OfficePlugin.Editor` | Formula editor session boundary |
| `hosts/WordAddIn` | Word host workflow core: Ribbon XML, OMML builder, controller, editor |
| `hosts/WordVstoAddIn` | Thin VSTO shell loaded by Word |
| `hosts/PowerPointAddIn` | PowerPoint host workflow core: Ribbon XML, PNG image insertion, controller, editor |
| `hosts/PowerPointVstoAddIn` | Thin VSTO shell loaded by PowerPoint |
| `installer/` | Inno Setup 6 installer script, build batch, assets |
| `tools/` | PowerShell registration and build scripts |
| `hosts/OleFormulaObject/` | OLE/COM formula object scaffold (next version) |

Shared libraries target `net48;net9.0`. Host projects target `net48` (VSTO requirement). VSTO projects require Visual Studio MSBuild; they are excluded from the `.slnx` solution file.

## Build

### Shared libraries

```powershell
cd office_plugin
dotnet build LaTeXSnipper.OfficePlugin.slnx
```

### VSTO shells (requires Visual Studio 2022 with Office/SharePoint workload)

MSBuild is auto-discovered via `vswhere` in the registration scripts. No hardcoded paths needed:

```powershell
.\tools\Register-WordVstoAddIn.ps1 -Configuration Release -SkipCertificateTrust -SkipVstoInstaller -SkipOfficeRegistration
.\tools\Register-PowerPointVstoAddIn.ps1 -Configuration Release -SkipCertificateTrust -SkipVstoInstaller -SkipOfficeRegistration
```

### Installer

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```batch
cd installer
build.bat 2.3.2 Release
```

The build script discovers Inno Setup from `PATH` or standard install locations and exports the VSTO signing certificate to `installer\vsto-signing.cer` before packaging.

If the VSTO shell build and certificate export have already completed, the installer script can also be run directly with `ISCC.exe` available on `PATH`:

```powershell
ISCC.exe /DVersion=2.3.2 /DConfig=Release installer\setup.iss
```

Output: `dist\OfficePluginSetup-2.3.2.exe`

**Important:** ISCC 6.5.4 does not correctly embed the `requireAdministrator` manifest. Run the installer by right-clicking → "Run as administrator".

## Architecture Rule

This directory is the active Office product architecture. New Office behavior lands in the VSTO hosts and shared modules here.

# LaTeXSnipper Native Office Plugin

`office_plugin` is the Windows-native Office integration line. It is the only active Office product architecture.

## Goals

- Persistent Word and PowerPoint Ribbon without sideload manifests or Microsoft 365 tenant deployment.
- Word OMML insertion for native Word editability, with Load Selected, in-place update, Delete Selected, Auto Number, and Renumber All.
- Native status task pane for command progress, formula context, and non-blocking errors.
- LaTeXSnipper OLE formula objects for MathType/AxMath-style double-click editing and self-rendered display.
- PowerPoint image insertion for compatibility and OLE formula objects for editable native formulas.
- Formula metadata stored with each object: LaTeX source, display mode, numbering mode, render engine, schema version.
- Word managed formulas use content-control tags plus document variables for durable identity and metadata.
- Ribbon and dialog text goes through a host-local English/Chinese text provider.
- Local TeX rendering pipeline. The implementation may choose KaTeX, MathJax, MathLive, or a later native renderer behind the same contract.

## Project Layout

| Path | Role |
|---|---|
| `src/LaTeXSnipper.OfficePlugin.Abstractions` | Stable contracts shared by hosts, renderer, editor, Bridge, and OLE object |
| `src/LaTeXSnipper.OfficePlugin.Bridge` | HTTP boundary to the LaTeXSnipper desktop Bridge, defaulting to `http://127.0.0.1:28765/` |
| `src/LaTeXSnipper.OfficePlugin.Rendering` | Engine-neutral render pipeline |
| `src/LaTeXSnipper.OfficePlugin.Editor` | Formula editor session boundary |
| `hosts/WordAddIn` | Reusable Word host workflow core: Ribbon XML, status pane, MathLive editor command, Bridge OMML insertion |
| `hosts/WordVstoAddIn` | Thin VSTO shell loaded by Word; creates the task pane and delegates commands to `hosts/WordAddIn` |
| `hosts/PowerPointAddIn` | VSTO PowerPoint host scaffold notes |
| `hosts/OleFormulaObject` | COM/OLE formula object scaffold notes |

The compileable projects target `net48;net9.0`: `net48` fits VSTO-era Office hosts, while `net9.0` keeps the shared contracts usable from modern helper processes and tests. VSTO and OLE projects are intentionally not faked here; they need Visual Studio Office tooling and COM registration work in the next phase.

## Build

```powershell
cd office_plugin
dotnet build .\LaTeXSnipper.OfficePlugin.slnx
```

The VSTO shell requires Visual Studio Office tooling and should be built with Visual Studio 2022 MSBuild:

```powershell
& "D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" .\hosts\WordVstoAddIn\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj /restore
```

Visual Studio itself does not need to be opened for the local Word plugin loop.
After the signing certificate exists in
`hosts/WordVstoAddIn/LaTeXSnipper.OfficePlugin.WordVstoAddIn.user.props`, run:

```powershell
.\tools\Register-WordVstoAddIn.ps1
.\tools\Test-WordVstoAddIn.ps1
```

## Architecture Rule

New Office product behavior lands here. Do not add dependencies on sideload catalogs, localhost HTTPS static sites, or retired Office packaging paths.

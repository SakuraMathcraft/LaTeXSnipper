# LaTeXSnipper Office Plugin Installer

Uses [Inno Setup 6](https://jrsoftware.org/isinfo.php) to produce a standalone Windows installer.

## Prerequisites

- Inno Setup 6+ (install from https://jrsoftware.org/isdl.php)
- Visual Studio 2022 with Office/SharePoint development workload (for VSTO MSBuild)
- .NET 9.0 SDK (for dotnet build of shared libraries)

## Build

```batch
cd office_plugin\installer
build.bat 2.3.2 Release
```

Output: `office_plugin\dist\OfficePluginSetup-2.3.2.exe`

## What the installer does

1. Pre-checks VSTO Runtime 10.0, aborts with a download link if missing
2. Copies Word and PowerPoint VSTO files to the chosen directory
3. Installs the signing certificate to both Root and Trusted Publisher stores
4. Writes HKLM registry keys with `|vstolocal` manifest URIs (versionless + Office 16.0 + WOW6432Node for 32/64-bit)
5. Cleans stale HKCU VSTO metadata, resiliency, and uninstall entries left over from previous installs
6. Runs `VSTOInstaller.exe /Install` for each add-in (creates per-user SolutionMetadata for the installing user)
7. Promotes VSTO security inclusion entries from HKCU to HKLM (trusts the add-in for all machine users, prevents per-user re-install)
8. Uninstaller removes all files and registry keys, plus cleans per-user and per-machine VSTO metadata and Office resiliency

## Version convention

The installer version follows the main LaTeXSnipper client version (`2.3.2`).

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
4. Writes HKLM registry keys (versionless + Office 16.0 + WOW6432Node for 32/64-bit)
5. Clears stale ClickOnce cache, HKCU entries, VSTO metadata, and Office resiliency
6. Runs `VSTOInstaller.exe /Uninstall` then `/Install` for both add-ins
7. Uninstaller reverses all steps except certificate removal (harmless to leave)

## Version convention

The installer version follows the main LaTeXSnipper client version (`2.3.2`).

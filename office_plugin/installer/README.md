# LaTeXSnipper Office Plugin Installer

Uses [Inno Setup 6](https://jrsoftware.org/isinfo.php) to produce a standalone Windows installer.

## Prerequisites

- Inno Setup 6+ (install from https://jrsoftware.org/isdl.php)
- Visual Studio 2022 with Office/SharePoint development workload (for VSTO MSBuild)
- Visual Studio 2022 Visual C++ ATL components (for the native OLE formula object)
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
5. Cleans stale Office-plugin VSTO metadata, resiliency, and uninstall entries left over from previous installs
6. Writes VSTO security inclusion entries to HKLM and to the installing user's HKCU
7. Registers native x64 and x86 OLE formula-object in-process handlers for matching Office bitness
8. Uninstaller removes all files and plugin registry keys, plus cleans per-user and per-machine VSTO metadata, Office resiliency, and OLE formula-object registration

The installer does not run `VSTOInstaller.exe /Install`; registration is the explicit HKLM Addins keys plus VSTO trust entries above. Cleanup matches Office-plugin identifiers only and does not remove the LaTeXSnipper desktop client registry keys.

## Version convention

The installer version follows the main LaTeXSnipper client version (`2.3.2`).

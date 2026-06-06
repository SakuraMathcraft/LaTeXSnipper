# LaTeXSnipper Office Plugin Installer

Produces the released Word and PowerPoint plugin installer with Inno Setup 6.

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

## Installation Responsibilities

1. Pre-checks VSTO Runtime 10.0, aborts with a download link if missing
2. Copies Word and PowerPoint VSTO files to the chosen directory
3. Installs the signing certificate to both Root and Trusted Publisher stores
4. Writes HKLM registry keys with `|vstolocal` manifest URIs (versionless + Office 16.0 + WOW6432Node for 32/64-bit)
5. Removes plugin-owned registration and cache data from previous installations
6. Writes VSTO security inclusion entries to HKLM and to the installing user's HKCU
7. Registers native x64 and x86 OLE formula-object in-process handlers for matching Office bitness
8. Uninstaller removes all files and plugin registry keys, plus cleans per-user and per-machine VSTO metadata, Office resiliency, and OLE formula-object registration

Registration uses explicit Office add-in keys and VSTO trust entries. Cleanup is restricted to Office-plugin identifiers and does not remove LaTeXSnipper desktop client settings.

## Version convention

The installer version follows the main LaTeXSnipper client version (`2.3.2`).

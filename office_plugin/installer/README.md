# LaTeXSnipper Office Plugin Installer

Uses [Inno Setup 6](https://jrsoftware.org/isinfo.php) to produce a standalone Windows installer.

## Prerequisites

- Inno Setup 6+ (install from https://jrsoftware.org/isdl.php)
- Visual Studio 2022 with Office/SharePoint development workload (for VSTO MSBuild)
- .NET 9.0 SDK (for dotnet build of shared libraries)

## Build

```batch
cd office_plugin\installer
build.bat 1.2.3 Release
```

Or pass no args for defaults (`0.0.0` Debug):

```batch
build.bat
```

Output appears in `office_plugin\dist\`.

## CI (GitHub Actions)

```yaml
- name: Build Office plugin installer
  run: |
    choco install innosetup -y
    cd office_plugin/installer
    build.bat ${{ github.ref_name }} Release
```

## What the installer does

1. Copies Word and PowerPoint VSTO files to `%ProgramFiles%\LaTeXSnipper\OfficePlugin\`
2. Installs the code-signing certificate to Trusted Publisher store
3. Writes registry keys for both Word and PowerPoint (HKLM, versionless + Office 16.0 + WOW6432Node)
4. Runs VSTOInstaller.exe silently for both add-ins
5. Uninstaller removes all files, registry keys, and unregisters VSTO

## Version convention

The installer version follows the main LaTeXSnipper client version (e.g., `1.2.3`).

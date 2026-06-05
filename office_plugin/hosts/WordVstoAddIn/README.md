# WordVstoAddIn Shell

This project is the thin VSTO shell that Word loads. It keeps Office-specific startup, Ribbon extensibility, and VSTO registration metadata separate from the reusable `hosts/WordAddIn` workflow code.

Build this project with Visual Studio 2022 MSBuild, not the .NET SDK CLI:

```powershell
& "D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe" .\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj /restore
```

Visual Studio does not need to be opened for local development. From
`office_plugin`, use the CLI registration script after creating the local
manifest-signing certificate:

```powershell
.\tools\Register-WordVstoAddIn.ps1
```

The script builds the VSTO shell, trusts the current-user dev signing
certificate for VSTO/ClickOnce, registers Word add-in keys for Office 16.0 and
the versionless Office path, and runs `VSTOInstaller.exe` silently.

VSTO requires signed ClickOnce manifests even for local development. Keep the
machine-specific test certificate outside version control by creating
`LaTeXSnipper.OfficePlugin.WordVstoAddIn.user.props` next to the project file:

```xml
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ManifestCertificateThumbprint>YOUR_CURRENT_USER_CODE_SIGNING_CERT_THUMBPRINT</ManifestCertificateThumbprint>
  </PropertyGroup>
</Project>
```

The shell wires:

- `ThisAddIn.CreateRibbonExtensibilityObject()` -> `WordRibbonExtensibility`
- `WordRibbonExtensibility.GetCustomUI()` -> embedded Ribbon XML from `hosts/WordAddIn`
- Ribbon callbacks -> `WordPluginController`
- `ThisAddIn.Application` -> `DynamicWordApplicationAdapter`

The final installer must package this VSTO output separately for 64-bit and 32-bit Office registration.

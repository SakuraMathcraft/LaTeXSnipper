# PowerPointVstoAddIn Shell

This project is the thin VSTO shell that PowerPoint loads. It keeps Office-specific startup, Ribbon extensibility, manifest signing, and registration metadata separate from the reusable `hosts/PowerPointAddIn` workflow code.

Build and register locally:

```powershell
cd office_plugin
.\tools\Register-PowerPointVstoAddIn.ps1
```

Installer-style machine-wide registration:

```powershell
.\tools\Register-PowerPointVstoAddIn.ps1 -RegistryScope LocalMachine
```

The final installer can call `tools/Register-OfficeVstoAddIns.ps1 -RegistryScope LocalMachine` to register both Word and PowerPoint.

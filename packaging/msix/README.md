# Microsoft Store MSIX Packaging

This folder contains the Store-channel MSIX manifest template for LaTeXSnipper.

Store identity values from Partner Center:

```text
Package/Identity/Name: MathCraft.LaTeXSnipper
Package/Identity/Publisher: CN=126B7303-E9CB-485C-8DA9-542DD30D121A
Package/Properties/PublisherDisplayName: MathCraft
Package Family Name: MathCraft.LaTeXSnipper_akhs4jyvhsn64
Store ID: 9NM3W4C98PFC
```

Build the Store-channel MSIX package:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_store_msix.ps1 -PackageVersion 2.3.100.0 -StoreRuntimeDir Store_CPU
```

The Store package must bundle a CPU-only dependency runtime. `Store_CPU` must contain `python311\python.exe` and `.deps_state.json`, and the state file must declare `MATHCRAFT_CPU` without `MATHCRAFT_GPU`.

The Store package also bundles MathCraft models by default. The script looks in `MathCraft\models` first, then `%APPDATA%\MathCraft\models`; pass `-MathCraftModelsRoot` to use another complete model directory.

By default the script runs PyInstaller with the bundled build interpreter at `src\deps\python311\python.exe`, not the Python found on `PATH`. This interpreter is only used to build the package; the runtime bundled into the MSIX comes from `-StoreRuntimeDir`. Override the build interpreter only when deliberately testing another environment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_store_msix.ps1 -PackageVersion 2.3.100.0 -StoreRuntimeDir Store_CPU -MathCraftModelsRoot "$env:APPDATA\MathCraft\models" -PythonPath src\deps\python311\python.exe
```

The script emits an unsigned `.msix` under `dist\store` for Partner Center upload. For local install testing only:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_store_msix.ps1 -PackageVersion 2.3.100.0 -StoreRuntimeDir Store_CPU -SignForLocalTest
```

The local-test package is signed with a self-signed certificate. Trust that certificate before installing the signed local-test package:

```cmd
certutil -addstore Root "E:\LaTexSnipper\dist\store\LaTeXSnipperStore-localtest.cer"
certutil -addstore TrustedPeople "E:\LaTexSnipper\dist\store\LaTeXSnipperStore-localtest.cer"
```

Run those commands from an elevated Command Prompt or PowerShell. Importing into `CurrentUser\Root` is not enough for App Installer on all systems.

Upload the unsigned `.msix` to Partner Center. Do not upload the `.localtest.msix` package.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw "Visual Studio Installer discovery tool was not found: $vswhere"
}

$installationPath = & $vswhere -latest -products * -property installationPath
if (-not $installationPath) {
    throw "Visual Studio was not found."
}

$hostingAssembly = Join-Path (
    Join-Path $installationPath "Common7\IDE\ReferenceAssemblies\v4.0"
) "Microsoft.VisualStudio.Tools.Applications.Hosting.dll"
$officeBuildToolsAvailable = $false
if (Test-Path -LiteralPath $hostingAssembly) {
    try {
        [void][System.Reflection.Assembly]::Load(
            "Microsoft.VisualStudio.Tools.Applications.Hosting, Version=10.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a"
        )
        $officeBuildToolsAvailable = $true
    }
    catch {
        $officeBuildToolsAvailable = $false
    }
}

$missingComponents = @()
if (-not $officeBuildToolsAvailable) {
    $missingComponents += "Microsoft.VisualStudio.Component.TeamOffice.BuildTools"
}
foreach ($component in @(
    "Microsoft.VisualStudio.Component.VC.ATL",
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
)) {
    $matchingInstallation = & $vswhere -latest -products * -requires $component -property installationPath
    if (-not $matchingInstallation) {
        $missingComponents += $component
    }
}

if ($missingComponents.Count -gt 0) {
    $installer = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vs_installer.exe"
    if (-not (Test-Path -LiteralPath $installer)) {
        throw "Visual Studio Installer was not found: $installer"
    }

    $arguments = @("modify", "--installPath", $installationPath)
    foreach ($component in $missingComponents) {
        $arguments += @("--add", $component)
    }
    $arguments += @("--quiet", "--norestart", "--wait")

    Write-Host "Installing Visual Studio components: $($missingComponents -join ', ')"
    & $installer @arguments
    if ($LASTEXITCODE -notin @(0, 3010)) {
        throw "Visual Studio Installer failed with exit code $LASTEXITCODE."
    }
}

$officeTargets = Get-ChildItem (
    Join-Path $installationPath "MSBuild\Microsoft\VisualStudio\v*\OfficeTools\Microsoft.VisualStudio.Tools.Office.targets"
) -ErrorAction SilentlyContinue
if (-not $officeTargets -or -not (Test-Path -LiteralPath $hostingAssembly)) {
    throw "The Visual Studio VSTO build tools installation is incomplete."
}
try {
    [void][System.Reflection.Assembly]::Load(
        "Microsoft.VisualStudio.Tools.Applications.Hosting, Version=10.0.0.0, Culture=neutral, PublicKeyToken=b03f5f7f11d50a3a"
    )
}
catch {
    throw "The Visual Studio VSTO hosting assembly is not registered correctly."
}

Write-Host "Visual Studio Office and native build prerequisites are available."

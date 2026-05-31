param(
    [string] $Configuration = "Debug",
    [string] $MSBuildPath = "",
    [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope = "CurrentUser",
    [string] $ProjectPath = "",
    [string] $ManifestPath = "",
    [switch] $SkipBuild,
    [switch] $SkipCertificateTrust,
    [switch] $SkipVstoInstaller,
    [switch] $SkipOfficeRegistration
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
. (Join-Path $scriptRoot "OfficeVstoRegistration.ps1")

$resolvedProjectPath = if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    Join-Path $pluginRoot "hosts\PowerPointVstoAddIn\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.csproj"
}
else {
    $ProjectPath
}

Invoke-OfficeVstoRegistration `
    -OfficeApplication "PowerPoint" `
    -ProjectPath $resolvedProjectPath `
    -AddInName "LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn" `
    -FriendlyName "LaTeXSnipper" `
    -Description "LaTeXSnipper native PowerPoint plugin" `
    -Configuration $Configuration `
    -MSBuildPath $MSBuildPath `
    -RegistryScope $RegistryScope `
    -ManifestPath $ManifestPath `
    -SkipBuild:$SkipBuild `
    -SkipCertificateTrust:$SkipCertificateTrust `
    -SkipVstoInstaller:$SkipVstoInstaller `
    -SkipOfficeRegistration:$SkipOfficeRegistration

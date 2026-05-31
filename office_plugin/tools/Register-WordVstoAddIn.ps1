param(
    [string] $Configuration = "Debug",
    [string] $MSBuildPath = "",
    [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope = "CurrentUser",
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

Invoke-OfficeVstoRegistration `
    -OfficeApplication "Word" `
    -ProjectPath (Join-Path $pluginRoot "hosts\WordVstoAddIn\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj") `
    -AddInName "LaTeXSnipper.OfficePlugin.WordVstoAddIn" `
    -FriendlyName "LaTeXSnipper" `
    -Description "LaTeXSnipper native Word plugin" `
    -Configuration $Configuration `
    -MSBuildPath $MSBuildPath `
    -RegistryScope $RegistryScope `
    -ManifestPath $ManifestPath `
    -SkipBuild:$SkipBuild `
    -SkipCertificateTrust:$SkipCertificateTrust `
    -SkipVstoInstaller:$SkipVstoInstaller `
    -SkipOfficeRegistration:$SkipOfficeRegistration

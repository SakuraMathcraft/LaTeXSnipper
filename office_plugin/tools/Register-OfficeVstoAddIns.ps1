param(
    [string] $Configuration = "Debug",
    [string] $MSBuildPath = "",
    [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope = "CurrentUser",
    [string] $PowerPointProjectPath = "",
    [string] $PowerPointManifestPath = "",
    [switch] $SkipBuild,
    [switch] $SkipCertificateTrust,
    [switch] $SkipVstoInstaller,
    [switch] $SkipOfficeRegistration
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $scriptRoot "Register-WordVstoAddIn.ps1") `
    -Configuration $Configuration `
    -MSBuildPath $MSBuildPath `
    -RegistryScope $RegistryScope `
    -SkipBuild:$SkipBuild `
    -SkipCertificateTrust:$SkipCertificateTrust `
    -SkipVstoInstaller:$SkipVstoInstaller `
    -SkipOfficeRegistration:$SkipOfficeRegistration

& (Join-Path $scriptRoot "Register-PowerPointVstoAddIn.ps1") `
    -Configuration $Configuration `
    -MSBuildPath $MSBuildPath `
    -RegistryScope $RegistryScope `
    -ProjectPath $PowerPointProjectPath `
    -ManifestPath $PowerPointManifestPath `
    -SkipBuild:$SkipBuild `
    -SkipCertificateTrust:$SkipCertificateTrust `
    -SkipVstoInstaller:$SkipVstoInstaller `
    -SkipOfficeRegistration:$SkipOfficeRegistration

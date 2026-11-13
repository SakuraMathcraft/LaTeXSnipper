[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Debug",

    [switch] $SkipRestore,

    [switch] $IncludeVstoBuild,

    [switch] $FullAudit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$solutionPath = Join-Path $pluginRoot "LaTeXSnipper.OfficePlugin.slnx"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Executable,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments,

        [Parameter(Mandatory = $true)]
        [string] $FailureMessage
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE."
    }
}

$dotnet = (Get-Command dotnet -ErrorAction Stop).Source
$analysisLevel = if ($FullAudit) { "latest-recommended" } else { "latest-none" }
Write-Host "Analysis profile: $(if ($FullAudit) { 'full recommended rules' } else { 'build gate' })"

if (-not $SkipRestore) {
    Write-Host "Restoring Office plugin projects..."
    Invoke-CheckedCommand `
        -Executable $dotnet `
        -Arguments @("restore", $solutionPath) `
        -FailureMessage "Office plugin restore failed."
}

Write-Host "Building analyzer-enabled C# projects..."
Invoke-CheckedCommand `
    -Executable $dotnet `
    -Arguments @(
        "build",
        $solutionPath,
        "-c",
        $Configuration,
        "--no-restore",
        "-p:AnalysisLevel=$analysisLevel"
    ) `
    -FailureMessage "Office plugin analyzer build failed."

if ($IncludeVstoBuild) {
    $windowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $vstoBuildScript = Join-Path $scriptRoot "Build-VstoAddIns.ps1"
    Write-Host "Building Word and PowerPoint VSTO shells..."
    Invoke-CheckedCommand `
        -Executable $windowsPowerShell `
        -Arguments @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $vstoBuildScript,
            "-Configuration",
            $Configuration
        ) `
        -FailureMessage "Office plugin VSTO build failed."
}

Write-Host "Office plugin C# analysis completed successfully."

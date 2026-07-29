[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string] $Configuration = "Debug"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$projectPath = Join-Path (
    $pluginRoot
) "tests\LaTeXSnipper.OfficePlugin.MetadataSafety.Tests\LaTeXSnipper.OfficePlugin.MetadataSafety.Tests.csproj"
Write-Host "Running metadata safety tests..."
& (Get-Command dotnet -ErrorAction Stop).Source test $projectPath -c $Configuration
if ($LASTEXITCODE -ne 0) {
    throw "Metadata safety tests failed. Exit code: $LASTEXITCODE."
}

Write-Host "Office metadata safety tests completed successfully."

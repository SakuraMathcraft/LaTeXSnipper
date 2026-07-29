[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $BaseRevision,

    [string] $SearchText = "",

    [switch] $RegexSearch
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$repositoryRoot = Split-Path -Parent $pluginRoot
$pluginRelativePath = "office_plugin"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    & git -C $repositoryRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')"
    }
}

$resolvedBase = (& git -C $repositoryRoot rev-parse --verify "$BaseRevision^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or -not $resolvedBase) {
    throw "Base revision is not a commit: $BaseRevision"
}

Write-Host "Repository: $repositoryRoot"
Write-Host "Baseline:   $resolvedBase"
Write-Host "Head:       $(& git -C $repositoryRoot rev-parse HEAD)"

Write-Host "`nOffice plugin working tree:"
Invoke-Git -Arguments @("status", "--short", "--", $pluginRelativePath)

Write-Host "`nCommits after baseline:"
Invoke-Git -Arguments @(
    "log",
    "--oneline",
    "--decorate",
    "$resolvedBase..HEAD",
    "--",
    $pluginRelativePath
)

Write-Host "`nTracked file changes relative to baseline, including uncommitted work:"
Invoke-Git -Arguments @(
    "diff",
    "--name-status",
    $resolvedBase,
    "--",
    $pluginRelativePath
)

Write-Host "`nChange summary:"
Invoke-Git -Arguments @(
    "diff",
    "--stat",
    $resolvedBase,
    "--",
    $pluginRelativePath
)

Write-Host "`nWhitespace and conflict-marker validation:"
Invoke-Git -Arguments @(
    "diff",
    "--check",
    $resolvedBase,
    "--",
    $pluginRelativePath
)

if ($SearchText) {
    $searchOption = if ($RegexSearch) { "-G$SearchText" } else { "-S$SearchText" }
    $searchKind = if ($RegexSearch) { "regex" } else { "exact text" }
    Write-Host "`nHistory containing $searchKind '$SearchText':"
    Invoke-Git -Arguments @(
        "log",
        "--oneline",
        "--decorate",
        $searchOption,
        "--",
        $pluginRelativePath
    )
}

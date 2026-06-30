param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$pluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$releaseRoot = Join-Path $pluginRoot "release"
$stagingRoot = Join-Path $releaseRoot "InstallerAssets"

if (Test-Path $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $stagingRoot | Out-Null

function Copy-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [string[]]$ExcludeFiles = @(),
        [string[]]$ExcludeDirectories = @()
    )

    $sourceRoot = (Resolve-Path $Source).Path.TrimEnd("\", "/")
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($sourceRoot.Length).TrimStart("\", "/")
        $segments = $relative -split "[\\/]"
        if ($ExcludeFiles -contains $_.Name) {
            return
        }

        if ($segments.Length -gt 0 -and $ExcludeDirectories -contains $segments[0]) {
            return
        }

        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

$mathJaxSource = Join-Path $pluginRoot "..\src\assets\MathJax-3.2.2"
$sharedEditorSource = Join-Path $pluginRoot "src\LaTeXSnipper.OfficePlugin.Editor\EditorAssets"
$mathLiveVendorSource = Join-Path $pluginRoot "..\src\assets\mathlive\vendor"
$wordEditorSource = Join-Path $pluginRoot "hosts\WordAddIn\EditorAssets"
$powerPointEditorSource = Join-Path $pluginRoot "hosts\PowerPointAddIn\EditorAssets"

Copy-Directory `
    -Source $mathJaxSource `
    -Destination (Join-Path $stagingRoot "MathJax-3.2.2")

Copy-Directory `
    -Source $sharedEditorSource `
    -Destination (Join-Path $stagingRoot "EditorSharedAssets")

Copy-Directory `
    -Source $mathLiveVendorSource `
    -Destination (Join-Path $stagingRoot "EditorSharedAssets\vendor") `
    -ExcludeFiles @("compute-engine.min.esm.js", "compute-engine.LICENSE.txt")

Copy-Directory `
    -Source $wordEditorSource `
    -Destination (Join-Path $stagingRoot "Word\EditorAssets") `
    -ExcludeFiles @("editor.js") `
    -ExcludeDirectories @("vendor")

Copy-Directory `
    -Source $powerPointEditorSource `
    -Destination (Join-Path $stagingRoot "PowerPoint\EditorAssets") `
    -ExcludeFiles @("editor.js") `
    -ExcludeDirectories @("vendor")

Write-Host "Installer assets staged at $stagingRoot"

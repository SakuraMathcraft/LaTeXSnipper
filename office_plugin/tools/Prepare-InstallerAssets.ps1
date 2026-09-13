param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$pluginRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$releaseRoot = Join-Path $pluginRoot "release"
$stagingRoot = Join-Path $releaseRoot "InstallerAssets"

$stagingRoot = [IO.Path]::GetFullPath($stagingRoot)
if (-not $stagingRoot.StartsWith(([IO.Path]::GetFullPath($releaseRoot) + "\"), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Installer staging path is outside the release directory."
}
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

$mathJaxSource = Join-Path $pluginRoot "..\src\assets\MathJax"
$sharedEditorSource = Join-Path $pluginRoot "src\LaTeXSnipper.OfficePlugin.Editor\EditorAssets"
$mathLiveVendorSource = Join-Path $pluginRoot "..\src\assets\mathlive\vendor"
$wordEditorSource = Join-Path $pluginRoot "hosts\WordAddIn\EditorAssets"
$powerPointEditorSource = Join-Path $pluginRoot "hosts\PowerPointAddIn\EditorAssets"

$mathJaxManifest = Get-Content -LiteralPath (Join-Path $mathJaxSource "resources.json") -Raw | ConvertFrom-Json
foreach ($relative in $mathJaxManifest.profiles.office) {
    $target = Join-Path (Join-Path $stagingRoot "MathJax") $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $mathJaxSource $relative) -Destination $target -Force
}

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

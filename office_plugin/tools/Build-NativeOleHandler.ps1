param(
    [string] $Configuration = "Release",
    [string] $MSBuildPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$project = Join-Path $pluginRoot "hosts\OleFormulaObjectNative\LaTeXSnipper.OfficePlugin.OleFormulaObjectHandler.vcxproj"

function Find-NativeBuildEnvironment {
    param([string] $RequestedMSBuildPath)

    $installationPaths = [System.Collections.Generic.List[string]]::new()
    if ($RequestedMSBuildPath) {
        if (-not (Test-Path -LiteralPath $RequestedMSBuildPath)) {
            throw "Requested MSBuild was not found: $RequestedMSBuildPath"
        }

        if ($RequestedMSBuildPath -match "^(.*)\\MSBuild\\Current\\Bin(?:\\amd64)?\\MSBuild\.exe$") {
            $installationPaths.Add($Matches[1])
        }
        else {
            throw "Requested MSBuild is not inside a Visual Studio installation: $RequestedMSBuildPath"
        }
    }
    else {
        $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path -LiteralPath $vswhere) {
            foreach ($installation in @(& $vswhere -products * -property installationPath)) {
                if ($installation) {
                    $installationPaths.Add($installation)
                }
            }
        }

        foreach ($candidate in @(
            "D:\Microsoft Visual Studio\2022\Community",
            "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community",
            "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community"
        )) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $installationPaths.Add($candidate)
            }
        }
    }

    foreach ($installation in $installationPaths | Select-Object -Unique) {
        $msbuildCandidates = @(
            (Join-Path $installation "MSBuild\Current\Bin\amd64\MSBuild.exe"),
            (Join-Path $installation "MSBuild\Current\Bin\MSBuild.exe")
        )
        $msbuild = $msbuildCandidates |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if (-not $msbuild) {
            continue
        }

        $vcTargetsRoot = Join-Path $installation "MSBuild\Microsoft\VC"
        if (-not (Test-Path -LiteralPath $vcTargetsRoot)) {
            continue
        }

        $toolsets = Get-ChildItem -LiteralPath $vcTargetsRoot -Directory |
            ForEach-Object {
                $platformToolsets = Join-Path $_.FullName "Platforms\x64\PlatformToolsets"
                if (Test-Path -LiteralPath $platformToolsets) {
                    Get-ChildItem -LiteralPath $platformToolsets -Directory
                }
            } |
            Where-Object { $_.Name -match "^v\d+$" } |
            Sort-Object { [int]$_.Name.Substring(1) } -Descending
        $toolset = $toolsets | Select-Object -First 1
        if ($toolset) {
            return [pscustomobject]@{
                MSBuildPath = $msbuild
                PlatformToolset = $toolset.Name
            }
        }
    }

    throw "Visual Studio MSBuild with a C++ v### platform toolset was not found."
}

if (-not (Test-Path -LiteralPath $project)) {
    throw "Native OLE project was not found: $project"
}

$environment = Find-NativeBuildEnvironment -RequestedMSBuildPath $MSBuildPath
Write-Host "Native MSBuild: $($environment.MSBuildPath)"
Write-Host "Native platform toolset: $($environment.PlatformToolset)"

foreach ($platform in @("x64", "Win32")) {
    & $environment.MSBuildPath $project `
        "/p:Configuration=$Configuration" `
        "/p:Platform=$platform" `
        "/p:PlatformToolset=$($environment.PlatformToolset)" `
        "/m" `
        "/nologo" `
        "/v:minimal"
    if ($LASTEXITCODE -ne 0) {
        throw "Native OLE $platform build failed with exit code $LASTEXITCODE."
    }
}

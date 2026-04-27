param(
    [string]$PackageVersion = "2.3.100.0",
    [string]$IdentityName = "MathCraft.LaTeXSnipper",
    [string]$Publisher = "CN=126B7303-E9CB-485C-8DA9-542DD30D121A",
    [string]$PublisherDisplayName = "MathCraft",
    [string]$StoreProductId = "9NM3W4C98PFC",
    [string]$BuildName = "LaTeXSnipperStore",
    [string]$DisplayName = "LaTeXSnipper",
    [string]$Description = "Recognize, edit, and export mathematical content from screenshots, images, PDFs, and handwriting.",
    [string]$PythonPath = "",
    [ValidateSet("x64", "x86", "arm64")]
    [string]$Architecture = "x64",
    [switch]$SkipPyInstaller,
    [switch]$Clean,
    [switch]$SignForLocalTest
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Test-PackageVersion {
    param([string]$Version)
    if ($Version -notmatch '^\d+\.\d+\.\d+\.\d+$') {
        throw "PackageVersion must use four numeric parts, for example 2.3.100.0"
    }
}

function Resolve-PythonExecutable {
    param(
        [string]$Root,
        [string]$RequestedPath
    )

    if ([string]::IsNullOrWhiteSpace($RequestedPath)) {
        $candidate = Join-Path $Root "src\deps\python311\python.exe"
    }
    elseif ([System.IO.Path]::IsPathRooted($RequestedPath)) {
        $candidate = $RequestedPath
    }
    else {
        $candidate = Join-Path $Root $RequestedPath
    }

    if (-not (Test-Path $candidate)) {
        throw "Python executable not found: $candidate"
    }

    return (Resolve-Path $candidate).Path
}

function Find-WindowsSdkTool {
    param([string]$ToolName)

    $roots = @()
    if ($env:ProgramFiles) {
        $roots += (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
    }
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if ($programFilesX86) {
        $roots += (Join-Path $programFilesX86 "Windows Kits\10\bin")
    }

    foreach ($root in $roots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $candidate = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\$ToolName" } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate
        }
    }

    $command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Could not find $ToolName. Install the Windows SDK, then rerun this script."
}

function ConvertTo-XmlEscaped {
    param([string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

function Write-TextFile {
    param(
        [string]$Path,
        [string]$Value
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $utf8NoBom)
}

function New-PngFromIcon {
    param(
        [string]$PythonPath,
        [string]$IconPath,
        [string]$OutputPath,
        [int]$Width,
        [int]$Height,
        [string]$Background = "#202020",
        [double]$PaddingRatio = 0.04
    )

    $assetScript = @'
import sys
import warnings
from pathlib import Path

from PIL import Image


warnings.filterwarnings("ignore", category=UserWarning)
icon_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
width = int(sys.argv[3])
height = int(sys.argv[4])
background = sys.argv[5]
padding_ratio = float(sys.argv[6])

canvas = Image.new("RGBA", (width, height), background)
image = Image.open(icon_path)
image.load()
image = image.convert("RGBA")

padding = max(1, round(min(width, height) * padding_ratio))
max_width = max(1, width - padding * 2)
max_height = max(1, height - padding * 2)
image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

x = (width - image.width) // 2
y = (height - image.height) // 2
canvas.alpha_composite(image, (x, y))
output_path.parent.mkdir(parents=True, exist_ok=True)
canvas.save(output_path, "PNG")
'@
    $tempScript = Join-Path ([System.IO.Path]::GetTempPath()) "latexsnipper-msix-asset-$PID.py"
    Write-TextFile -Path $tempScript -Value $assetScript
    try {
        & $PythonPath $tempScript $IconPath $OutputPath $Width $Height $Background $PaddingRatio
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to generate MSIX image asset: $OutputPath"
        }
    }
    finally {
        Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
    }
}

function New-MsixAssets {
    param(
        [string]$Root,
        [string]$IconPath,
        [string]$PythonPath
    )

    $assetsDir = Join-Path $Root "Assets"
    New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "Square44x44Logo.png") -Width 44 -Height 44 -PaddingRatio 0.04
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "Square71x71Logo.png") -Width 71 -Height 71 -PaddingRatio 0.04
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "Square150x150Logo.png") -Width 150 -Height 150 -PaddingRatio 0.04
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "Square310x310Logo.png") -Width 310 -Height 310 -PaddingRatio 0.04
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "StoreLogo.png") -Width 50 -Height 50 -PaddingRatio 0.04
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "Wide310x150Logo.png") -Width 310 -Height 150 -PaddingRatio 0.12
    New-PngFromIcon -PythonPath $PythonPath -IconPath $IconPath -OutputPath (Join-Path $assetsDir "SplashScreen.png") -Width 620 -Height 300 -PaddingRatio 0.18
}

function Invoke-PyInstallerBuild {
    param(
        [string]$PythonPath,
        [string]$Root,
        [string]$BuildName,
        [string]$StoreProductId,
        [bool]$Clean
    )

    $oldChannel = $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL
    $oldProduct = $env:LATEXSNIPPER_STORE_PRODUCT_ID
    $oldBuildName = $env:LATEXSNIPPER_BUILD_NAME
    try {
        $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL = "store"
        $env:LATEXSNIPPER_STORE_PRODUCT_ID = $StoreProductId
        $env:LATEXSNIPPER_BUILD_NAME = $BuildName
        $args = @("-m", "PyInstaller", (Join-Path $Root "LaTeXSnipper.spec"), "--noconfirm")
        if ($Clean) {
            $args += "--clean"
        }
        & $PythonPath @args
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL = $oldChannel
        $env:LATEXSNIPPER_STORE_PRODUCT_ID = $oldProduct
        $env:LATEXSNIPPER_BUILD_NAME = $oldBuildName
    }
}

function New-LocalTestCertificate {
    param([string]$Publisher)

    $existing = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Subject -eq $Publisher -and $_.HasPrivateKey } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
    if ($existing) {
        return $existing
    }

    return New-SelfSignedCertificate `
        -Type Custom `
        -Subject $Publisher `
        -KeyUsage DigitalSignature `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
}

function Sign-LocalTestMsix {
    param(
        [string]$MsixPath,
        [string]$Publisher,
        [string]$OutputDir
    )

    $signtool = Find-WindowsSdkTool -ToolName "signtool.exe"
    $cert = New-LocalTestCertificate -Publisher $Publisher
    $signedPath = [System.IO.Path]::ChangeExtension($MsixPath, ".localtest.msix")
    $signLog = Join-Path $OutputDir "signtool-localtest.log"
    Copy-Item -LiteralPath $MsixPath -Destination $signedPath -Force
    & $signtool sign /fd SHA256 /sha1 $cert.Thumbprint $signedPath *> $signLog
    if ($LASTEXITCODE -ne 0) {
        $tail = Get-Content -Path $signLog -Tail 80 -ErrorAction SilentlyContinue
        if ($tail) {
            Write-Host ""
            Write-Host "signtool output tail:"
            $tail | ForEach-Object { Write-Host $_ }
            Write-Host ""
        }
        throw "signtool failed with exit code $LASTEXITCODE. Full log: $signLog"
    }
    $cerPath = Join-Path $OutputDir "LaTeXSnipperStore-localtest.cer"
    Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null
    return [pscustomobject]@{
        Msix = $signedPath
        Certificate = $cerPath
        SignLog = $signLog
    }
}

function Invoke-MakeAppxPack {
    param(
        [string]$MakeAppxPath,
        [string]$StagingRoot,
        [string]$MsixPath,
        [string]$LogPath
    )

    if (Test-Path $LogPath) {
        Remove-Item -LiteralPath $LogPath -Force
    }

    & $MakeAppxPath pack /d $StagingRoot /p $MsixPath /o /h SHA256 *> $LogPath
    if ($LASTEXITCODE -ne 0) {
        $tail = Get-Content -Path $LogPath -Tail 80 -ErrorAction SilentlyContinue
        if ($tail) {
            Write-Host ""
            Write-Host "makeappx output tail:"
            $tail | ForEach-Object { Write-Host $_ }
            Write-Host ""
        }
        throw "makeappx failed with exit code $LASTEXITCODE. Full log: $LogPath"
    }
}

Test-PackageVersion -Version $PackageVersion

$root = Resolve-RepoRoot
$resolvedPythonPath = Resolve-PythonExecutable -Root $root -RequestedPath $PythonPath
$distApp = Join-Path $root "dist\$BuildName"
$stagingRoot = Join-Path $root "build\msix\$BuildName"
$outputDir = Join-Path $root "dist\store"
$makeappxLog = Join-Path $root "build\msix\makeappx-pack.log"
$templatePath = Join-Path $root "packaging\msix\AppxManifest.xml.template"
$iconPath = Join-Path $root "src\assets\icon.ico"
$makeappx = Find-WindowsSdkTool -ToolName "makeappx.exe"

if (-not (Test-Path $templatePath)) {
    throw "MSIX manifest template not found: $templatePath"
}
if (-not (Test-Path $iconPath)) {
    throw "Application icon not found: $iconPath"
}

Write-Host "Using Python:"
Write-Host "  $resolvedPythonPath"
Write-Host ""

if (-not $SkipPyInstaller) {
    Invoke-PyInstallerBuild -PythonPath $resolvedPythonPath -Root $root -BuildName $BuildName -StoreProductId $StoreProductId -Clean ([bool]$Clean)
}

$exePath = Join-Path $distApp "$BuildName.exe"
if (-not (Test-Path $exePath)) {
    throw "PyInstaller output not found: $exePath"
}

if (Test-Path $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null
Copy-Item -Path (Join-Path $distApp "*") -Destination $stagingRoot -Recurse -Force

New-MsixAssets -Root $stagingRoot -IconPath $iconPath -PythonPath $resolvedPythonPath

$manifest = Get-Content -Path $templatePath -Raw -Encoding UTF8
$tokens = @{
    "{{IDENTITY_NAME}}" = ConvertTo-XmlEscaped $IdentityName
    "{{PUBLISHER}}" = ConvertTo-XmlEscaped $Publisher
    "{{PACKAGE_VERSION}}" = ConvertTo-XmlEscaped $PackageVersion
    "{{ARCHITECTURE}}" = ConvertTo-XmlEscaped $Architecture
    "{{DISPLAY_NAME}}" = ConvertTo-XmlEscaped $DisplayName
    "{{PUBLISHER_DISPLAY_NAME}}" = ConvertTo-XmlEscaped $PublisherDisplayName
    "{{DESCRIPTION}}" = ConvertTo-XmlEscaped $Description
    "{{EXECUTABLE_NAME}}" = ConvertTo-XmlEscaped "$BuildName.exe"
}
foreach ($key in $tokens.Keys) {
    $manifest = $manifest.Replace($key, $tokens[$key])
}
Write-TextFile -Path (Join-Path $stagingRoot "AppxManifest.xml") -Value $manifest

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$msixName = "$($IdentityName)_$($PackageVersion)_$($Architecture).msix"
$msixPath = Join-Path $outputDir $msixName
if (Test-Path $msixPath) {
    Remove-Item -LiteralPath $msixPath -Force
}

Invoke-MakeAppxPack -MakeAppxPath $makeappx -StagingRoot $stagingRoot -MsixPath $msixPath -LogPath $makeappxLog

$hash = (Get-FileHash -Algorithm SHA256 $msixPath).Hash.ToLowerInvariant()
Write-TextFile -Path "$msixPath.sha256" -Value "$hash  $(Split-Path -Leaf $msixPath)`n"

Write-Host ""
Write-Host "MSIX package created:"
Write-Host "  $msixPath"
Write-Host "SHA256:"
Write-Host "  $hash"
Write-Host "MakeAppx log:"
Write-Host "  $makeappxLog"
Write-Host ""
Write-Host "Store identity:"
Write-Host "  Identity Name: $IdentityName"
Write-Host "  Publisher: $Publisher"
Write-Host "  Publisher Display Name: $PublisherDisplayName"
Write-Host "  Store Product ID: $StoreProductId"
Write-Host ""
Write-Host "Upload the unsigned .msix package to Partner Center. Use -SignForLocalTest only for local installation testing."

if ($SignForLocalTest) {
    $signed = Sign-LocalTestMsix -MsixPath $msixPath -Publisher $Publisher -OutputDir $outputDir
    Write-Host ""
    Write-Host "Local test package created:"
    Write-Host "  $($signed.Msix)"
    Write-Host "Local test certificate:"
    Write-Host "  $($signed.Certificate)"
    Write-Host "SignTool log:"
    Write-Host "  $($signed.SignLog)"
    Write-Host "Trust the local-test certificate before installing the local test MSIX."
    Write-Host "Run these commands from an elevated Command Prompt or PowerShell:"
    Write-Host "  certutil -addstore Root `"$($signed.Certificate)`""
    Write-Host "  certutil -addstore TrustedPeople `"$($signed.Certificate)`""
}

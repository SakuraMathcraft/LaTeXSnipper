param(
    [ValidateSet("normal", "offline")]
    [string]$Flavor = "normal",
    [switch]$Sign,
    [string]$CertificateThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$InnoCompiler = "",
    [string]$PythonPath = "",
    [switch]$SkipPythonInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Find-Tool {
    param(
        [string]$ToolName,
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    $command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Could not find $ToolName."
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

    throw "Could not find $ToolName. Install the Windows SDK or put it on PATH."
}

function Resolve-BuildPython {
    param(
        [string]$Root,
        [string]$RequestedPython
    )

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        $candidates += $RequestedPython
    }

    $candidates += (Join-Path $Root "src\deps\python311\python.exe")

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    $pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    throw "Could not find build Python. Pass -PythonPath or install Python on PATH."
}

function Invoke-CodeSign {
    param(
        [string]$Signtool,
        [string]$Path,
        [string]$Thumbprint,
        [string]$TimestampUrl
    )

    if (-not (Test-Path $Path)) {
        throw "Cannot sign missing file: $Path"
    }

    $args = @("sign", "/fd", "SHA256", "/td", "SHA256", "/tr", $TimestampUrl)
    if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
        $args += "/a"
    }
    else {
        $args += @("/sha1", $Thumbprint)
    }
    $args += $Path

    & $Signtool @args
    if ($LASTEXITCODE -ne 0) {
        throw "signtool failed with exit code $LASTEXITCODE for $Path"
    }
}

function Write-Sha256File {
    param([string]$Path)

    $hash = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
    $shaPath = "$Path.sha256"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($shaPath, "$hash  $(Split-Path -Leaf $Path)`n", $utf8NoBom)
    return $hash
}

$root = Resolve-RepoRoot
$python = Resolve-BuildPython -Root $root -RequestedPython $PythonPath

$isccCandidates = @()
if ($InnoCompiler) {
    $isccCandidates += $InnoCompiler
}
if (${env:ProgramFiles(x86)}) {
    $isccCandidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
}
if ($env:ProgramFiles) {
    $isccCandidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
}
$isccCandidates += "D:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$iscc = Find-Tool -ToolName "ISCC.exe" -Candidates $isccCandidates

if ($Flavor -eq "offline") {
    $buildName = "LaTeXSnipperOffline"
    $spec = Join-Path $root "LaTeXSnipper.offline.spec"
    $iss = Join-Path $root "Inno\latexsnipper_offline.iss"
    $installer = Join-Path $root "dist\installer\LaTeXSnipperOfflineSetup-2.3.2.exe"
}
else {
    $buildName = "LaTeXSnipper"
    $spec = Join-Path $root "LaTeXSnipper.spec"
    $iss = Join-Path $root "Inno\latexsnipper.iss"
    $installer = Join-Path $root "dist\installer\LaTeXSnipperSetup-2.3.2.exe"
}

if (-not (Test-Path $spec)) {
    throw "PyInstaller spec not found: $spec"
}
if (-not (Test-Path $iss)) {
    throw "Inno Setup script not found: $iss"
}

$oldChannel = $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL
$oldStoreProduct = $env:LATEXSNIPPER_STORE_PRODUCT_ID
$oldBuildName = $env:LATEXSNIPPER_BUILD_NAME
$oldBundlePythonInstaller = $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER
try {
    $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL = "github"
    $env:LATEXSNIPPER_STORE_PRODUCT_ID = ""
    $env:LATEXSNIPPER_BUILD_NAME = $buildName
    $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER = if ($SkipPythonInstaller) { "0" } else { "1" }

    & $python -m PyInstaller $spec --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:LATEXSNIPPER_DISTRIBUTION_CHANNEL = $oldChannel
    $env:LATEXSNIPPER_STORE_PRODUCT_ID = $oldStoreProduct
    $env:LATEXSNIPPER_BUILD_NAME = $oldBuildName
    $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER = $oldBundlePythonInstaller
}

$appExe = Join-Path $root "dist\$buildName\$buildName.exe"
if (-not (Test-Path $appExe)) {
    throw "PyInstaller output exe not found: $appExe"
}

$signtool = ""
if ($Sign) {
    $signtool = Find-WindowsSdkTool -ToolName "signtool.exe"
    Invoke-CodeSign -Signtool $signtool -Path $appExe -Thumbprint $CertificateThumbprint -TimestampUrl $TimestampUrl
}

$oldRepoRoot = $env:LATEXSNIPPER_REPO_ROOT
try {
    $env:LATEXSNIPPER_REPO_ROOT = $root
    & $iscc $iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:LATEXSNIPPER_REPO_ROOT = $oldRepoRoot
}

if (-not (Test-Path $installer)) {
    throw "Installer output not found: $installer"
}

if ($Sign) {
    Invoke-CodeSign -Signtool $signtool -Path $installer -Thumbprint $CertificateThumbprint -TimestampUrl $TimestampUrl
}

$hash = Write-Sha256File -Path $installer

Write-Host ""
Write-Host "GitHub release installer created:"
Write-Host "  $installer"
Write-Host "SHA256:"
Write-Host "  $hash"
if ($Sign) {
    Write-Host "Signing: completed"
}
else {
    Write-Host "Signing: skipped. Submit the installer to SignPath, or rerun with -Sign when a trusted code-signing certificate is available."
}

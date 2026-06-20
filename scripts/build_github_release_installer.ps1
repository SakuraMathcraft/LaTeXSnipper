param(
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

    $candidates += (Join-Path $Root "tools\deps\python311\python.exe")

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

function Test-PythonHttpsRuntime {
    param([string]$PythonExe)

    if (-not (Test-Path $PythonExe)) {
        throw "Python HTTPS verification target is missing: $PythonExe"
    }

    $code = @'
import json
import pathlib
import ssl
import sys
import urllib.request

handlers = [type(h).__name__ for h in urllib.request.build_opener().handlers]
result = {
    "executable": str(pathlib.Path(sys.executable).resolve()),
    "openssl": ssl.OPENSSL_VERSION,
    "handlers": handlers,
}
print(json.dumps(result, ensure_ascii=False))
if "HTTPSHandler" not in handlers:
    raise SystemExit("urllib HTTPSHandler is unavailable")
'@
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $verifyScript = Join-Path ([System.IO.Path]::GetTempPath()) ("latexsnipper_verify_python_https_{0}.py" -f ([System.Guid]::NewGuid().ToString("N")))
    try {
        [System.IO.File]::WriteAllText($verifyScript, $code, $utf8NoBom)
        $verifyJson = & $PythonExe $verifyScript
        if ($LASTEXITCODE -ne 0) {
            throw "Python HTTPS verification failed for $PythonExe"
        }
        $verify = $verifyJson | ConvertFrom-Json
        Write-Host "Python HTTPS runtime verified:"
        Write-Host "  executable: $($verify.executable)"
        Write-Host "  openssl: $($verify.openssl)"
    }
    finally {
        if (Test-Path $verifyScript) {
            Remove-Item -LiteralPath $verifyScript -Force
        }
    }
}

function Normalize-BundledPythonSeed {
    param([string]$Root)

    $seedRoot = Join-Path $Root "python311"
    if (-not (Test-Path $seedRoot)) {
        Write-Host "Bundled Python seed not found, skip normalization: $seedRoot"
        return
    }

    $pythonExe = Join-Path $seedRoot "python.exe"
    if (-not (Test-Path $pythonExe)) {
        throw "Bundled Python seed is missing python.exe: $pythonExe"
    }

    $pyvenvCfg = Join-Path $seedRoot "pyvenv.cfg"
    if (Test-Path $pyvenvCfg) {
        Remove-Item -LiteralPath $pyvenvCfg -Force
    }

    $pthPath = Join-Path $seedRoot "python311._pth"
    $pthLines = @(
        "python311.zip",
        ".",
        "DLLs",
        "Lib",
        "Lib\site-packages",
        "import site"
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($pthPath, (($pthLines -join "`n") + "`n"), $utf8NoBom)

    $sitePackages = Join-Path $seedRoot "Lib\site-packages"
    if (Test-Path $sitePackages) {
        $keepNames = @(
            "_distutils_hack",
            "distutils-precedence.pth",
            "packaging",
            "pip",
            "pkg_resources",
            "README.txt",
            "setuptools",
            "wheel"
        )
        $keepPrefixes = @(
            "packaging-",
            "pip-",
            "setuptools-",
            "wheel-"
        )
        foreach ($child in Get-ChildItem -LiteralPath $sitePackages -Force) {
            $keep = $keepNames -contains $child.Name
            foreach ($prefix in $keepPrefixes) {
                if ($child.Name.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $keep = $true
                    break
                }
            }
            if (-not $keep) {
                Remove-Item -LiteralPath $child.FullName -Recurse -Force
                Write-Host "Pruned bundled Python package: $($child.Name)"
            }
        }
    }

    $scriptsDir = Join-Path $seedRoot "Scripts"
    if (Test-Path $scriptsDir) {
        foreach ($child in Get-ChildItem -LiteralPath $scriptsDir -Force) {
            $name = $child.Name.ToLowerInvariant()
            if ($name.StartsWith("pip") -or $name.StartsWith("easy_install") -or $name.StartsWith("wheel")) {
                continue
            }
            Remove-Item -LiteralPath $child.FullName -Recurse -Force
            Write-Host "Pruned bundled Python script: $($child.Name)"
        }
    }

    $verifyCode = @'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
paths = [pathlib.Path(p).resolve() for p in sys.path]
bad = [str(p) for p in paths if not (p == root or root in p.parents)]
result = {
    "executable": str(pathlib.Path(sys.executable).resolve()),
    "prefix": str(pathlib.Path(sys.prefix).resolve()),
    "base_prefix": str(pathlib.Path(sys.base_prefix).resolve()),
    "paths": [str(p) for p in paths],
    "outside_paths": bad,
}
print(json.dumps(result, ensure_ascii=False))
if pathlib.Path(sys.prefix).resolve() != root:
    raise SystemExit("sys.prefix does not point to bundled python311")
if pathlib.Path(sys.base_prefix).resolve() != root:
    raise SystemExit("sys.base_prefix does not point to bundled python311")
if bad:
    raise SystemExit("sys.path contains paths outside bundled python311")
'@
    $verifyScript = Join-Path ([System.IO.Path]::GetTempPath()) ("latexsnipper_verify_python_seed_{0}.py" -f ([System.Guid]::NewGuid().ToString("N")))
    try {
        [System.IO.File]::WriteAllText($verifyScript, $verifyCode, $utf8NoBom)
        $verifyJson = & $pythonExe $verifyScript $seedRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Bundled Python seed verification failed."
        }
    }
    finally {
        if (Test-Path $verifyScript) {
            Remove-Item -LiteralPath $verifyScript -Force
        }
    }
    $verify = $verifyJson | ConvertFrom-Json
    Write-Host "Bundled Python seed normalized:"
    Write-Host "  executable: $($verify.executable)"
    Write-Host "  prefix: $($verify.prefix)"
    Test-PythonHttpsRuntime -PythonExe $pythonExe
}

function Stage-BundledPythonSeed {
    param([string]$Root)

    $source = Join-Path $Root "python311"
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Bundled Python template not found: $source"
    }

    $stagingBase = Join-Path $Root "build\github-release"
    New-Item -ItemType Directory -Path $stagingBase -Force | Out-Null
    $stagingBase = (Resolve-Path -LiteralPath $stagingBase).Path
    $stagedRoot = Join-Path $stagingBase "bundled-deps"
    if (Test-Path -LiteralPath $stagedRoot) {
        $resolvedStagedRoot = (Resolve-Path -LiteralPath $stagedRoot).Path
        $expectedPrefix = $stagingBase.TrimEnd('\') + '\'
        if (-not $resolvedStagedRoot.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to replace bundled dependency stage outside build directory: $resolvedStagedRoot"
        }
        Remove-Item -LiteralPath $stagedRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stagedRoot -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $stagedRoot "python311") -Recurse -Force

    $depsState = Join-Path $Root ".deps_state.json"
    if (Test-Path -LiteralPath $depsState) {
        Copy-Item -LiteralPath $depsState -Destination $stagedRoot -Force
    }
    Write-Host "Bundled Python template staged: $stagedRoot"
    return $stagedRoot
}

$root = Resolve-RepoRoot
$python = Resolve-BuildPython -Root $root -RequestedPython $PythonPath
$bundledDepsRoot = Stage-BundledPythonSeed -Root $root
Normalize-BundledPythonSeed -Root $bundledDepsRoot

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

$buildName = "LaTeXSnipper"
$spec = Join-Path $root "LaTeXSnipper.spec"
$iss = Join-Path $root "Inno\latexsnipper.iss"
$installerOutputDir = Join-Path $root "dist\installer"

if (-not (Test-Path $spec)) {
    throw "PyInstaller spec not found: $spec"
}
if (-not (Test-Path $iss)) {
    throw "Inno Setup script not found: $iss"
}

$oldBuildName = $env:LATEXSNIPPER_BUILD_NAME
$oldBundlePythonInstaller = $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER
$oldBundledDepsDir = $env:LATEXSNIPPER_BUNDLED_DEPS_DIR
try {
    $env:LATEXSNIPPER_BUILD_NAME = $buildName
    $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER = if ($SkipPythonInstaller) { "0" } else { "1" }
    $env:LATEXSNIPPER_BUNDLED_DEPS_DIR = $bundledDepsRoot

    & $python -m PyInstaller $spec --clean --noconfirm
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    $distPython = Join-Path $root "dist\$buildName\_internal\deps\python311\python.exe"
    Test-PythonHttpsRuntime -PythonExe $distPython
}
finally {
    $env:LATEXSNIPPER_BUILD_NAME = $oldBuildName
    $env:LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER = $oldBundlePythonInstaller
    $env:LATEXSNIPPER_BUNDLED_DEPS_DIR = $oldBundledDepsDir
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
    if (Test-Path $installerOutputDir) {
        Get-ChildItem -LiteralPath $installerOutputDir -Filter "LaTeXSnipperSetup-*.exe" -File |
            Remove-Item -Force
    }
    & $iscc $iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
}
finally {
    $env:LATEXSNIPPER_REPO_ROOT = $oldRepoRoot
}

$installer = Get-ChildItem -LiteralPath $installerOutputDir -Filter "LaTeXSnipperSetup-*.exe" -File |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $installer -or -not (Test-Path -LiteralPath $installer.FullName)) {
    throw "Installer output not found in: $installerOutputDir"
}

if ($Sign) {
    Invoke-CodeSign -Signtool $signtool -Path $installer.FullName -Thumbprint $CertificateThumbprint -TimestampUrl $TimestampUrl
}

$hash = Write-Sha256File -Path $installer.FullName

Write-Host ""
Write-Host "GitHub release installer created:"
Write-Host "  $($installer.FullName)"
Write-Host "SHA256:"
Write-Host "  $hash"
if ($Sign) {
    Write-Host "Signing: completed"
}
else {
    Write-Host "Signing: skipped. Submit the installer to SignPath, or rerun with -Sign when a trusted code-signing certificate is available."
}

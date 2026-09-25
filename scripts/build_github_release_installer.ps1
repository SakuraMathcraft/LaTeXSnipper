param(
    [Parameter(Mandatory = $true)]
    [string]$BundledPythonPath,
    [string]$PythonPath = "python",
    [string]$InnoCompiler = ""
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
    param([string]$SeedRoot)

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

    $removePaths = @(
        "include",
        "libs",
        "tcl",
        "NEWS.txt",
        "Lib\venv",
        "Lib\idlelib",
        "Lib\lib2to3",
        "Lib\pydoc_data",
        "Lib\tkinter",
        "Lib\turtledemo",
        "Lib\unittest",
        "Lib\ctypes\test",
        "Lib\distutils\tests",
        "Lib\doctest.py",
        "Lib\pdb.py",
        "Lib\pydoc.py",
        "Lib\turtle.py",
        "DLLs\_ctypes_test.pyd",
        "DLLs\_testbuffer.pyd",
        "DLLs\_testcapi.pyd",
        "DLLs\_testconsole.pyd",
        "DLLs\_testimportmultiple.pyd",
        "DLLs\_testinternalcapi.pyd",
        "DLLs\_testmultiphase.pyd",
        "DLLs\_tkinter.pyd",
        "DLLs\tcl86t.dll",
        "DLLs\tk86t.dll",
        "DLLs\py.ico",
        "DLLs\pyc.ico",
        "DLLs\pyd.ico",
        "DLLs\python_lib.cat",
        "DLLs\python_tools.cat"
    )
    foreach ($relativePath in $removePaths) {
        $target = Join-Path $seedRoot $relativePath
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
            Write-Host "Pruned bundled Python runtime artifact: $relativePath"
        }
    }

    Remove-PythonCache -Root $seedRoot

    $verifyCode = @'
import json
import importlib
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1]).resolve()
paths = [pathlib.Path(p).resolve() for p in sys.path]
bad = [str(p) for p in paths if not (p == root or root in p.parents)]
toolchain = {}
for module_name in ("ensurepip", "setuptools", "wheel", "packaging", "pip"):
    module = importlib.import_module(module_name)
    toolchain[module_name] = getattr(module, "__version__", "available")
pip_check = subprocess.run(
    [sys.executable, "-m", "pip", "--version"],
    check=False,
    capture_output=True,
    text=True,
)
result = {
    "executable": str(pathlib.Path(sys.executable).resolve()),
    "prefix": str(pathlib.Path(sys.prefix).resolve()),
    "base_prefix": str(pathlib.Path(sys.base_prefix).resolve()),
    "paths": [str(p) for p in paths],
    "outside_paths": bad,
    "toolchain": toolchain,
    "pip": pip_check.stdout.strip(),
}
print(json.dumps(result, ensure_ascii=False))
if pathlib.Path(sys.prefix).resolve() != root:
    raise SystemExit("sys.prefix does not point to bundled python311")
if pathlib.Path(sys.base_prefix).resolve() != root:
    raise SystemExit("sys.base_prefix does not point to bundled python311")
if bad:
    raise SystemExit("sys.path contains paths outside bundled python311")
if pip_check.returncode != 0:
    raise SystemExit(f"bundled pip is not executable: {pip_check.stderr.strip()}")
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
    Write-Host "  pip: $($verify.pip)"
    Test-PythonHttpsRuntime -PythonExe $pythonExe
    Remove-PythonCache -Root $seedRoot
}

function Remove-PythonCache {
    param([string]$Root)

    if (-not (Test-Path -LiteralPath $Root)) {
        return
    }
    Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $Root -Recurse -Force -File |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force
}

$root = Resolve-RepoRoot
$python = (Get-Command $PythonPath -CommandType Application -ErrorAction Stop).Source
$bundledPython = (Resolve-Path -LiteralPath $BundledPythonPath).Path
$runnerTemp = (Resolve-Path -LiteralPath $env:RUNNER_TEMP).Path.TrimEnd('\') + '\'
if (-not $bundledPython.StartsWith($runnerTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Bundled Python must be prepared inside RUNNER_TEMP: $bundledPython"
}
Normalize-BundledPythonSeed -SeedRoot $bundledPython

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
$iscc = Find-Tool -ToolName "ISCC.exe" -Candidates $isccCandidates

$buildName = "LaTeXSnipper"
$spec = Join-Path $root "LaTeXSnipper.spec"
$iss = Join-Path $root "Inno\latexsnipper.iss"
$distRoot = Join-Path $root "dist"
$distAppDir = Join-Path $distRoot $buildName
$pyinstallerWorkDir = Join-Path $root "build\pyinstaller_windows"
$installerOutputDir = Join-Path $root "dist\installer"

if (-not (Test-Path $spec)) {
    throw "PyInstaller spec not found: $spec"
}
if (-not (Test-Path $iss)) {
    throw "Inno Setup script not found: $iss"
}

$oldBuildName = $env:LATEXSNIPPER_BUILD_NAME
$oldBundledPython = $env:LATEXSNIPPER_BUNDLED_PYTHON
try {
    $env:LATEXSNIPPER_BUILD_NAME = $buildName
    $env:LATEXSNIPPER_BUNDLED_PYTHON = $bundledPython

    foreach ($path in @($distAppDir, $pyinstallerWorkDir)) {
        if (Test-Path -LiteralPath $path) {
            $resolvedPath = (Resolve-Path -LiteralPath $path).Path
            $expectedPrefix = $root.TrimEnd('\') + '\'
            if (-not $resolvedPath.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove build output outside repository: $resolvedPath"
            }
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }

    Push-Location $root
    try {
        & $python -m PyInstaller `
            --distpath $distRoot `
            --workpath $pyinstallerWorkDir `
            --clean `
            --noconfirm `
            $spec
    }
    finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    & (Join-Path $root "scripts\normalize_windows_crt.ps1") -DistributionRoot $distAppDir
    $distPython = Join-Path $distAppDir "_internal\deps\python311\python.exe"
    Test-PythonHttpsRuntime -PythonExe $distPython
    Remove-PythonCache -Root (Join-Path $distAppDir "_internal\deps\python311")
}
finally {
    $env:LATEXSNIPPER_BUILD_NAME = $oldBuildName
    $env:LATEXSNIPPER_BUNDLED_PYTHON = $oldBundledPython
}

$appExe = Join-Path $distAppDir "$buildName.exe"
if (-not (Test-Path $appExe)) {
    throw "PyInstaller output exe not found: $appExe"
}

if (Test-Path $installerOutputDir) {
    Get-ChildItem -LiteralPath $installerOutputDir -Filter "LaTeXSnipperSetup-*.exe" -File |
        Remove-Item -Force
}
& $iscc $iss
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$installer = Get-ChildItem -LiteralPath $installerOutputDir -Filter "LaTeXSnipperSetup-*.exe" -File |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if (-not $installer -or -not (Test-Path -LiteralPath $installer.FullName)) {
    throw "Installer output not found in: $installerOutputDir"
}

$hash = Write-Sha256File -Path $installer.FullName

Write-Host ""
Write-Host "GitHub release installer created:"
Write-Host "  $($installer.FullName)"
Write-Host "SHA256:"
Write-Host "  $hash"
Write-Host "Signing is handled by the release workflow through SignPath."

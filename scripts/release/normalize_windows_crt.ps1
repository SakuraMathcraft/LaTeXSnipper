param(
    [Parameter(Mandatory = $true)][string]$DistributionRoot,
    [string]$RedistRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-DllVersion([string]$Path) {
    $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
    return [version]::new($info.FileMajorPart, $info.FileMinorPart, $info.FileBuildPart, $info.FilePrivatePart)
}

function Assert-X64Dll([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $reader = [System.IO.BinaryReader]::new($stream)
    try {
        $stream.Position = 0x3c
        $offset = $reader.ReadInt32()
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) {
            throw "Not an x64 PE file: $Path"
        }
    }
    finally { $reader.Dispose() }
}

if (-not $RedistRoot) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $installations = & $vswhere -all -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate Visual Studio CRT redistributables.' }
    $candidates = @(foreach ($installation in $installations) {
        $base = Join-Path $installation 'VC\Redist\MSVC'
        if (Test-Path -LiteralPath $base) {
            Get-ChildItem -LiteralPath $base -Directory |
                Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } |
                ForEach-Object { Get-ChildItem -Path (Join-Path $_.FullName 'x64\Microsoft.VC*.CRT') -Directory }
        }
    })
    $selected = $candidates | Sort-Object { Get-DllVersion (Join-Path $_.FullName 'msvcp140.dll') } -Descending | Select-Object -First 1
    if (-not $selected) { throw 'No Visual Studio x64 CRT redistributable directory found.' }
    $RedistRoot = $selected.FullName
}

$distribution = (Resolve-Path -LiteralPath $DistributionRoot).Path
$internal = Join-Path $distribution '_internal'
if (-not (Test-Path -LiteralPath $internal -PathType Container)) {
    throw "Not a collected LaTeXSnipper distribution: $distribution"
}
$sources = @{}
foreach ($dll in Get-ChildItem -LiteralPath $RedistRoot -Filter '*.dll' -File) {
    Assert-X64Dll $dll.FullName
    $signature = Get-AuthenticodeSignature -LiteralPath $dll.FullName
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "CRT DLL is not validly signed by Microsoft: $($dll.FullName)"
    }
    $sources[$dll.Name] = $dll.FullName
}
foreach ($required in @('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    if (-not $sources.ContainsKey($required)) { throw "Missing CRT redistributable: $required" }
}

# Replace all copies, including Qt and the Python seed, before signing/packaging.
# Do not grow the minimal seed; only the GUI runtime gets the complete CRT set.
$existing = @(Get-ChildItem -LiteralPath $distribution -Recurse -File | Where-Object {
    $_.Name -match '^(msvcp140.*|vcruntime140.*|concrt140|vccorlib140)\.dll$'
})
foreach ($dll in $existing) {
    if (-not $sources.ContainsKey($dll.Name)) { throw "Unknown CRT DLL in distribution: $($dll.FullName)" }
    if ((Get-DllVersion $dll.FullName) -gt (Get-DllVersion $sources[$dll.Name])) {
        throw "Refusing to downgrade CRT DLL: $($dll.FullName)"
    }
}
foreach ($dll in $existing) {
    Copy-Item -LiteralPath $sources[$dll.Name] -Destination $dll.FullName -Force
}
foreach ($directory in @($internal, (Join-Path $internal 'PyQt6\Qt6\bin'))) {
    if (Test-Path -LiteralPath $directory -PathType Container) {
        foreach ($source in $sources.Values) {
            Copy-Item -LiteralPath $source -Destination $directory -Force
        }
    }
}
foreach ($dll in Get-ChildItem -LiteralPath $distribution -Recurse -File | Where-Object { $sources.ContainsKey($_.Name) }) {
    $expected = (Get-FileHash -LiteralPath $sources[$dll.Name] -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash -ne $expected) {
        throw "CRT consistency check failed: $($dll.FullName)"
    }
}
Write-Host "Windows CRT normalized and verified: $RedistRoot"

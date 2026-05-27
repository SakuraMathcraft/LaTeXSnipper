param(
    [string]$InnoCompiler = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path (Split-Path -Parent $PSCommandPath) "..")).Path
$addin = Join-Path $root "office_addin"
$stage = Join-Path $root "build\office_addin\windows"
$output = Join-Path $root "dist\office-addin"
$publicOrigin = "https://localhost:8765"

Push-Location $addin
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "Office add-in Vite build failed."
    }
}
finally {
    Pop-Location
}

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $stage "site") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage "manifests") -Force | Out-Null
New-Item -ItemType Directory -Path $output -Force | Out-Null
Copy-Item -Path (Join-Path $addin "dist\*") -Destination (Join-Path $stage "site") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root "src\assets\icon.ico") -Destination (Join-Path $stage "icon.ico") -Force
Copy-Item -LiteralPath (Join-Path $root "Inno\ChineseSimplified.isl") -Destination (Join-Path $stage "ChineseSimplified.isl") -Force
Copy-Item -LiteralPath (Join-Path $addin "installer\windows\install.ps1") -Destination (Join-Path $stage "install.ps1") -Force
Copy-Item -LiteralPath (Join-Path $addin "installer\windows\uninstall.ps1") -Destination (Join-Path $stage "uninstall.ps1") -Force

foreach ($manifest in @("manifest.word.xml", "manifest.powerpoint.xml")) {
    $source = Get-Content -LiteralPath (Join-Path $addin $manifest) -Raw -Encoding UTF8
    $production = $source.Replace("https://localhost:3000", $publicOrigin)
    [System.IO.File]::WriteAllText(
        (Join-Path (Join-Path $stage "manifests") $manifest),
        $production,
        [System.Text.UTF8Encoding]::new($false)
    )
}

if ($SkipInstaller) {
    Write-Host "Office add-in staging created: $stage"
    exit 0
}

$candidates = @()
if ($InnoCompiler) {
    $candidates += $InnoCompiler
}
if (${env:ProgramFiles(x86)}) {
    $candidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
}
if ($env:ProgramFiles) {
    $candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
}
$iscc = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $iscc) {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    $iscc = if ($command) { $command.Source } else { "" }
}
if (-not $iscc) {
    throw "Inno Setup compiler was not found."
}

$oldStage = $env:LATEXSNIPPER_OFFICE_STAGE
$oldOutput = $env:LATEXSNIPPER_OFFICE_OUTPUT
try {
    $env:LATEXSNIPPER_OFFICE_STAGE = $stage
    $env:LATEXSNIPPER_OFFICE_OUTPUT = $output
    & $iscc (Join-Path $root "Inno\latexsnipper-office-addin.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:LATEXSNIPPER_OFFICE_STAGE = $oldStage
    $env:LATEXSNIPPER_OFFICE_OUTPUT = $oldOutput
}

$installer = Get-ChildItem -LiteralPath $output -Filter "LaTeXSnipperOfficeAddinSetup-*.exe" | Select-Object -First 1
if (-not $installer) {
    throw "Office add-in installer output was not produced."
}
$hash = (Get-FileHash -Algorithm SHA256 $installer.FullName).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText("$($installer.FullName).sha256", "$hash  $($installer.Name)`n", [System.Text.UTF8Encoding]::new($false))
Write-Host "Office add-in installer created: $($installer.FullName)"

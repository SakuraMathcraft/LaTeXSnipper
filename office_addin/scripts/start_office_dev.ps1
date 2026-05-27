param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Word", "PowerPoint")]
    [string]$HostApp,
    [switch]$LaunchLaTeXSnipper,
    [switch]$NoSideload
)

$ErrorActionPreference = "Stop"

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
try {
    chcp 65001 | Out-Null
}
catch {
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$addinRoot = Join-Path $repoRoot "office_addin"
$python = Join-Path $repoRoot "tools\deps\python311\python.exe"
$mainPy = Join-Path $repoRoot "src\main.py"

function Get-OfficeBridgeHealth {
    try {
        return Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
    }
    catch {
        return $null
    }
}

function Wait-HttpReady($Url, $Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

Push-Location $addinRoot
try {
    $viteListening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if (-not $viteListening) {
        Write-Host "Starting Office add-in Vite dev server..."
        Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory $addinRoot -WindowStyle Hidden
        if (-not (Wait-HttpReady "https://localhost:3000/taskpane.html" 20)) {
            throw "Vite dev server did not become ready at https://localhost:3000."
        }
    }
    else {
        Write-Host "Vite dev server is already listening on port 3000."
    }

    if ($LaunchLaTeXSnipper) {
        $mainRunning = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*src/main.py*" }
        if (-not $mainRunning) {
            Write-Host "Launching LaTeXSnipper..."
            Start-Process -FilePath $python -ArgumentList @($mainPy) -WorkingDirectory $repoRoot
        }
    }

    $health = Get-OfficeBridgeHealth
    if ($health -and $health.ok) {
        $capture = [bool]$health.result.features.capture_recognize
        Write-Host "Office bridge detected: capture_recognize=$capture"
        if (-not $capture) {
            Write-Host "Warning: current bridge is conversion-only. Screenshot OCR needs the LaTeXSnipper desktop bridge."
        }
    }
    else {
        Write-Host "Warning: Office bridge is not reachable at http://127.0.0.1:8765."
        Write-Host "Open LaTeXSnipper settings and enable the Office add-in before testing Screenshot OCR."
    }

    if (-not $NoSideload) {
        if ($HostApp -eq "PowerPoint") {
            npm run sideload:powerpoint
        }
        else {
            npm run sideload:word
        }
    }
}
finally {
    Pop-Location
}

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
$devServerUrl = "https://localhost:3000/taskpane.html"
$officeBridgeUrl = "https://localhost:8765"

function Invoke-LocalHttpsProbe($Url, $ReadBody) {
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $code = if ($ReadBody) {
            "import ssl, sys, urllib.request; ctx = ssl._create_unverified_context(); print(urllib.request.urlopen(sys.argv[1], context=ctx, timeout=2).read().decode('utf-8'))"
        }
        else {
            "import ssl, sys, urllib.request; ctx = ssl._create_unverified_context(); urllib.request.urlopen(sys.argv[1], context=ctx, timeout=2).close(); print('ok')"
        }
        $output = & $python -c $code $Url 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $output
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
}

function Get-OfficeBridgeHealth {
    $payload = Invoke-LocalHttpsProbe "$officeBridgeUrl/health" $true
    if (-not $payload) {
        return $null
    }
    return $payload | ConvertFrom-Json
}

function Wait-HttpReady($Url, $Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ($null -ne (Invoke-LocalHttpsProbe $Url $false)) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Push-Location $addinRoot
try {
    if (Wait-HttpReady $devServerUrl 2) {
        Write-Host "Vite dev server is already reachable at $devServerUrl."
    }
    else {
        $viteListening = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
        if ($viteListening) {
            throw "Port 3000 is already in use, but $devServerUrl did not respond."
        }
        Write-Host "Starting Office add-in Vite dev server..."
        Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory $addinRoot -WindowStyle Hidden
        if (-not (Wait-HttpReady $devServerUrl 20)) {
            throw "Vite dev server did not become ready at $devServerUrl."
        }
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
        Write-Host "LaTeXSnipper Office bridge detected."
    }
    else {
        Write-Host "Warning: Office bridge is not reachable at $officeBridgeUrl."
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

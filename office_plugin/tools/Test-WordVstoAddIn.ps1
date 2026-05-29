param(
    [switch] $SkipRegister,
    [switch] $LeaveWordOpen
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$registerScript = Join-Path $scriptRoot "Register-WordVstoAddIn.ps1"
$addinName = "LaTeXSnipper.OfficePlugin.WordVstoAddIn"

function Get-WinWordPath {
    $appPath = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE" -ErrorAction SilentlyContinue
    if ($appPath -and $appPath.'(default)' -and (Test-Path -LiteralPath $appPath.'(default)')) {
        return $appPath.'(default)'
    }

    throw "WINWORD.EXE was not found in App Paths."
}

function Get-WordApplication {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            return [Runtime.InteropServices.Marshal]::GetActiveObject("Word.Application")
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    throw "Timed out waiting for Word.Application."
}

function Get-WordComAddIns {
    param([Parameter(Mandatory = $true)] [object] $Word)

    $lastError = $null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $collection = $Word.COMAddIns
            $count = [int] $collection.Count
            return [pscustomobject] @{
                Collection = $collection
                Count = $count
            }
        }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Seconds 1
        }
    }

    throw "Timed out waiting for Word COMAddIns. Last error: $lastError"
}

function Quit-Word {
    param(
        [object] $Word,
        [System.Diagnostics.Process] $Process
    )

    try {
        $saveChanges = 0
        $missing = [Type]::Missing
        $Word.Quit([ref] $saveChanges, [ref] $missing, [ref] $missing)
    }
    catch {
        Write-Warning "Word rejected the COM Quit call; closing the test process instead."
    }
    finally {
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($Word) | Out-Null
    }

    Start-Sleep -Seconds 3
    $stillRunning = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($stillRunning) {
        $stillRunning.CloseMainWindow() | Out-Null
        Start-Sleep -Seconds 3
    }

    $stillRunning = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Stop-Process -Id $Process.Id -Force
    }
}

if (-not $SkipRegister) {
    & $registerScript
}

$existingWord = Get-Process WINWORD -ErrorAction SilentlyContinue
if ($existingWord) {
    throw "Close existing WINWORD processes before running this automation test."
}

$env:VSTO_SUPPRESSDISPLAYALERTS = "0"
$env:VSTO_LOGALERTS = "1"
$winwordPath = Get-WinWordPath
$process = Start-Process -FilePath $winwordPath -ArgumentList "/x" -WindowStyle Minimized -PassThru
$word = $null

try {
    $word = Get-WordApplication
    Start-Sleep -Seconds 6

    $comAddIns = Get-WordComAddIns -Word $word
    $addin = $null
    $seenProgIds = New-Object System.Collections.Generic.List[string]
    for ($i = 1; $i -le $comAddIns.Count; $i++) {
        $candidate = $comAddIns.Collection.Item($i)
        $seenProgIds.Add([string] $candidate.ProgId)
        if ($candidate.ProgId -eq $addinName) {
            $addin = $candidate
            break
        }
    }

    if (-not $addin) {
        throw "$addinName was not found in Word COMAddIns. Seen: $($seenProgIds -join ', ')"
    }

    if (-not $addin.Connect) {
        $addin.Connect = $true
        Start-Sleep -Seconds 2
    }

    if (-not $addin.Connect) {
        throw "$addinName was found but is not connected."
    }

    Write-Output "Word VSTO add-in loaded: $($addin.ProgId)"
}
finally {
    if ($word -and -not $LeaveWordOpen) {
        Quit-Word -Word $word -Process $process
    }
}

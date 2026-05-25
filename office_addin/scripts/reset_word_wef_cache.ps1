param(
    [switch]$KillOffice
)

$ErrorActionPreference = "Stop"

if ($KillOffice) {
    Get-Process WINWORD, POWERPNT, EXCEL -ErrorAction SilentlyContinue | Stop-Process -Force
}

$runningOffice = Get-Process WINWORD, POWERPNT, EXCEL -ErrorAction SilentlyContinue
if ($runningOffice) {
    throw "Close Word, PowerPoint, and Excel first, or run with -KillOffice."
}

$wefRoot = Join-Path $env:LOCALAPPDATA "Microsoft\Office\16.0\Wef"
if (Test-Path $wefRoot) {
    Remove-Item -LiteralPath $wefRoot -Recurse -Force
}

$wefReg = "HKCU:\Software\Microsoft\Office\16.0\WEF"
New-Item -Path $wefReg -Force | Out-Null
New-ItemProperty -Path $wefReg -Name "Word_RequireForceRefreshAtBoot" -PropertyType String -Value ([guid]::NewGuid().ToString("B")) -Force | Out-Null
New-ItemProperty -Path $wefReg -Name "Word_AggregatedCache" -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $wefReg -Name "Word_RibbonCache" -PropertyType DWord -Value 0 -Force | Out-Null
New-ItemProperty -Path $wefReg -Name "WordOMEXRefreshPending" -PropertyType DWord -Value 1 -Force | Out-Null

Write-Host "Word Office Add-in cache was reset."
Write-Host "Reopen Word and open Insert -> Add-ins / My Add-ins again."

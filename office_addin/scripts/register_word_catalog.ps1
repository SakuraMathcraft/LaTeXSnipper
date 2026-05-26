param(
    [string]$SharePath = "",
    [string]$CatalogId = "{7C4B0843-A874-420F-908C-73673C42F4B0}"
)

$ErrorActionPreference = "Stop"

if (-not $SharePath) {
    $SharePath = "\\$env:COMPUTERNAME\office_addin"
}

if (-not $SharePath.StartsWith("\\")) {
    throw "Office trusted catalogs require a UNC share path, for example \\$env:COMPUTERNAME\office_addin"
}

$catalogRoot = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
$catalogPath = Join-Path $catalogRoot $CatalogId

New-Item -Path $catalogPath -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Id" -PropertyType String -Value $CatalogId -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Url" -PropertyType String -Value $SharePath -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Flags" -PropertyType DWord -Value 1 -Force | Out-Null

Write-Host "Registered Office shared-folder add-in catalog:"
Write-Host "  $SharePath"
Write-Host "Close all Office apps, then reopen Word."

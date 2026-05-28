param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path -LiteralPath $InstallRoot).Path
$thumbprintFile = Join-Path $InstallRoot "tls\thumbprint.txt"
if (Test-Path -LiteralPath $thumbprintFile) {
    $thumbprint = (Get-Content -LiteralPath $thumbprintFile -Raw).Trim()
    foreach ($store in @("Cert:\CurrentUser\Root", "Cert:\CurrentUser\My")) {
        Remove-Item -LiteralPath (Join-Path $store $thumbprint) -Force -ErrorAction SilentlyContinue
    }
}
Remove-Item -LiteralPath (Join-Path $InstallRoot "tls") -Force -Recurse -ErrorAction SilentlyContinue

$wefBase = "HKCU:\Software\Microsoft\Office\16.0\WEF"
$devKey = Join-Path $wefBase "Developer"
$propNames = @(
    "7b6d0711-08ec-4a81-9c3f-3f8e0d6f6d21",
    "b5182ab2-5a84-45fb-81c4-67a725d6c7b1"
)
foreach ($name in $propNames) {
    Remove-ItemProperty -Path $devKey -Name $name -Force -ErrorAction SilentlyContinue
}

$productKey = "HKCU:\Software\LaTeXSnipper\OfficeAddin"
$installed = Get-ItemProperty -LiteralPath $productKey -Name "InstallRoot" -ErrorAction SilentlyContinue
if ($null -ne $installed -and [string]::Equals($installed.InstallRoot, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $productKey -Force -Recurse -ErrorAction SilentlyContinue
}

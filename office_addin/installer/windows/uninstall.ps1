param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"

$thumbprintFile = Join-Path $InstallRoot "tls\thumbprint.txt"
if (Test-Path -LiteralPath $thumbprintFile) {
    $thumbprint = (Get-Content -LiteralPath $thumbprintFile -Raw).Trim()
    foreach ($store in @("Cert:\CurrentUser\Root", "Cert:\CurrentUser\My")) {
        Remove-Item -LiteralPath (Join-Path $store $thumbprint) -Force -ErrorAction SilentlyContinue
    }
}

$wefBase = "HKCU:\Software\Microsoft\Office\16.0\WEF"
$addinIds = @(
    "{7b6d0711-08ec-4a81-9c3f-3f8e0d6f6d21}",
    "{b5182ab2-5a84-45fb-81c4-67a725d6c7b1}"
)
foreach ($id in $addinIds) {
    Remove-Item -LiteralPath (Join-Path $wefBase "Developer" $id) -Force -ErrorAction SilentlyContinue -Recurse
}
Remove-Item -LiteralPath (Join-Path $wefBase "TrustedCatalogs" "{7C4B0843-A874-420F-908C-73673C42F4B0}") -Force -ErrorAction SilentlyContinue -Recurse

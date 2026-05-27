param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [string]$CatalogId = "{7C4B0843-A874-420F-908C-73673C42F4B0}",
    [string]$ShareName = "LaTeXSnipperOfficeAddin$"
)

$ErrorActionPreference = "Stop"

$thumbprintFile = Join-Path $InstallRoot "tls\thumbprint.txt"
if (Test-Path -LiteralPath $thumbprintFile) {
    $thumbprint = (Get-Content -LiteralPath $thumbprintFile -Raw).Trim()
    foreach ($store in @("Cert:\CurrentUser\Root", "Cert:\CurrentUser\My")) {
        Remove-Item -LiteralPath (Join-Path $store $thumbprint) -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath (Join-Path "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs" $CatalogId) -Recurse -Force -ErrorAction SilentlyContinue
if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) {
    Remove-SmbShare -Name $ShareName -Force
}

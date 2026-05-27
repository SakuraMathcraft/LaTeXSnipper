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

param(
    [switch]$Force,
    [switch]$OpenInstaller
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$addinRoot = Resolve-Path (Join-Path $scriptDir "..")
$certDir = Join-Path $addinRoot ".certs\basic-ssl"
$certPem = Join-Path $certDir "_cert.pem"
$certCer = Join-Path $certDir "latexsnipper-office-dev.cer"

Push-Location $addinRoot
try {
    if ($Force -and (Test-Path $certDir)) {
        Remove-Item -LiteralPath $certDir -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path $certDir | Out-Null

    $nodeScript = @"
import { getCertificate } from '@vitejs/plugin-basic-ssl';
await getCertificate('.certs/basic-ssl', 'latexsnipper-office-dev', ['localhost', '127.0.0.1'], 3650);
"@
    $nodeScript | node --input-type=module

    if (-not (Test-Path $certPem)) {
        throw "Vite development certificate was not generated: $certPem"
    }

    $pem = Get-Content -Raw -Path $certPem
    $match = [regex]::Match(
        $pem,
        "-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----"
    )
    if (-not $match.Success) {
        throw "Generated Vite certificate does not contain a certificate block."
    }

    Set-Content -Path $certCer -Value $match.Value -Encoding ascii

    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certCer)

    Write-Host "Office add-in development certificate generated:"
    Write-Host "  $certCer"
    Write-Host "  Thumbprint: $($cert.Thumbprint)"
    Write-Host ""
    Write-Host "To trust it for Word/WebView2:"
    Write-Host "  1. Double-click the .cer file above."
    Write-Host "  2. Install Certificate..."
    Write-Host "  3. Current User"
    Write-Host "  4. Place all certificates in the following store"
    Write-Host "  5. Trusted Root Certification Authorities"
    Write-Host "  6. Confirm the security warning, then restart Word."

    if ($OpenInstaller) {
        Start-Process -FilePath $certCer
    }
}
finally {
    Pop-Location
}

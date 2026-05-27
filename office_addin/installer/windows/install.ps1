param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Pem {
    param([string]$Path, [string]$Label, [byte[]]$Bytes)
    $base64 = [Convert]::ToBase64String($Bytes, [Base64FormattingOptions]::InsertLineBreaks)
    $content = "-----BEGIN $Label-----`r`n$base64`r`n-----END $Label-----`r`n"
    [System.IO.File]::WriteAllText($Path, $content, [System.Text.Encoding]::ASCII)
}

function ConvertTo-DerLength {
    param([int]$Length)
    if ($Length -lt 128) {
        return [byte[]]@([byte]$Length)
    }
    $bytes = [BitConverter]::GetBytes($Length)
    [Array]::Reverse($bytes)
    $offset = 0
    while ($offset -lt ($bytes.Length - 1) -and $bytes[$offset] -eq 0) {
        $offset++
    }
    [byte[]]$value = $bytes[$offset..($bytes.Length - 1)]
    return [byte[]](@([byte](0x80 -bor $value.Length)) + $value)
}

function ConvertTo-DerInteger {
    param([byte[]]$Bytes)
    $offset = 0
    while ($offset -lt ($Bytes.Length - 1) -and $Bytes[$offset] -eq 0) {
        $offset++
    }
    [byte[]]$value = $Bytes[$offset..($Bytes.Length - 1)]
    if (($value[0] -band 0x80) -ne 0) {
        $value = [byte[]](@(0) + $value)
    }
    return [byte[]](@(0x02) + (ConvertTo-DerLength -Length $value.Length) + $value)
}

function ConvertTo-RsaPrivateKeyDer {
    param([System.Security.Cryptography.RSA]$Rsa)
    $parameters = $Rsa.ExportParameters($true)
    [byte[]]$body = @()
    foreach ($integer in @(
        [byte[]]@(0),
        $parameters.Modulus,
        $parameters.Exponent,
        $parameters.D,
        $parameters.P,
        $parameters.Q,
        $parameters.DP,
        $parameters.DQ,
        $parameters.InverseQ
    )) {
        $body += ConvertTo-DerInteger -Bytes $integer
    }
    return [byte[]](@(0x30) + (ConvertTo-DerLength -Length $body.Length) + $body)
}

$root = (Resolve-Path -LiteralPath $InstallRoot).Path
$tls = Join-Path $root "tls"
$thumbprintFile = Join-Path $tls "thumbprint.txt"
New-Item -ItemType Directory -Path $tls -Force | Out-Null

if (Test-Path -LiteralPath $thumbprintFile) {
    $oldThumbprint = (Get-Content -LiteralPath $thumbprintFile -Raw).Trim()
    foreach ($store in @("Cert:\CurrentUser\Root", "Cert:\CurrentUser\My")) {
        Remove-Item -LiteralPath (Join-Path $store $oldThumbprint) -Force -ErrorAction SilentlyContinue
    }
}

$certificate = New-SelfSignedCertificate `
    -Subject "CN=localhost" `
    -DnsName @("localhost") `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -KeyExportPolicy Exportable `
    -KeyUsage DigitalSignature, KeyEncipherment `
    -NotAfter (Get-Date).AddYears(10) `
    -FriendlyName "LaTeXSnipper Office Add-in localhost"

$rsa = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
if ($null -eq $rsa) {
    throw "Failed to export Office add-in TLS private key."
}

$certPath = Join-Path $tls "server.crt"
$keyPath = Join-Path $tls "server.key"
Write-Pem -Path $certPath -Label "CERTIFICATE" -Bytes $certificate.RawData
Write-Pem -Path $keyPath -Label "RSA PRIVATE KEY" -Bytes (ConvertTo-RsaPrivateKeyDer -Rsa $rsa)
Import-Certificate -FilePath $certPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
[System.IO.File]::WriteAllText($thumbprintFile, $certificate.Thumbprint, [System.Text.Encoding]::ASCII)

$wefBase = "HKCU:\Software\Microsoft\Office\16.0\WEF"
$addins = @(
    @{ Id = "{7b6d0711-08ec-4a81-9c3f-3f8e0d6f6d21}"; Name = "LaTeXSnipper Word"; Manifest = "manifest.word.xml" },
    @{ Id = "{b5182ab2-5a84-45fb-81c4-67a725d6c7b1}"; Name = "LaTeXSnipper PowerPoint"; Manifest = "manifest.powerpoint.xml" }
)
$manifestsDir = Join-Path $root "manifests"

$devKey = Join-Path $wefBase "Developer"
New-Item -Path $devKey -Force | Out-Null
foreach ($addin in $addins) {
    $manifestPath = Join-Path $manifestsDir $addin.Manifest
    $propName = $addin.Id.Trim('{').Trim('}')
    Remove-ItemProperty -Path $devKey -Name $propName -Force -ErrorAction SilentlyContinue
    New-ItemProperty -Path $devKey -Name $propName -PropertyType String -Value $manifestPath -Force | Out-Null
}

Write-Host "LaTeXSnipper Office local runtime and local sideload registration installed."
Write-Host "Restart LaTeXSnipper with the Office feature enabled, then restart Word and PowerPoint."
Write-Host "For managed production deployment, use the release manifests through Microsoft 365 Integrated apps."

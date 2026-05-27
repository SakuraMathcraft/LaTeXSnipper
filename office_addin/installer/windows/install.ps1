param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [string]$CatalogId = "{7C4B0843-A874-420F-908C-73673C42F4B0}",
    [string]$ShareName = "LaTeXSnipperOfficeAddin$"
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
$manifests = Join-Path $root "manifests"
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

$existingShare = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existingShare) {
    Remove-SmbShare -Name $ShareName -Force
}
New-SmbShare -Name $ShareName -Path $manifests -ReadAccess "Everyone" | Out-Null

$catalogRoot = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
$catalogPath = Join-Path $catalogRoot $CatalogId
$sharePath = "\\localhost\$ShareName"
New-Item -Path $catalogPath -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Id" -PropertyType String -Value $CatalogId -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Url" -PropertyType String -Value $sharePath -Force | Out-Null
New-ItemProperty -Path $catalogPath -Name "Flags" -PropertyType DWord -Value 1 -Force | Out-Null

Write-Host "LaTeXSnipper Office add-in installed."
Write-Host "Restart Word and PowerPoint, then add LaTeXSnipper from Shared Folder add-ins."

param(
    [string] $Configuration = "Debug",
    [string] $MSBuildPath = "D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
    [switch] $SkipBuild,
    [switch] $SkipCertificateTrust,
    [switch] $SkipVstoInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$projectPath = Join-Path $pluginRoot "hosts\WordVstoAddIn\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj"
$projectDir = Split-Path -Parent $projectPath
$addinName = "LaTeXSnipper.OfficePlugin.WordVstoAddIn"
$friendlyName = "LaTeXSnipper"
$description = "LaTeXSnipper native Word plugin"
$outputDir = Join-Path $projectDir "bin\$Configuration"
$deploymentManifest = Join-Path $outputDir "$addinName.vsto"
$userProps = Join-Path $projectDir "$addinName.user.props"
$devCertificateSubject = "CN=LaTeXSnipper Office Plugin Dev VSTO"

function Test-VstoSigningCertificate {
    param([Parameter(Mandatory = $true)] [System.Security.Cryptography.X509Certificates.X509Certificate2] $Certificate)

    try {
        return $Certificate.PrivateKey -is [System.Security.Cryptography.RSACryptoServiceProvider]
    }
    catch {
        return $false
    }
}

function Get-ManifestCertificate {
    if (-not (Test-Path -LiteralPath $userProps)) {
        return $null
    }

    [xml] $props = Get-Content -LiteralPath $userProps
    $thumbprint = [string] $props.Project.PropertyGroup.ManifestCertificateThumbprint
    if ([string]::IsNullOrWhiteSpace($thumbprint)) {
        return $null
    }

    $thumbprint = $thumbprint.Trim().Replace(" ", "")
    $cert = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Thumbprint -eq $thumbprint } |
        Select-Object -First 1
    return $cert
}

function Set-ManifestCertificateThumbprint {
    param([Parameter(Mandatory = $true)] [string] $Thumbprint)

    $xml = @"
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ManifestCertificateThumbprint>$Thumbprint</ManifestCertificateThumbprint>
  </PropertyGroup>
</Project>
"@
    Set-Content -LiteralPath $userProps -Value $xml -Encoding UTF8
}

function New-VstoSigningCertificate {
    New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $devCertificateSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
        -NotAfter (Get-Date).AddYears(5)
}

function Ensure-ManifestCertificate {
    $certificate = Get-ManifestCertificate
    if ($certificate -and (Test-VstoSigningCertificate -Certificate $certificate)) {
        return $certificate
    }

    $certificate = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $devCertificateSubject -and (Test-VstoSigningCertificate -Certificate $_) } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if (-not $certificate) {
        $certificate = New-VstoSigningCertificate
    }

    Set-ManifestCertificateThumbprint -Thumbprint $certificate.Thumbprint
    return $certificate
}

function Ensure-CertificateInStore {
    param(
        [Parameter(Mandatory = $true)] [System.Security.Cryptography.X509Certificates.X509Certificate2] $Certificate,
        [Parameter(Mandatory = $true)] [string] $StoreName
    )

    $storePath = "Cert:\CurrentUser\$StoreName"
    $existing = Get-ChildItem -Path $storePath -ErrorAction SilentlyContinue |
        Where-Object { $_.Thumbprint -eq $Certificate.Thumbprint } |
        Select-Object -First 1
    if ($existing) {
        return
    }

    $tempCertPath = Join-Path $env:TEMP "$($Certificate.Thumbprint).cer"
    try {
        Export-Certificate -Cert $Certificate -FilePath $tempCertPath | Out-Null
        Import-Certificate -FilePath $tempCertPath -CertStoreLocation $storePath | Out-Null
    }
    finally {
        Remove-Item -LiteralPath $tempCertPath -Force -ErrorAction SilentlyContinue
    }
}

function Clear-WordAddInResiliency {
    $resiliencyRoots = @(
        "HKCU:\Software\Microsoft\Office\Word\Resiliency",
        "HKCU:\Software\Microsoft\Office\16.0\Word\Resiliency"
    )

    foreach ($root in $resiliencyRoots) {
        foreach ($subkey in @("DisabledItems", "CrashingAddinList")) {
            $path = Join-Path $root $subkey
            if (-not (Test-Path -LiteralPath $path)) {
                continue
            }

            $item = Get-Item -LiteralPath $path
            foreach ($name in $item.GetValueNames()) {
                $value = $item.GetValue($name)
                $text = if ($value -is [byte[]]) {
                    ([System.Text.Encoding]::Unicode.GetString($value) + " " + [System.Text.Encoding]::ASCII.GetString($value))
                }
                else {
                    [string] $value
                }

                if ($text -like "*$addinName*") {
                    Remove-ItemProperty -LiteralPath $path -Name $name -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

function Get-VstoInstallerPath {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "VSTOInstaller.exe was not found. Install the Visual Studio Tools for Office runtime."
}

function Set-WordAddInRegistry {
    param([Parameter(Mandatory = $true)] [string] $ManifestPath)

    $manifestUri = ([System.Uri] (Resolve-Path -LiteralPath $ManifestPath).Path).AbsoluteUri + "|vstolocal"
    $registryPaths = @(
        "HKCU:\Software\Microsoft\Office\Word\Addins\$addinName",
        "HKCU:\Software\Microsoft\Office\16.0\Word\Addins\$addinName"
    )

    foreach ($registryPath in $registryPaths) {
        New-Item -Path $registryPath -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "Description" -Value $description -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "FriendlyName" -Value $friendlyName -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "LoadBehavior" -Value 3 -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "Manifest" -Value $manifestUri -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "CommandLineSafe" -Value 1 -PropertyType DWord -Force | Out-Null
    }
}

$certificate = Ensure-ManifestCertificate

if (-not $SkipBuild) {
    if (-not (Test-Path -LiteralPath $MSBuildPath)) {
        throw "MSBuild was not found at $MSBuildPath."
    }

    & $MSBuildPath $projectPath "/restore" "/t:Build;VisualStudioForApplicationsBuild;RegisterOfficeAddin" "/p:Configuration=$Configuration" "/p:VSTO_ProjectType=Application" "/nologo" "/v:minimal"
    if ($LASTEXITCODE -ne 0) {
        throw "MSBuild failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $deploymentManifest)) {
    throw "VSTO deployment manifest was not found at $deploymentManifest."
}

if (-not $SkipCertificateTrust) {
    if ($certificate) {
        Ensure-CertificateInStore -Certificate $certificate -StoreName "TrustedPublisher"
    }
}

if (-not $SkipVstoInstaller) {
    $installerPath = Get-VstoInstallerPath
    $installer = Start-Process -FilePath $installerPath -ArgumentList @("/Install", $deploymentManifest, "/Silent") -Wait -PassThru -WindowStyle Hidden
    if ($installer.ExitCode -ne 0) {
        throw "VSTOInstaller failed with exit code $($installer.ExitCode)."
    }
}

Clear-WordAddInResiliency
Set-WordAddInRegistry -ManifestPath $deploymentManifest

Write-Output "Registered $addinName for Word using $deploymentManifest."

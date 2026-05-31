$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:SigningCertificateSubject = "CN=LaTeXSnipper Office Plugin VSTO"

function Resolve-MSBuildPath {
    param([string] $RequestedPath)

    if ($RequestedPath -and (Test-Path -LiteralPath $RequestedPath)) {
        return $RequestedPath
    }

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $versions = & $vswhere -products * -requires Microsoft.Component.MSBuild -property installationPath
        foreach ($ver in $versions) {
            $msbuild = Join-Path $ver "MSBuild\Current\Bin\MSBuild.exe"
            $vsto = Join-Path $ver "MSBuild\Microsoft\VisualStudio\v17.0\OfficeTools\Microsoft.VisualStudio.Tools.Office.targets"
            if ((Test-Path -LiteralPath $msbuild) -and (Test-Path -LiteralPath $vsto)) {
                return $msbuild
            }
        }
    }

    $candidates = @(
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }

    $fromPath = (Get-Command MSBuild.exe -ErrorAction SilentlyContinue).Source
    if ($fromPath) { return $fromPath }

    throw "MSBuild was not found. Install Visual Studio 2022 or set MSBuildPath."
}

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
    param([Parameter(Mandatory = $true)] [string] $UserPropsPath)

    if (-not (Test-Path -LiteralPath $UserPropsPath)) {
        return $null
    }

    [xml] $props = Get-Content -LiteralPath $UserPropsPath
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
    param(
        [Parameter(Mandatory = $true)] [string] $UserPropsPath,
        [Parameter(Mandatory = $true)] [string] $Thumbprint
    )

    $xml = @"
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ManifestCertificateThumbprint>$Thumbprint</ManifestCertificateThumbprint>
  </PropertyGroup>
</Project>
"@
    Set-Content -LiteralPath $UserPropsPath -Value $xml -Encoding UTF8
}

function New-VstoSigningCertificate {
    New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $script:SigningCertificateSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
        -NotAfter (Get-Date).AddYears(5)
}

function Ensure-ManifestCertificate {
    param([Parameter(Mandatory = $true)] [string] $UserPropsPath)

    $certificate = Get-ManifestCertificate -UserPropsPath $UserPropsPath
    if ($certificate -and (Test-VstoSigningCertificate -Certificate $certificate)) {
        return $certificate
    }

    $certificate = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $script:SigningCertificateSubject -and (Test-VstoSigningCertificate -Certificate $_) } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if (-not $certificate) {
        $certificate = New-VstoSigningCertificate
    }

    Set-ManifestCertificateThumbprint -UserPropsPath $UserPropsPath -Thumbprint $certificate.Thumbprint
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

function Clear-OfficeAddInResiliency {
    param(
        [Parameter(Mandatory = $true)] [ValidateSet("Word", "PowerPoint")] [string] $OfficeApplication,
        [Parameter(Mandatory = $true)] [string] $AddInName
    )

    $resiliencyRoots = @(
        "HKCU:\Software\Microsoft\Office\$OfficeApplication\Resiliency",
        "HKCU:\Software\Microsoft\Office\16.0\$OfficeApplication\Resiliency"
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

                if ($text -like "*$AddInName*") {
                    Remove-ItemProperty -LiteralPath $path -Name $name -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

function Get-OfficeAddInRegistryPaths {
    param(
        [Parameter(Mandatory = $true)] [ValidateSet("Word", "PowerPoint")] [string] $OfficeApplication,
        [Parameter(Mandatory = $true)] [string] $AddInName,
        [Parameter(Mandatory = $true)] [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope
    )

    $root = if ($RegistryScope -eq "LocalMachine") { "HKLM:" } else { "HKCU:" }
    $paths = @(
        "$root\Software\Microsoft\Office\$OfficeApplication\Addins\$AddInName",
        "$root\Software\Microsoft\Office\16.0\$OfficeApplication\Addins\$AddInName"
    )

    if ($RegistryScope -eq "LocalMachine") {
        $paths += @(
            "$root\Software\WOW6432Node\Microsoft\Office\$OfficeApplication\Addins\$AddInName",
            "$root\Software\WOW6432Node\Microsoft\Office\16.0\$OfficeApplication\Addins\$AddInName"
        )
    }

    return $paths
}

function Set-OfficeAddInRegistry {
    param(
        [Parameter(Mandatory = $true)] [ValidateSet("Word", "PowerPoint")] [string] $OfficeApplication,
        [Parameter(Mandatory = $true)] [string] $AddInName,
        [Parameter(Mandatory = $true)] [string] $FriendlyName,
        [Parameter(Mandatory = $true)] [string] $Description,
        [Parameter(Mandatory = $true)] [string] $ManifestPath,
        [Parameter(Mandatory = $true)] [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope
    )

    $manifestUri = ([System.Uri] (Resolve-Path -LiteralPath $ManifestPath).Path).AbsoluteUri + "|vstolocal"
    $registryPaths = Get-OfficeAddInRegistryPaths -OfficeApplication $OfficeApplication -AddInName $AddInName -RegistryScope $RegistryScope

    foreach ($registryPath in $registryPaths) {
        New-Item -Path $registryPath -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "Description" -Value $Description -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "FriendlyName" -Value $FriendlyName -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "LoadBehavior" -Value 3 -PropertyType DWord -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "Manifest" -Value $manifestUri -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $registryPath -Name "CommandLineSafe" -Value 1 -PropertyType DWord -Force | Out-Null
    }
}

function Invoke-OfficeVstoRegistration {
    param(
        [Parameter(Mandatory = $true)] [ValidateSet("Word", "PowerPoint")] [string] $OfficeApplication,
        [Parameter(Mandatory = $true)] [string] $ProjectPath,
        [Parameter(Mandatory = $true)] [string] $AddInName,
        [Parameter(Mandatory = $true)] [string] $FriendlyName,
        [Parameter(Mandatory = $true)] [string] $Description,
        [Parameter(Mandatory = $true)] [string] $Configuration,
        [string] $MSBuildPath = "",
        [Parameter(Mandatory = $true)] [ValidateSet("CurrentUser", "LocalMachine")] [string] $RegistryScope,
        [string] $ManifestPath,
        [switch] $SkipBuild,
        [switch] $SkipCertificateTrust,
        [switch] $SkipVstoInstaller,
        [switch] $SkipOfficeRegistration
    )

    $projectDir = Split-Path -Parent $ProjectPath
    $outputDir = Join-Path $projectDir "bin\$Configuration"
    $deploymentManifest = if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        Join-Path $outputDir "$AddInName.vsto"
    }
    else {
        $ManifestPath
    }
    $userProps = Join-Path $projectDir "$AddInName.user.props"

    $certificate = if (Test-Path -LiteralPath $projectDir) {
        Ensure-ManifestCertificate -UserPropsPath $userProps
    }
    else {
        $null
    }

    if (-not $SkipBuild) {
        if (-not (Test-Path -LiteralPath $ProjectPath)) {
            throw "$OfficeApplication VSTO project was not found at $ProjectPath."
        }

        $MSBuildPath = Resolve-MSBuildPath -RequestedPath $MSBuildPath

        $targets = if ($SkipOfficeRegistration) {
            "Build;VisualStudioForApplicationsBuild"
        }
        else {
            "Build;VisualStudioForApplicationsBuild;RegisterOfficeAddin"
        }

        & $MSBuildPath $ProjectPath "/restore" "/t:$targets" "/p:Configuration=$Configuration" "/p:VSTO_ProjectType=Application" "/nologo" "/v:minimal"
        if ($LASTEXITCODE -ne 0) {
            throw "MSBuild failed with exit code $LASTEXITCODE."
        }
    }

    if (-not (Test-Path -LiteralPath $ProjectPath) -and [string]::IsNullOrWhiteSpace($ManifestPath)) {
        throw "$OfficeApplication VSTO project was not found at $ProjectPath. Create the VSTO shell or pass -ManifestPath to a packaged .vsto manifest."
    }

    if (-not (Test-Path -LiteralPath $deploymentManifest)) {
        throw "$OfficeApplication VSTO deployment manifest was not found at $deploymentManifest."
    }

    if (-not $SkipCertificateTrust) {
        if ($certificate) {
            Ensure-CertificateInStore -Certificate $certificate -StoreName "TrustedPublisher"
        }
    }

    if ((-not $SkipOfficeRegistration) -and (-not $SkipVstoInstaller)) {
        $installerPath = Get-VstoInstallerPath
        $installer = Start-Process -FilePath $installerPath -ArgumentList @("/Install", $deploymentManifest, "/Silent") -Wait -PassThru -WindowStyle Hidden
        if ($installer.ExitCode -ne 0) {
            throw "VSTOInstaller failed with exit code $($installer.ExitCode)."
        }
    }

    if (-not $SkipOfficeRegistration) {
        Clear-OfficeAddInResiliency -OfficeApplication $OfficeApplication -AddInName $AddInName
        Set-OfficeAddInRegistry `
            -OfficeApplication $OfficeApplication `
            -AddInName $AddInName `
            -FriendlyName $FriendlyName `
            -Description $Description `
            -ManifestPath $deploymentManifest `
            -RegistryScope $RegistryScope

        Write-Output "Registered $AddInName for $OfficeApplication using $deploymentManifest."
    }
    else {
        Write-Output "Built $AddInName for $OfficeApplication without Office registration."
    }
}

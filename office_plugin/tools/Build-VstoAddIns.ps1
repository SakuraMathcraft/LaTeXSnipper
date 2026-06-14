param(
    [string] $Configuration = "Release",
    [string] $MSBuildPath = "",
    [string] $CertificateOutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$windowsPowerShellModules = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\Modules"
Import-Module (
    Join-Path $windowsPowerShellModules "Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
) -ErrorAction Stop
Import-Module (Join-Path $windowsPowerShellModules "PKI\PKI.psd1") -ErrorAction Stop
if (-not (Get-PSDrive -Name Cert -ErrorAction SilentlyContinue)) {
    New-PSDrive -Name Cert -PSProvider Certificate -Root "\" | Out-Null
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$certificateSubject = "CN=LaTeXSnipper Office Plugin VSTO"

function Find-VstoBuildEnvironment {
    param([string] $RequestedMSBuildPath)

    $installationPaths = [System.Collections.Generic.List[string]]::new()
    if ($RequestedMSBuildPath) {
        if (-not (Test-Path -LiteralPath $RequestedMSBuildPath)) {
            throw "Requested MSBuild was not found: $RequestedMSBuildPath"
        }

        if ($RequestedMSBuildPath -match "^(.*)\\MSBuild\\Current\\Bin(?:\\amd64)?\\MSBuild\.exe$") {
            $installationPaths.Add($Matches[1])
        }
        else {
            throw "Requested MSBuild is not inside a Visual Studio installation: $RequestedMSBuildPath"
        }
    }
    else {
        $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
        if (Test-Path -LiteralPath $vswhere) {
            foreach ($installation in @(& $vswhere -products * -property installationPath)) {
                if ($installation) {
                    $installationPaths.Add($installation)
                }
            }
        }

        foreach ($candidate in @(
            "D:\Microsoft Visual Studio\2022\Community",
            "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community",
            "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community"
        )) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                $installationPaths.Add($candidate)
            }
        }
    }

    foreach ($installation in $installationPaths | Select-Object -Unique) {
        $msbuildCandidates = @(
            (Join-Path $installation "MSBuild\Current\Bin\MSBuild.exe"),
            (Join-Path $installation "MSBuild\Current\Bin\amd64\MSBuild.exe")
        )
        $msbuild = $msbuildCandidates |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
        if (-not $msbuild) {
            continue
        }

        $visualStudioTargetsRoot = Join-Path $installation "MSBuild\Microsoft\VisualStudio"
        if (-not (Test-Path -LiteralPath $visualStudioTargetsRoot)) {
            continue
        }

        $versionDirectories = Get-ChildItem -LiteralPath $visualStudioTargetsRoot -Directory |
            Where-Object { $_.Name -match "^v\d+\.\d+$" } |
            Sort-Object { [version]$_.Name.Substring(1) } -Descending
        foreach ($versionDirectory in $versionDirectories) {
            $officeTarget = Join-Path $versionDirectory.FullName "OfficeTools\Microsoft.VisualStudio.Tools.Office.targets"
            if (Test-Path -LiteralPath $officeTarget) {
                return [pscustomobject]@{
                    MSBuildPath = $msbuild
                    VisualStudioVersion = $versionDirectory.Name.Substring(1)
                    VSToolsPath = $versionDirectory.FullName
                }
            }
        }
    }

    throw "Visual Studio MSBuild with Microsoft.VisualStudio.Tools.Office.targets was not found."
}

function Test-VstoSigningCertificate {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2] $Certificate)

    $codeSigningOid = "1.3.6.1.5.5.7.3.3"
    $supportsCodeSigning = $Certificate.Extensions |
        Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] } |
        ForEach-Object { $_.EnhancedKeyUsages } |
        Where-Object { $_.Value -eq $codeSigningOid }
    if (-not $Certificate.HasPrivateKey -or -not $supportsCodeSigning) {
        return $false
    }

    try {
        return $Certificate.PrivateKey -is [System.Security.Cryptography.RSACryptoServiceProvider]
    }
    catch {
        return $false
    }
}

function Get-OrCreateSigningCertificate {
    $certificate = Get-ChildItem -Path Cert:\CurrentUser\My |
        Where-Object {
            $_.Subject -eq $certificateSubject -and
            (Test-VstoSigningCertificate -Certificate $_)
        } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if ($certificate) {
        return $certificate
    }

    return New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $certificateSubject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider" `
        -NotAfter (Get-Date).AddYears(5)
}

function Set-ManifestCertificate {
    param(
        [string] $ProjectPath,
        [string] $Thumbprint
    )

    $projectDirectory = Split-Path -Parent $ProjectPath
    $projectName = [System.IO.Path]::GetFileNameWithoutExtension($ProjectPath)
    $propsPath = Join-Path $projectDirectory "$projectName.user.props"
    $content = @"
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <ManifestCertificateThumbprint>$Thumbprint</ManifestCertificateThumbprint>
  </PropertyGroup>
</Project>
"@
    Set-Content -LiteralPath $propsPath -Value $content -Encoding UTF8
}

$environment = Find-VstoBuildEnvironment -RequestedMSBuildPath $MSBuildPath
$certificate = Get-OrCreateSigningCertificate
$certificatePath = if ($CertificateOutputPath) {
    $CertificateOutputPath
}
else {
    Join-Path $pluginRoot "installer\vsto-signing.cer"
}
$certificateDirectory = Split-Path -Parent $certificatePath
if ($certificateDirectory) {
    New-Item -ItemType Directory -Path $certificateDirectory -Force | Out-Null
}
Export-Certificate -Cert $certificate -FilePath $certificatePath -Type CERT -Force | Out-Null

Write-Host "VSTO MSBuild: $($environment.MSBuildPath)"
Write-Host "VSTO tools: $($environment.VSToolsPath)"

$projects = @(
    (Join-Path $pluginRoot "hosts\WordVstoAddIn\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj"),
    (Join-Path $pluginRoot "hosts\PowerPointVstoAddIn\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.csproj")
)
foreach ($project in $projects) {
    if (-not (Test-Path -LiteralPath $project)) {
        throw "VSTO project was not found: $project"
    }

    Set-ManifestCertificate -ProjectPath $project -Thumbprint $certificate.Thumbprint
    & $environment.MSBuildPath $project `
        "/restore" `
        "/t:Build;VisualStudioForApplicationsBuild" `
        "/p:Configuration=$Configuration" `
        "/p:VSTO_ProjectType=Application" `
        "/p:VisualStudioVersion=$($environment.VisualStudioVersion)" `
        "/p:VSToolsPath=$($environment.VSToolsPath)" `
        "/nologo" `
        "/v:minimal"
    if ($LASTEXITCODE -ne 0) {
        throw "MSBuild failed for $project with exit code $LASTEXITCODE."
    }
}

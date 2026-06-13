param(
    [string] $Configuration = "Release",
    [string] $MSBuildPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$certificateSubject = "CN=LaTeXSnipper Office Plugin VSTO"

function Resolve-MSBuildPath {
    param([string] $RequestedPath)

    if ($RequestedPath -and (Test-Path -LiteralPath $RequestedPath)) {
        return $RequestedPath
    }

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $installations = & $vswhere -products * -requires Microsoft.Component.MSBuild -property installationPath
        foreach ($installation in $installations) {
            $candidate = Join-Path $installation "MSBuild\Current\Bin\MSBuild.exe"
            $officeTargets = Join-Path $installation "MSBuild\Microsoft\VisualStudio\v17.0\OfficeTools\Microsoft.VisualStudio.Tools.Office.targets"
            if ((Test-Path -LiteralPath $candidate) -and (Test-Path -LiteralPath $officeTargets)) {
                return $candidate
            }
        }
    }

    $candidates = @(
        "D:\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles}\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    $fromPath = (Get-Command MSBuild.exe -ErrorAction SilentlyContinue).Source
    if ($fromPath) {
        return $fromPath
    }

    throw "MSBuild with the Visual Studio Office tools was not found."
}

function Test-VstoSigningCertificate {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2] $Certificate)

    try {
        return $Certificate.PrivateKey -is [System.Security.Cryptography.RSACryptoServiceProvider]
    }
    catch {
        return $false
    }
}

function Get-OrCreateSigningCertificate {
    $certificate = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert |
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

$msbuild = Resolve-MSBuildPath -RequestedPath $MSBuildPath
$certificate = Get-OrCreateSigningCertificate
$projects = @(
    (Join-Path $pluginRoot "hosts\WordVstoAddIn\LaTeXSnipper.OfficePlugin.WordVstoAddIn.csproj"),
    (Join-Path $pluginRoot "hosts\PowerPointVstoAddIn\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn.csproj")
)

foreach ($project in $projects) {
    if (-not (Test-Path -LiteralPath $project)) {
        throw "VSTO project was not found: $project"
    }

    Set-ManifestCertificate -ProjectPath $project -Thumbprint $certificate.Thumbprint
    & $msbuild $project `
        "/restore" `
        "/t:Build;VisualStudioForApplicationsBuild" `
        "/p:Configuration=$Configuration" `
        "/p:VSTO_ProjectType=Application" `
        "/nologo" `
        "/v:minimal"
    if ($LASTEXITCODE -ne 0) {
        throw "MSBuild failed for $project with exit code $LASTEXITCODE."
    }
}

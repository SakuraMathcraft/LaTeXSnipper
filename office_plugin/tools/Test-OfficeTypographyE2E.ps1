[CmdletBinding()]
param(
    [ValidateSet('Word', 'PowerPoint', 'Both')]
    [string]$HostScope = 'Both',

    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release',

    [ValidateSet('Omml', 'Ole', 'Both')]
    [string]$WordBackend = 'Both',

    [switch]$WordCopyOnly,
    [switch]$IncludeMathType,
    [switch]$WordMathTypeOnly,
    [switch]$WordMathTypeNativeEdit,
    [switch]$PowerPointMathTypeNativeEdit,

    [ValidateSet('Full', 'Batch', 'Copy', 'Gesture', 'MathType')]
    [string]$PowerPointMode = 'Full',
    [string]$OutputDirectory = (Join-Path $env:TEMP ('latexsnipper-office-' + [Guid]::NewGuid().ToString('N')))
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$pluginRoot = Split-Path -Parent $PSScriptRoot
if (Get-Process WINWORD, POWERPNT -ErrorAction SilentlyContinue) {
    throw 'Close Word and PowerPoint before running isolated Office tests.'
}
$runWord = $HostScope -in @('Word', 'Both')
$runPowerPoint = $HostScope -in @('PowerPoint', 'Both')
$needsOle = ($runWord -and $WordBackend -ne 'Omml') -or ($runPowerPoint -and $PowerPointMode -ne 'Batch')
if ($needsOle -and (-not [Environment]::Is64BitProcess -or
    (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration').Platform -ne 'x64')) {
    throw 'This Office integration runner requires 64-bit PowerShell and 64-bit Office.'
}
$handler = Join-Path $pluginRoot "hosts\OleFormulaObjectNative\bin\x64\$Configuration\LaTeXSnipper.OfficePlugin.OleFormulaObject.Handler.dll"
$wordTest = Join-Path $pluginRoot "tests\LaTeXSnipper.OfficePlugin.WordParsingE2E\bin\$Configuration\net48\LaTeXSnipper.OfficePlugin.WordParsingE2E.exe"
$pptTest = Join-Path $pluginRoot "tests\LaTeXSnipper.OfficePlugin.PowerPointE2E\bin\$Configuration\net48\LaTeXSnipper.OfficePlugin.PowerPointE2E.exe"
$requiredFiles = @()
if ($needsOle) { $requiredFiles += $handler }
if ($runWord) { $requiredFiles += $wordTest }
if ($runPowerPoint) { $requiredFiles += $pptTest }
foreach ($file in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Build the handler and managed solution first: $file" }
}
$clsid = '{B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F}'
$classes = 'HKCU:\Software\Classes'
$registrationRoots = if ($needsOle) { @("$classes\LaTeXSnipper.Formula", "$classes\LaTeXSnipper.Formula.1", "$classes\CLSID\$clsid") } else { @() }
foreach ($path in $registrationRoots) {
    if (Test-Path -LiteralPath $path) {
        $serverPath = "$classes\CLSID\$clsid\InprocServer32"
        $server = if (Test-Path -LiteralPath $serverPath) { Get-Item -LiteralPath $serverPath } else { $null }
        try {
            if ($server -and $server.GetValue('')) { throw "Existing user registration must not be overwritten: $path" }
        } finally { if ($server) { $server.Close() } }
    }
}
$createdRoots = [System.Collections.Generic.List[string]]::new()
$originalValues = [System.Collections.Generic.List[object]]::new()
function Set-TestRegistration([string]$Path, [string]$Value, [string]$Name = '') {
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($Path.Substring('HKCU:\'.Length))
    try {
        $originalValues.Add(@{ Path = $Path; Name = $Name; Exists = $key.GetValueNames() -contains $Name; Value = $key.GetValue($Name) })
        $key.SetValue($Name, $Value, [Microsoft.Win32.RegistryValueKind]::String)
    }
    finally { $key.Close() }
}
function Wait-OfficeExit([string]$Name) {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (Get-Process -Name $Name -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) { throw "Test Office process did not exit: $Name" }
        Start-Sleep -Milliseconds 200
    }
}
try {
    if ($needsOle) {
        foreach ($path in $registrationRoots) {
            if (-not (Test-Path -LiteralPath $path)) {
                New-Item -Path $path -Force | Out-Null
                $createdRoots.Add($path)
            }
            Set-TestRegistration $path 'LaTeXSnipper Formula'
        }
        Set-TestRegistration "$classes\LaTeXSnipper.Formula\CLSID" $clsid
        Set-TestRegistration "$classes\LaTeXSnipper.Formula.1\CLSID" $clsid
        $classPath = "$classes\CLSID\$clsid"
        Set-TestRegistration "$classPath\ProgID" 'LaTeXSnipper.Formula.1'
        Set-TestRegistration "$classPath\VersionIndependentProgID" 'LaTeXSnipper.Formula'
        Set-TestRegistration "$classPath\InprocServer32" $handler
        Set-TestRegistration "$classPath\InprocServer32" 'Apartment' 'ThreadingModel'
        Set-TestRegistration "$classPath\MiscStatus" '672272'
        Set-TestRegistration "$classPath\MiscStatus\1" '672272'
        $registered = Get-Item -LiteralPath "$classPath\InprocServer32"
        try {
            if ($registered.GetValue('') -ne $handler -or $registered.GetValue('ThreadingModel') -ne 'Apartment') {
                throw 'Temporary COM registration does not match the test handler.'
            }
        } finally { $registered.Close() }
    }
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    if ($runWord) {
        $backends = if ($WordBackend -eq 'Both') { @('omml', 'ole') } else { @($WordBackend.ToLowerInvariant()) }
        foreach ($backend in $backends) {
            $wordArgs = @('--backend', $backend, '--output', (Join-Path $OutputDirectory "word-$backend.docx"))
            if ($WordCopyOnly) { $wordArgs += '--copy' }
            if ($IncludeMathType) { $wordArgs += '--mathtype' }
            if ($WordMathTypeOnly) { $wordArgs += '--mathtype-only' }
            if ($WordMathTypeNativeEdit) { $wordArgs += '--mathtype-native-edit' }
            & $wordTest @wordArgs | Tee-Object -FilePath (Join-Path $OutputDirectory "word-$backend.log")
            if ($LASTEXITCODE -ne 0) { throw "Word $backend E2E failed: $LASTEXITCODE" }
            Wait-OfficeExit 'WINWORD'
        }
    }
    if ($runPowerPoint) {
        $mode = switch ($PowerPointMode) { 'Batch' { '--batch' } 'Copy' { '--copy' } 'Gesture' { '--gesture' } 'MathType' { '--mathtype-only' } default { '--ole' } }
        $pptArgs = @((Join-Path $OutputDirectory 'powerpoint.pptx'), $mode)
        if ($IncludeMathType -and $PowerPointMode -in @('Full', 'Copy')) { $pptArgs += '--mathtype' }
        if ($PowerPointMathTypeNativeEdit) { $pptArgs += '--mathtype-native-edit' }
        & $pptTest @pptArgs | Tee-Object -FilePath (Join-Path $OutputDirectory 'powerpoint.log')
        if ($LASTEXITCODE -ne 0) { throw "PowerPoint E2E failed: $LASTEXITCODE" }
    }
    Write-Host "PASS|Office typography|$OutputDirectory"
}
finally {
    foreach ($entry in $originalValues) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($entry.Path.Substring('HKCU:\'.Length), $true)
        try {
            if ($entry.Exists) { $key.SetValue($entry.Name, $entry.Value, [Microsoft.Win32.RegistryValueKind]::String) }
            else { $key.DeleteValue($entry.Name, $false) }
        } finally { $key.Close() }
    }
    foreach ($path in $createdRoots) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
    if ($needsOle) { Write-Host 'Temporary COM registration restored; machine registration unchanged.' }
}

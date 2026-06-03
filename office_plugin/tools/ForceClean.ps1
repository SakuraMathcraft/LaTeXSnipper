# ForceClean.ps1 — Clean LaTeXSnipper Office VSTO / ClickOnce artifacts

param(
    [switch]$KillOffice,
    [switch]$RemoveInstallDir,
    [string]$InstallRoot = ""
)

$ErrorActionPreference = "Continue"

$WordAddInName = "LaTeXSnipper.OfficePlugin.WordVstoAddIn"
$PowerPointAddInName = "LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn"
$AddInNames = @($WordAddInName, $PowerPointAddInName)
$Apps = @("Word", "PowerPoint")
$MatchPatterns = @(
    "*LaTeXSnipper.OfficePlugin*",
    "*LaTeXSnipper Office Plugin*",
    "*LaTeXSnipper\OfficePlugin*",
    "*LaTeXSnipper/OfficePlugin*",
    "*OfficePluginSetup-*"
)
$SigningCertificateSubjects = @(
    "CN=LaTeXSnipper Office Plugin VSTO"
)
$OleFormulaClassId = "{B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F}"
$OleFormulaProgIds = @(
    "LaTeXSnipper.Formula",
    "LaTeXSnipper.Formula.1"
)

if (-not [string]::IsNullOrWhiteSpace($InstallRoot)) {
    $resolvedInstallRoot = Convert-Path -LiteralPath $InstallRoot -ErrorAction SilentlyContinue
    if ($resolvedInstallRoot) {
        $InstallRoot = $resolvedInstallRoot
    }
}

Write-Host "=== Force Clean LaTeXSnipper VSTO ==="

function Test-MatchText {
    param([AllowNull()][object]$Value)
    $s = "$Value"
    foreach ($pattern in $script:MatchPatterns) {
        if ($s -like $pattern) { return $true }
    }
    return $false
}

function Remove-RegistryTree {
    param([string]$Path, [string]$Message)
    if (Test-Path $Path) {
        try {
            Remove-Item $Path -Recurse -Force -ErrorAction Stop
            Write-Host "$($Message): $Path"
        } catch {
            Write-Host "Failed to remove registry key: $Path -> $($_.Exception.Message)"
        }
    }
}

function Remove-RegistryChildrenByNameOrValue {
    param([string]$RootPath, [switch]$Recurse, [string]$Message)

    if (-not (Test-Path $RootPath)) { return }

    $items = @()
    try {
        if ($Recurse) {
            $items = Get-ChildItem $RootPath -Recurse -ErrorAction SilentlyContinue
        } else {
            $items = Get-ChildItem $RootPath -ErrorAction SilentlyContinue
        }
    } catch {
        return
    }

    $targets = New-Object System.Collections.Generic.HashSet[string]

    foreach ($item in $items) {
        $hit = $false

        if (Test-MatchText $item.PSChildName) {
            $hit = $true
        }

        if (-not $hit) {
            try {
                $props = Get-ItemProperty $item.PSPath -ErrorAction SilentlyContinue
                foreach ($prop in $props.PSObject.Properties) {
                    if ($prop.Name -match '^PS') { continue }
                    if ((Test-MatchText $prop.Name) -or (Test-MatchText $prop.Value)) {
                        $hit = $true
                        break
                    }
                }
            } catch {}
        }

        if ($hit) {
            [void]$targets.Add($item.PSPath)
        }
    }

    $targets |
        Sort-Object Length -Descending |
        ForEach-Object {
            try {
                Remove-Item $_ -Recurse -Force -ErrorAction Stop
                Write-Host "$($Message): $_"
            } catch {
                Write-Host "Failed to remove registry key: $_ -> $($_.Exception.Message)"
            }
        }
}

# 0. Optionally close Office processes
if ($KillOffice) {
    foreach ($proc in @("WINWORD", "POWERPNT")) {
        Get-Process $proc -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                Stop-Process -Id $_.Id -Force -ErrorAction Stop
                Write-Host "Killed process: $($_.ProcessName) [$($_.Id)]"
            } catch {
                Write-Host "Failed to kill process: $($_.ProcessName) [$($_.Id)] -> $($_.Exception.Message)"
            }
        }
    }
} else {
    $runningOffice = Get-Process WINWORD, POWERPNT -ErrorAction SilentlyContinue
    if ($runningOffice) {
        Write-Host "Warning: Word/PowerPoint is running. For deepest cleanup, rerun with -KillOffice after saving documents."
    }
}

# 1. Uninstall via VSTOInstaller from known manifest paths
$vstoInstallerCandidates = @(
    "${env:ProgramFiles(x86)}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe",
    "${env:ProgramFiles}\Common Files\Microsoft Shared\VSTO\10.0\VSTOInstaller.exe"
)

$vstoInstaller = $vstoInstallerCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

$knownManifestPaths = @(
    $(if ($InstallRoot) { Join-Path $InstallRoot "Word\$WordAddInName.vsto" }),
    $(if ($InstallRoot) { Join-Path $InstallRoot "PowerPoint\$PowerPointAddInName.vsto" }),
    "$env:ProgramFiles\LaTeXSnipper\OfficePlugin\Word\$WordAddInName.vsto",
    "$env:ProgramFiles\LaTeXSnipper\OfficePlugin\PowerPoint\$PowerPointAddInName.vsto",
    "${env:ProgramFiles(x86)}\LaTeXSnipper\OfficePlugin\Word\$WordAddInName.vsto",
    "${env:ProgramFiles(x86)}\LaTeXSnipper\OfficePlugin\PowerPoint\$PowerPointAddInName.vsto"
) | Where-Object { $_ }

if ($vstoInstaller) {
    foreach ($manifestPath in $knownManifestPaths) {
        if (Test-Path $manifestPath) {
            try {
                & $vstoInstaller /Uninstall $manifestPath /Silent 2>$null
                $code = $LASTEXITCODE
                Write-Host "VSTO uninstall attempted: $manifestPath, exit=$code"
            } catch {
                Write-Host "VSTO uninstall failed: $manifestPath -> $($_.Exception.Message)"
            }
        }
    }
} else {
    Write-Host "VSTOInstaller.exe not found; skip VSTOInstaller /Uninstall."
}

# 2. Clean VSTO metadata and security inclusion entries
$vstoRoots = @(
    "HKCU:\Software\Microsoft\VSTO",
    "HKLM:\Software\Microsoft\VSTO",
    "HKCU:\Software\WOW6432Node\Microsoft\VSTO",
    "HKLM:\Software\WOW6432Node\Microsoft\VSTO"
)

foreach ($root in $vstoRoots) {
    Remove-RegistryChildrenByNameOrValue -RootPath "$root\SolutionMetadata" -Recurse -Message "Removed VSTO SolutionMetadata"
    Remove-RegistryChildrenByNameOrValue -RootPath "$root\Security\Inclusion" -Recurse -Message "Removed VSTO Security Inclusion"
}

# 3. Clean Office Add-ins registry keys, including Office 365 ClickToRun virtualization
$softwareRoots = @(
    "HKCU:\Software",
    "HKLM:\Software",
    "HKCU:\Software\WOW6432Node",
    "HKLM:\Software\WOW6432Node"
)

foreach ($softwareRoot in $softwareRoots) {
    foreach ($app in $Apps) {
        $addinParents = @(
            "$softwareRoot\Microsoft\Office\$app\Addins",
            "$softwareRoot\Microsoft\Office\16.0\$app\Addins",
            "$softwareRoot\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\$app\Addins",
            "$softwareRoot\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\$app\Addins"
        )

        foreach ($parent in $addinParents) {
            foreach ($addinName in $AddInNames) {
                Remove-RegistryTree -Path "$parent\$addinName" -Message "Removed Office add-in key"
            }

            Remove-RegistryChildrenByNameOrValue -RootPath $parent -Message "Removed Office add-in child"
        }
    }
}

# 4. Clean ClickOnce / Deployment registry stores
$deploymentStores = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Deployment\SubscriptionStore",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Deployment\ActivationData",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Deployment\SideBySide",
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Deployment\PackageMetadata",
    "HKCU:\Software\Classes\Software\Microsoft\Windows\CurrentVersion\Deployment\SubscriptionStore",
    "HKCU:\Software\Classes\Software\Microsoft\Windows\CurrentVersion\Deployment\ActivationData"
)

foreach ($store in $deploymentStores) {
    Remove-RegistryChildrenByNameOrValue -RootPath $store -Recurse -Message "Removed ClickOnce deployment registry"
}

# 5. Clean Windows uninstall entries
$uninstallRoots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKCU:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)

foreach ($root in $uninstallRoots) {
    Remove-RegistryChildrenByNameOrValue -RootPath $root -Message "Removed uninstall entry"
}

# 5.1 Clean only plugin settings under the shared LaTeXSnipper vendor key.
Remove-RegistryTree -Path "HKCU:\Software\LaTeXSnipper\OfficePlugin" -Message "Removed plugin settings"

# 5.2 Clean stale OLE formula registrations before the installer writes the
# current static display-only server registration.
foreach ($progId in $OleFormulaProgIds) {
    Remove-RegistryTree -Path "HKCU:\Software\Classes\$progId" -Message "Removed OLE ProgID"
    Remove-RegistryTree -Path "HKCU:\Software\Classes\WOW6432Node\$progId" -Message "Removed OLE ProgID"
    Remove-RegistryTree -Path "HKLM:\Software\Classes\$progId" -Message "Removed OLE ProgID"
    Remove-RegistryTree -Path "HKLM:\Software\WOW6432Node\Classes\$progId" -Message "Removed OLE ProgID"
}
Remove-RegistryTree -Path "HKCU:\Software\Classes\CLSID\$OleFormulaClassId" -Message "Removed OLE CLSID"
Remove-RegistryTree -Path "HKCU:\Software\Classes\WOW6432Node\CLSID\$OleFormulaClassId" -Message "Removed OLE CLSID"
Remove-RegistryTree -Path "HKLM:\Software\Classes\CLSID\$OleFormulaClassId" -Message "Removed OLE CLSID"
Remove-RegistryTree -Path "HKLM:\Software\WOW6432Node\Classes\CLSID\$OleFormulaClassId" -Message "Removed OLE CLSID"

# 6. Clean Office Resiliency records
foreach ($app in $Apps) {
    foreach ($ver in @("", "16.0")) {
        $base = if ($ver) { "HKCU:\Software\Microsoft\Office\$ver\$app\Resiliency" } else { "HKCU:\Software\Microsoft\Office\$app\Resiliency" }
        foreach ($sub in @("DisabledItems", "CrashingAddinList", "DoNotDisableAddinList", "StartupItems")) {
            $keyPath = "$base\$sub"
            if (-not (Test-Path $keyPath)) { continue }

            try {
                $props = Get-ItemProperty $keyPath -ErrorAction SilentlyContinue
                foreach ($prop in $props.PSObject.Properties) {
                    if ($prop.Name -match '^PS') { continue }
                    if ((Test-MatchText $prop.Name) -or (Test-MatchText $prop.Value)) {
                        Remove-ItemProperty -Path $keyPath -Name $prop.Name -Force -ErrorAction SilentlyContinue
                        Write-Host "Cleaned Office resiliency: $keyPath -> $($prop.Name)"
                    }
                }
            } catch {}
        }
    }
}

# 7. Robust ClickOnce local cache cleanup under %LOCALAPPDATA%\Apps\2.0
$cacheRoot = Join-Path $env:LocalAppData "Apps\2.0"

if (Test-Path $cacheRoot) {
    $targets = New-Object System.Collections.Generic.HashSet[string]

    # 7.1 Match by file/folder names and full paths
    Get-ChildItem $cacheRoot -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object {
            Test-MatchText $_.Name -or
            Test-MatchText $_.FullName
        } |
        ForEach-Object {
            $dir = if ($_.PSIsContainer) { $_ } else { $_.Directory }
            if ($dir -and $dir.FullName -ne $cacheRoot) {
                [void]$targets.Add($dir.FullName)
            }
        }

    # 7.2 Match by manifest / deployment metadata content
    Get-ChildItem $cacheRoot -Recurse -Force -Include "*.manifest", "*.vsto", "*.application", "*.cdf-ms", "*.config" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $content = $null
            try {
                $content = Get-Content $_.FullName -Raw -ErrorAction Stop
            } catch {
                $content = $null
            }

            if ($content -and (Test-MatchText $content)) {
                if ($_.Directory -and $_.Directory.FullName -ne $cacheRoot) {
                    [void]$targets.Add($_.Directory.FullName)
                }
            }
        }

    # 7.3 Prefer deleting the concrete application cache leaf folders, not the whole Apps\2.0 root
    $targets |
        Sort-Object Length -Descending |
        ForEach-Object {
            if (Test-Path $_) {
                try {
                    Remove-Item $_ -Recurse -Force -ErrorAction Stop
                    Write-Host "Removed ClickOnce cache: $_"
                } catch {
                    Write-Host "Failed to remove ClickOnce cache: $_ -> $($_.Exception.Message)"
                }
            }
        }

    # 7.4 Remove empty parent directories left under Apps\2.0
    Get-ChildItem $cacheRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object {
            try {
                $hasChild = Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Select-Object -First 1
                if (-not $hasChild) {
                    Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
}

# 8. Clean VSTO signing certificates used only by this add-in
$certStorePaths = @(
    "Cert:\CurrentUser\Root",
    "Cert:\CurrentUser\TrustedPublisher",
    "Cert:\LocalMachine\Root",
    "Cert:\LocalMachine\TrustedPublisher"
)

foreach ($store in $certStorePaths) {
    if (-not (Test-Path $store)) { continue }

    Get-ChildItem $store -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Subject -in $script:SigningCertificateSubjects -or
            $_.FriendlyName -like "*LaTeXSnipper Office Plugin*"
        } |
        ForEach-Object {
            try {
                $thumbprint = $_.Thumbprint
                Remove-Item $_.PSPath -Force -ErrorAction Stop
                Write-Host "Removed certificate: $store -> $thumbprint -> $($_.Subject)"
            } catch {
                Write-Host "Failed to remove certificate: $store -> $($_.Subject) -> $($_.Exception.Message)"
            }
        }
}

# 9. Optionally remove physical install directories
if ($RemoveInstallDir) {
    $installDirs = @(
        $InstallRoot,
        "$env:ProgramFiles\LaTeXSnipper\OfficePlugin",
        "${env:ProgramFiles(x86)}\LaTeXSnipper\OfficePlugin"
    ) | Where-Object { $_ } | Select-Object -Unique

    foreach ($dir in $installDirs) {
        if (Test-Path $dir) {
            try {
                Remove-Item $dir -Recurse -Force -ErrorAction Stop
                Write-Host "Removed install directory: $dir"
            } catch {
                Write-Host "Failed to remove install directory: $dir -> $($_.Exception.Message)"
            }
        }
    }
}

# 10. Clean plugin-owned local caches and temporary rendered PowerPoint files
$localPluginRoot = Join-Path $env:LocalAppData "LaTeXSnipper\OfficePlugin"
if (Test-Path $localPluginRoot) {
    try {
        Remove-Item -LiteralPath $localPluginRoot -Recurse -Force -ErrorAction Stop
        Write-Host "Removed local plugin cache: $localPluginRoot"
    } catch {
        Write-Host "Failed to remove local plugin cache: $localPluginRoot -> $($_.Exception.Message)"
    }
}

$powerPointTempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "LaTeXSnipper\OfficePlugin\PowerPoint"
if (Test-Path $powerPointTempRoot) {
    try {
        Remove-Item -LiteralPath $powerPointTempRoot -Recurse -Force -ErrorAction Stop
        Write-Host "Removed PowerPoint temp files: $powerPointTempRoot"
    } catch {
        Write-Host "Failed to remove PowerPoint temp files: $powerPointTempRoot -> $($_.Exception.Message)"
    }
}

Write-Host "=== Force clean complete ==="

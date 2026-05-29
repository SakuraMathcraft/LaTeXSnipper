#Requires -RunAsAdministrator
$ErrorActionPreference = "SilentlyContinue"

Get-Process WINWORD, POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2

Write-Host "=== NUCLEAR CLEANUP ==="

# 1. All registry
foreach ($app in @("Word", "PowerPoint")) {
  foreach ($root in @("HKCU:", "HKLM:")) {
    foreach ($wow in @("", "WOW6432Node")) {
      foreach ($ver in @("", "16.0")) {
        $base = "$root\Software"
        if ($wow) { $base += "\$wow" }
        $base += "\Microsoft\Office"
        if ($ver) { $base += "\$ver" }
        $kp = "$base\$app\Addins\LaTeXSnipper.OfficePlugin.*"
        Remove-Item $kp -Recurse -Force
      }
    }
  }
}

# 2. VSTO Metadata
Get-ChildItem "HKCU:\Software\Microsoft\VSTO\SolutionMetadata" -ErrorAction SilentlyContinue | ForEach-Object {
  $vals = Get-ItemProperty $_.PSPath
  $found = $false
  foreach ($p in $vals.PSObject.Properties) {
    $v = [string]$p.Value
    if ($v -like "*LaTeX*" -or $v -like "*WordVsto*" -or $v -like "*PowerPointVsto*") { $found = $true; break }
  }
  if ($found) {
    Remove-Item $_.PSPath -Recurse -Force
    Write-Host "Removed VSTO metadata: $($_.PSChildName)"
  }
}

# 3. VSTO Security
Get-ChildItem "HKCU:\Software\Microsoft\VSTO\Security\Inclusion" -ErrorAction SilentlyContinue | ForEach-Object {
  $url = (Get-ItemProperty $_.PSPath).Url
  if ([string]$url -like "*LaTeX*") {
    Remove-Item $_.PSPath -Recurse -Force
    Write-Host "Removed VSTO security: $($_.PSChildName)"
  }
}

# 4. ClickOnce caches
foreach ($dir in @("$env:LocalAppData\Apps\2.0", "$env:ProgramData\Microsoft\VSTO")) {
  if (Test-Path $dir) {
    Remove-Item $dir -Recurse -Force
    Write-Host "Removed: $dir"
  }
}

# 5. HKCU Uninstall
Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue | ForEach-Object {
  $dn = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName
  if ($dn -like "*LaTeXSnipper.OfficePlugin*") {
    Remove-Item $_.PSPath -Recurse -Force
    Write-Host "Removed HKCU uninstall: $dn"
  }
}

# 6. HKLM Uninstall (Inno)
foreach ($wow in @("", "WOW6432Node")) {
  $base = if ($wow) { "HKLM:\Software\$wow\Microsoft\Windows\CurrentVersion\Uninstall" } else { "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall" }
  Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
    $dn = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).DisplayName
    if ($dn -like "*LaTeXSnipper Office Plugin*") {
      Remove-Item $_.PSPath -Recurse -Force
      Write-Host "Removed HKLM uninstall: $dn"
    }
  }
}

# 7. Resiliency
foreach ($app in @("Word", "PowerPoint")) {
  foreach ($ver in @("", "16.0")) {
    $r = "HKCU:\Software\Microsoft\Office"
    if ($ver) { $r += "\$ver" }
    $r += "\$app\Resiliency"
    foreach ($sub in @("DisabledItems", "CrashingAddinList")) {
      $rp = "$r\$sub"
      if (Test-Path $rp) {
        Get-ItemProperty $rp -ErrorAction SilentlyContinue | ForEach-Object { $_.PSObject.Properties } | Where-Object {
          $_.Name -like "*LaTeX*"
        } | ForEach-Object {
          Remove-ItemProperty $rp -Name $_.Name -Force
          Write-Host "Removed resiliency: $rp\$($_.Name)"
        }
      }
    }
  }
}

# 8. Program Files
$pf = "C:\Program Files\LaTeXSnipper\OfficePlugin"
if (Test-Path $pf) {
  Remove-Item $pf -Recurse -Force
  Write-Host "Removed: $pf"
}

Write-Host "=== NUCLEAR CLEANUP COMPLETE ==="
Write-Host "Now run OfficePluginSetup-2.3.2.exe to reinstall."

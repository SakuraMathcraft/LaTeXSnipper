Write-Host "=== HKCU Office Addins ==="
foreach ($app in @("Word", "PowerPoint")) {
  foreach ($ver in @("", "16.0")) {
    $base = if ($ver) { "Software\Microsoft\Office\$ver\$app\Addins" } else { "Software\Microsoft\Office\$app\Addins" }
    Get-ChildItem "HKCU:\$base" -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like "*LaTeX*" } | ForEach-Object { Write-Host "  FOUND: HKCU:\$base\$($_.PSChildName)" }
  }
}

Write-Host "=== HKLM Office Addins ==="
foreach ($app in @("Word", "PowerPoint")) {
  foreach ($wow in @("", "WOW6432Node")) {
    foreach ($ver in @("", "16.0")) {
      $path = if ($wow) { "Software\$wow\Microsoft\Office" } else { "Software\Microsoft\Office" }
      if ($ver) { $path += "\$ver" }
      $path += "\$app\Addins"
      Get-ChildItem "HKLM:\$path" -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like "*LaTeX*" } | ForEach-Object { Write-Host "  FOUND: HKLM:\$path\$($_.PSChildName)" }
    }
  }
}

Write-Host "=== HKCU VSTO SolutionMetadata ==="
Get-ChildItem "HKCU:\Software\Microsoft\VSTO\SolutionMetadata" -ErrorAction SilentlyContinue | ForEach-Object {
  $vals = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
  $found = $false
  foreach ($p in $vals.PSObject.Properties) {
    if ($p.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider")) {
      if (([string]$p.Value) -like "*LaTeX*") { $found = $true }
    }
  }
  if ($found) { Write-Host "  FOUND: VSTO Metadata key $($_.PSChildName)" }
}

Write-Host "=== HKCU Resiliency ==="
foreach ($app in @("Word", "PowerPoint")) {
  foreach ($ver in @("", "16.0")) {
    $base = if ($ver) { "Software\Microsoft\Office\$ver\$app\Resiliency" } else { "Software\Microsoft\Office\$app\Resiliency" }
    foreach ($sub in @("DisabledItems", "CrashingAddinList")) {
      $kp = "HKCU:\$base\$sub"
      if (Test-Path $kp) {
        Get-ItemProperty $kp -ErrorAction SilentlyContinue | ForEach-Object { $_.PSObject.Properties } | Where-Object {
          $_.Name -notin @("PSPath","PSParentPath","PSChildName","PSDrive","PSProvider") -and $_.Name -like "*LaTeX*"
        } | ForEach-Object { Write-Host "  FOUND: $kp -> $($_.Name)" }
      }
    }
  }
}

Write-Host "=== ClickOnce Cache ==="
$cache = Join-Path $env:LocalAppData "Apps\2.0"
if (Test-Path $cache) {
  $vstos = Get-ChildItem $cache -Recurse -Filter "*.vsto" -ErrorAction SilentlyContinue
  foreach ($f in $vstos) {
    $content = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($content -like "*LaTeXSnipper.OfficePlugin*" -or
        $content -like "*LaTeXSnipper Office Plugin*" -or
        $content -like "*LaTeXSnipper\OfficePlugin*" -or
        $content -like "*LaTeXSnipper/OfficePlugin*") {
      Write-Host "  FOUND: $($f.FullName)"
    }
  }
}

Write-Host "=== Installed Programs ==="
Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" 2>$null | Where-Object { $_.DisplayName -like "*LaTeX*" } | ForEach-Object { Write-Host "  FOUND: $($_.DisplayName)" }
Get-ItemProperty "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*" 2>$null | Where-Object { $_.DisplayName -like "*LaTeX*" } | ForEach-Object { Write-Host "  FOUND (WOW): $($_.DisplayName)" }

$foundAny = $false
Write-Host "`n=== RESULT ==="
if (-not $foundAny) { Write-Host "Clean - no LaTeXSnipper Office Plugin registry entries found." }

param(
  [string]$InstallRoot = ""
)

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
  $InstallRoot = Join-Path $env:ProgramFiles "LaTeXSnipper\OfficePlugin"
}

Write-Host "=== Word HKLM Registry ==="
$kp = "HKLM:\Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn"
if (Test-Path $kp) {
  $p = Get-ItemProperty $kp
  Write-Host "LoadBehavior: $($p.LoadBehavior)"
  Write-Host "Manifest: $($p.Manifest)"
} else { Write-Host "MISSING" }

Write-Host "=== Word 16.0 ==="
$kp16 = "HKLM:\Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn"
Write-Host "Exists: $(Test-Path $kp16)"

Write-Host "=== PPT ==="
$kpp = "HKLM:\Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn"
Write-Host "Exists: $(Test-Path $kpp)"

Write-Host "=== ClickOnce Apps Cache ==="
$apps = "$env:LocalAppData\Apps\2.0"
if (Test-Path $apps) {
  $vstos = Get-ChildItem $apps -Recurse -Filter "*.vsto" -ErrorAction SilentlyContinue
  foreach ($f in $vstos) {
    $c = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
    if ($c -like "*LaTeXSnipper.OfficePlugin*" -or
        $c -like "*LaTeXSnipper Office Plugin*" -or
        $c -like "*LaTeXSnipper\OfficePlugin*" -or
        $c -like "*LaTeXSnipper/OfficePlugin*") {
      Write-Host "CACHED: $($f.FullName)"
    }
  }
}

Write-Host "=== VSTO Security Inclusions ==="
Get-ChildItem "HKCU:\Software\Microsoft\VSTO\Security\Inclusion" -ErrorAction SilentlyContinue | ForEach-Object {
  $url = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).Url
  if ([string]$url -like "*LaTeX*") { Write-Host "$($_.PSChildName): $url" }
}

Write-Host "=== Word Resiliency ==="
foreach ($ver in @("", "16.0")) {
  $r = "HKCU:\Software\Microsoft\Office"
  if ($ver) { $r += "\$ver" }
  foreach ($sub in @("DisabledItems", "CrashingAddinList")) {
    $rp = "$r\Word\Resiliency\$sub"
    if (Test-Path $rp) {
      (Get-ItemProperty $rp -ErrorAction SilentlyContinue).PSObject.Properties | Where-Object {
        $_.Name -notin @("PSPath", "PSParentPath", "PSChildName", "PSDrive", "PSProvider")
      } | ForEach-Object { Write-Host "$sub`: $($_.Name)" }
    }
  }
}

Write-Host "=== Manifest file check ==="
$mf = Join-Path $InstallRoot "Word\LaTeXSnipper.OfficePlugin.WordVstoAddIn.vsto"
Write-Host "Manifest exists: $(Test-Path $mf)"
if (Test-Path $mf) {
  $xml = [xml](Get-Content $mf)
  Write-Host "Identity: $($xml.assembly.assemblyIdentity.name) v$($xml.assembly.assemblyIdentity.version)"
  Write-Host "PublicKey: $($xml.assembly.assemblyIdentity.publicKeyToken)"
}

Write-Host "Done"

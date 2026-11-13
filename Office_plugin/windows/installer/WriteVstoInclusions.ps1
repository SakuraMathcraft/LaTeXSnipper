param(
    [Parameter(Mandatory = $true)] [string] $ManifestPath,
    [Parameter(Mandatory = $false)] [ValidateSet("HKCU", "HKLM", "Both")] [string] $Target = "Both"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    Write-Error "Manifest not found: $ManifestPath"
    exit 1
}

# Read the VSTO manifest
[xml] $manifest = Get-Content -LiteralPath $ManifestPath

# Extract the RSAKeyValue from the signed manifest
$ns = New-Object Xml.XmlNamespaceManager $manifest.NameTable
$ns.AddNamespace("asmv1", "urn:schemas-microsoft-com:asm.v1")
$ns.AddNamespace("dsig", "http://www.w3.org/2000/09/xmldsig#")

$rsaNode = $manifest.SelectSingleNode("//dsig:Signature/dsig:KeyInfo/dsig:KeyValue/dsig:RSAKeyValue", $ns)
if (-not $rsaNode) {
    Write-Error "Could not find RSAKeyValue in manifest signature"
    exit 1
}

$modulus = $rsaNode.Modulus
$exponent = $rsaNode.Exponent
$publicKey = "<RSAKeyValue><Modulus>$modulus</Modulus><Exponent>$exponent</Exponent></RSAKeyValue>"

# Compute deployment URL in the format VSTO expects: file:/// + path with forward slashes
# Do NOT use [System.Uri] — it encodes spaces as %20 which VSTO won't match
$manifestUri = "file:///" + $ManifestPath.Replace('\', '/')

# Generate a deterministic GUID-based key for the inclusion entry
$urlBytes = [System.Text.Encoding]::UTF8.GetBytes($manifestUri.ToLowerInvariant())
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$hash = $sha256.ComputeHash($urlBytes)
$guidBytes = [byte[]] ($hash[0..15])
$guid = ([Guid]::new($guidBytes)).ToString("D")

# Write to HKCU — Word requires HKCU inclusion entries (HKLM is not read by Word's VSTO runtime)
# When called with runasoriginaluser, this targets the actual user, not the admin account
if ($Target -in @("HKCU", "Both")) {
    $hkcuPath = "HKCU:\Software\Microsoft\VSTO\Security\Inclusion\$guid"
    New-Item -Path $hkcuPath -Force -ErrorAction SilentlyContinue | Out-Null
    if (Test-Path $hkcuPath) {
        New-ItemProperty -Path $hkcuPath -Name "Url" -Value $manifestUri -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $hkcuPath -Name "PublicKey" -Value $publicKey -PropertyType String -Force | Out-Null
        Write-Output "VSTO inclusion (HKCU): $manifestUri"
    } else {
        Write-Warning "Could not create HKCU inclusion (not admin for this user): $manifestUri"
    }
}

# Write to HKLM — PPT trusts via machine-wide inclusions; requires admin
if ($Target -in @("HKLM", "Both")) {
    $hklmPath = "HKLM:\Software\Microsoft\VSTO\Security\Inclusion\$guid"
    New-Item -Path $hklmPath -Force -ErrorAction SilentlyContinue | Out-Null
    if (Test-Path $hklmPath) {
        New-ItemProperty -Path $hklmPath -Name "Url" -Value $manifestUri -PropertyType String -Force | Out-Null
        New-ItemProperty -Path $hklmPath -Name "PublicKey" -Value $publicKey -PropertyType String -Force | Out-Null
        Write-Output "VSTO inclusion (HKLM): $manifestUri"
    } else {
        Write-Warning "Could not create HKLM inclusion (admin required): $manifestUri"
    }
}

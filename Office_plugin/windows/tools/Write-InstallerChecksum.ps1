param(
  [Parameter(Mandatory = $true)]
  [string]$Path
)

$ErrorActionPreference = "Stop"

$resolvedPath = (Resolve-Path -LiteralPath $Path).Path
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$stream = [System.IO.File]::OpenRead($resolvedPath)
try {
  $hashBytes = $sha256.ComputeHash($stream)
}
finally {
  $stream.Dispose()
  $sha256.Dispose()
}

$hash = -join ($hashBytes | ForEach-Object { $_.ToString("x2") })
$fileName = [System.IO.Path]::GetFileName($resolvedPath)
[System.IO.File]::WriteAllText($resolvedPath + ".sha256", $hash + "  " + $fileName + [Environment]::NewLine, [System.Text.Encoding]::ASCII)

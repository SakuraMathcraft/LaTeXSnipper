param(
    [int]$Port = 8765,
    [string]$Token = $env:LATEXSNIPPER_OFFICE_BRIDGE_TOKEN
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $repoRoot "tools\deps\python311\python.exe"
$srcPath = Join-Path $repoRoot "src"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python runtime not found: $pythonExe"
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = "dev-token"
}

$env:LATEXSNIPPER_OFFICE_BRIDGE_TOKEN = $Token

$code = "import sys; sys.path.insert(0, r'$srcPath'); from integration.office.dev_server import main; raise SystemExit(main())"
& $pythonExe -c $code --port $Port --token $Token

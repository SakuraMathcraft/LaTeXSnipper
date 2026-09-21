param(
    [string]$RepoRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [string]$DataRoot = (Join-Path (Split-Path $RepoRoot -Parent) "MathCraftBenchData"),
    [string]$CdmDir = (Join-Path $DataRoot "sources\UniMERNet_official\cdm"),
    [string]$Python = (Join-Path $RepoRoot "tools\deps\python311\python.exe"),
    [string]$InputPath = (Join-Path $DataRoot "runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json"),
    [string]$OutputDir = (Join-Path $DataRoot "runs\cdm_official_unimer_full"),
    [string]$PathPrepend = (Join-Path $DataRoot "tools\unix_shims"),
    [int]$ShardSize = 100,
    [int]$Pools = 8,
    [int]$StartOffset = 0,
    [int]$Limit = 0,
    [int]$MaxShards = 0,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($Pools -gt 8) {
    Write-Warning "Pools=$Pools is above the locally validated setting. Use this only after a bounded validation run."
}

$runner = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\reports\run_official_cdm.py"

foreach ($path in @($runner, $CdmDir, $Python, $InputPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

$argsList = @(
    $runner,
    "--input", $InputPath,
    "--output-dir", $OutputDir,
    "--cdm-dir", $CdmDir,
    "--python", $Python,
    "--path-prepend", $pathPrepend,
    "--shard-size", $ShardSize,
    "--pools", $Pools,
    "--start-offset", $StartOffset,
    "--limit", $Limit,
    "--max-shards", $MaxShards
)

if ($Force) {
    $argsList += "--force"
}

& $Python @argsList

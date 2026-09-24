param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [string]$CdmDir = (Join-Path $DataRoot "sources\UniMERNet_official\cdm"),
    [string]$Python = "python",
    [string]$PathPrepend = "",
    [string]$InputPath = (Join-Path $DataRoot "runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json"),
    [string]$OutputDir = (Join-Path $DataRoot "runs\cdm_official_unimer_full"),
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
$Python = (Get-Command $Python -CommandType Application -ErrorAction Stop).Source

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
    "--shard-size", $ShardSize,
    "--pools", $Pools,
    "--start-offset", $StartOffset,
    "--limit", $Limit,
    "--max-shards", $MaxShards
)

if ($PathPrepend) {
    $argsList += @("--path-prepend", $PathPrepend)
}

if ($Force) {
    $argsList += "--force"
}

& $Python @argsList

exit $LASTEXITCODE

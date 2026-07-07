param(
    [string]$RepoRoot = "E:\LaTexSnipper",
    [string]$DataRoot = "E:\MathCraftBenchData",
    [string]$CdmDir = "E:\MathCraftBenchData\sources\UniMERNet_official\cdm",
    [string]$Python = "D:\Python312\python.exe",
    [string]$InputPath = "E:\MathCraftBenchData\runs\mathwriting_test_gpu\cdm_input\mathwriting_test_full_cdm.json",
    [string]$OutputDir = "E:\MathCraftBenchData\runs\cdm_official_mathwriting_test",
    [int]$ShardSize = 100,
    [int]$Pools = 8,
    [int]$StartOffset = 0,
    [int]$Limit = 0,
    [int]$MaxShards = 0,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$runner = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\reports\run_official_cdm.py"
$pathPrepend = "E:\MathCraftBenchData\tools\unix_shims;E:\MathCraftBenchData\tools\Ghostscript\gs10.07.1\bin;C:\Program Files\ImageMagick-7.1.2-Q16"

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

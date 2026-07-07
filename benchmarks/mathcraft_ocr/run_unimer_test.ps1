param(
    [string]$RepoRoot = "E:\LaTexSnipper",
    [string]$DataRoot = "E:\MathCraftBenchData",
    [ValidateSet("gpu", "cpu", "auto")]
    [string]$Provider = "gpu",
    [int]$ShardSize = 250,
    [int]$StartOffset = 0,
    [int]$Limit = 0,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($ShardSize -le 0) {
    throw "ShardSize must be positive."
}
if ($StartOffset -lt 0) {
    throw "StartOffset must be non-negative."
}
if ($Limit -lt 0) {
    throw "Limit must be non-negative."
}

$python = Join-Path $RepoRoot "tools\deps\python311\python.exe"
$manifestScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\datasets\create_unimer_manifest.py"
$runnerScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\runners\run_mathcraft.py"
$combineScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\reports\combine_jsonl.py"

foreach ($path in @($python, $manifestScript, $runnerScript, $combineScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

$rawDir = Join-Path $DataRoot "raw\unimer"
$manifestDir = Join-Path $DataRoot "manifests"
$runDir = Join-Path $DataRoot "runs\unimer_test_$Provider"
$zipPath = Join-Path $rawDir "UniMER-Test.zip"
$testRoot = Join-Path $rawDir "UniMER-Test"
$manifestPath = Join-Path $manifestDir "unimer_test_full.jsonl"
$combinedPath = Join-Path $runDir "unimer_test_${Provider}_full.jsonl"

New-Item -ItemType Directory -Force -Path $rawDir, $manifestDir, $runDir | Out-Null

if (-not (Test-Path -LiteralPath $zipPath)) {
    Write-Host "[download] UniMER-Test.zip -> $rawDir"
    $downloadCode = @"
from huggingface_hub import hf_hub_download
from pathlib import Path
out = Path(r"$rawDir")
out.mkdir(parents=True, exist_ok=True)
path = hf_hub_download(
    repo_id="wanderkid/UniMER_Dataset",
    repo_type="dataset",
    filename="UniMER-Test.zip",
    local_dir=str(out),
)
print(path)
"@
    $downloadCode | & $python -
}

if (-not (Test-Path -LiteralPath $testRoot)) {
    Write-Host "[extract] $zipPath -> $rawDir"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $rawDir -Force
}

if ((-not (Test-Path -LiteralPath $manifestPath)) -or $Force) {
    Write-Host "[manifest] $manifestPath"
    & $python $manifestScript --root $testRoot --output $manifestPath
}

$totalRows = (Get-Content -LiteralPath $manifestPath | Measure-Object -Line).Lines
if ($totalRows -le 0) {
    throw "Manifest is empty: $manifestPath"
}

$runLimit = if ($Limit -gt 0) { [Math]::Min($Limit, $totalRows - $StartOffset) } else { $totalRows - $StartOffset }
if ($runLimit -le 0) {
    throw "Nothing to run. totalRows=$totalRows StartOffset=$StartOffset Limit=$Limit"
}

$endExclusive = $StartOffset + $runLimit
$expectedShardCount = [int][Math]::Ceiling($runLimit / [double]$ShardSize)
Write-Host "[plan] provider=$Provider total=$totalRows range=[$StartOffset,$endExclusive) shardSize=$ShardSize shards=$expectedShardCount"

$completedRows = 0
$completedShards = 0
for ($offset = $StartOffset; $offset -lt $endExclusive; $offset += $ShardSize) {
    $count = [Math]::Min($ShardSize, $endExclusive - $offset)
    $last = $offset + $count - 1
    $shardPath = Join-Path $runDir ("unimer_test_{0}_shard_{1:D5}_{2:D5}.jsonl" -f $Provider, $offset, $last)
    if (Test-Path -LiteralPath $shardPath) {
        $existingLines = (Get-Content -LiteralPath $shardPath | Measure-Object -Line).Lines
        if ($existingLines -eq $count) {
            $completedRows += $count
            $completedShards += 1
        }
    }
}
$initialPercent = [Math]::Round(($completedRows / [double]$runLimit) * 100.0, 2)
Write-Host "[resume] completedRows=$completedRows/$runLimit completedShards=$completedShards/$expectedShardCount progress=$initialPercent%"

$startedAt = Get-Date
$processedThisRun = 0
$shardIndex = 0
$expectedShardPaths = @()
for ($offset = $StartOffset; $offset -lt $endExclusive; $offset += $ShardSize) {
    $shardIndex += 1
    $count = [Math]::Min($ShardSize, $endExclusive - $offset)
    $last = $offset + $count - 1
    $shardPath = Join-Path $runDir ("unimer_test_{0}_shard_{1:D5}_{2:D5}.jsonl" -f $Provider, $offset, $last)
    $expectedShardPaths += $shardPath
    if ((Test-Path -LiteralPath $shardPath) -and (-not $Force)) {
        $existingLines = (Get-Content -LiteralPath $shardPath | Measure-Object -Line).Lines
        if ($existingLines -eq $count) {
            $doneRows = [Math]::Min($runLimit, $offset - $StartOffset + $count)
            $percent = [Math]::Round(($doneRows / [double]$runLimit) * 100.0, 2)
            Write-Progress -Activity "MathCraft UniMER-Test GPU" -Status "Skipping completed shard $shardIndex/$expectedShardCount" -PercentComplete $percent
            Write-Host "[skip] shard=$shardIndex/$expectedShardCount rows=$existingLines progress=$percent% path=$shardPath"
            continue
        }
        Write-Host "[rerun] $shardPath has $existingLines rows, expected $count"
    }

    $beforeRows = [Math]::Min($runLimit, $offset - $StartOffset)
    $beforePercent = [Math]::Round(($beforeRows / [double]$runLimit) * 100.0, 2)
    Write-Progress -Activity "MathCraft UniMER-Test GPU" -Status "Running shard $shardIndex/$expectedShardCount, offset $offset, rows $count" -PercentComplete $beforePercent
    Write-Host "[run] shard=$shardIndex/$expectedShardCount offset=$offset limit=$count progress=$beforePercent% -> $shardPath"
    $shardStartedAt = Get-Date
    & $python $runnerScript `
        --manifest $manifestPath `
        --output $shardPath `
        --provider $Provider `
        --offset $offset `
        --limit $count
    $shardFinishedAt = Get-Date
    $elapsed = $shardFinishedAt - $shardStartedAt
    $processedThisRun += $count
    $doneRows = [Math]::Min($runLimit, $offset - $StartOffset + $count)
    $percent = [Math]::Round(($doneRows / [double]$runLimit) * 100.0, 2)
    $overallElapsed = $shardFinishedAt - $startedAt
    $rowsPerSecond = if ($processedThisRun -gt 0 -and $overallElapsed.TotalSeconds -gt 0) {
        $processedThisRun / $overallElapsed.TotalSeconds
    } else {
        0.0
    }
    $remainingRows = [Math]::Max(0, $runLimit - $doneRows)
    $eta = if ($rowsPerSecond -gt 0) {
        [TimeSpan]::FromSeconds($remainingRows / $rowsPerSecond)
    } else {
        [TimeSpan]::Zero
    }
    $elapsedText = $elapsed.ToString("hh\:mm\:ss")
    $etaText = $eta.ToString("hh\:mm\:ss")
    Write-Host ("[done-shard] shard={0}/{1} rows={2} elapsed={3} progress={4}% speed={5:N2} rows/s eta={6}" -f $shardIndex, $expectedShardCount, $count, $elapsedText, $percent, $rowsPerSecond, $etaText)
}
Write-Progress -Activity "MathCraft UniMER-Test GPU" -Completed

Write-Host "[combine] $combinedPath"
if (Test-Path -LiteralPath $combinedPath) {
    Remove-Item -LiteralPath $combinedPath -Force
}
$shardListPath = Join-Path $runDir "unimer_test_${Provider}_expected_shards.txt"
Set-Content -LiteralPath $shardListPath -Value $expectedShardPaths -Encoding UTF8
foreach ($path in $expectedShardPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Expected shard is missing: $path"
    }
}
& $python $combineScript --list-file $shardListPath --output $combinedPath

$combinedRows = (Get-Content -LiteralPath $combinedPath | Measure-Object -Line).Lines
Write-Host "[done] rows=$combinedRows combined=$combinedPath"

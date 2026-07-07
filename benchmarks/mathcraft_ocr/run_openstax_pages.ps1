param(
    [string]$RepoRoot = "E:\LaTexSnipper",
    [string]$DataRoot = "E:\MathCraftBenchData",
    [ValidateSet("gpu", "cpu", "auto")]
    [string]$Provider = "gpu",
    [string]$Pages = "calculus_v1:40-89+120-169,college_algebra:60-109+180-229",
    [int]$Dpi = 144,
    [int]$ShardSize = 1,
    [int]$StartOffset = 0,
    [int]$Limit = 0,
    [string]$RunId = "",
    [switch]$ForceManifest,
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
if ($Dpi -le 0) {
    throw "Dpi must be positive."
}

$python = Join-Path $RepoRoot "tools\deps\python311\python.exe"
$manifestScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\datasets\create_openstax_manifest.py"
$runnerScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\runners\run_mathcraft.py"
$combineScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\reports\combine_jsonl.py"
$analyzeScript = Join-Path $RepoRoot "benchmarks\mathcraft_ocr\reports\analyze_openstax_pages.py"

foreach ($path in @($python, $manifestScript, $runnerScript, $combineScript, $analyzeScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

$manifestDir = Join-Path $DataRoot "manifests"
$safeRunId = if ($RunId.Trim()) { $RunId.Trim() } else { "openstax_mixed_${Provider}_${Dpi}dpi" }
$manifestPath = Join-Path $manifestDir "$safeRunId.jsonl"
$runDir = Join-Path $DataRoot "runs\$safeRunId"
$combinedPath = Join-Path $runDir "$safeRunId`_full.jsonl"
$shardListPath = Join-Path $runDir "$safeRunId`_expected_shards.txt"

New-Item -ItemType Directory -Force -Path $manifestDir, $runDir | Out-Null

if ((-not (Test-Path -LiteralPath $manifestPath)) -or $ForceManifest) {
    Write-Host "[manifest] $manifestPath"
    & $python $manifestScript `
        --data-root $DataRoot `
        --output $manifestPath `
        --pages $Pages `
        --dpi $Dpi
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
Write-Host "[plan] provider=$Provider total=$totalRows range=[$StartOffset,$endExclusive) shardSize=$ShardSize shards=$expectedShardCount dpi=$Dpi"
Write-Host "[pages] $Pages"

$completedRows = 0
$completedShards = 0
for ($offset = $StartOffset; $offset -lt $endExclusive; $offset += $ShardSize) {
    $count = [Math]::Min($ShardSize, $endExclusive - $offset)
    $last = $offset + $count - 1
    $shardPath = Join-Path $runDir ("{0}_shard_{1:D5}_{2:D5}.jsonl" -f $safeRunId, $offset, $last)
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
    $shardPath = Join-Path $runDir ("{0}_shard_{1:D5}_{2:D5}.jsonl" -f $safeRunId, $offset, $last)
    $expectedShardPaths += $shardPath

    if ((Test-Path -LiteralPath $shardPath) -and (-not $Force)) {
        $existingLines = (Get-Content -LiteralPath $shardPath | Measure-Object -Line).Lines
        if ($existingLines -eq $count) {
            $doneRows = [Math]::Min($runLimit, $offset - $StartOffset + $count)
            $percent = [Math]::Round(($doneRows / [double]$runLimit) * 100.0, 2)
            Write-Progress -Activity "MathCraft OpenStax Mixed OCR" -Status "Skipping completed shard $shardIndex/$expectedShardCount" -PercentComplete $percent
            Write-Host "[skip] shard=$shardIndex/$expectedShardCount rows=$existingLines progress=$percent% path=$shardPath"
            continue
        }
        Write-Host "[rerun] $shardPath has $existingLines rows, expected $count"
    }

    $beforeRows = [Math]::Min($runLimit, $offset - $StartOffset)
    $beforePercent = [Math]::Round(($beforeRows / [double]$runLimit) * 100.0, 2)
    Write-Progress -Activity "MathCraft OpenStax Mixed OCR" -Status "Running shard $shardIndex/$expectedShardCount, offset $offset, rows $count" -PercentComplete $beforePercent
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
    Write-Host ("[done-shard] shard={0}/{1} rows={2} elapsed={3} progress={4}% speed={5:N2} pages/s eta={6}" -f $shardIndex, $expectedShardCount, $count, $elapsedText, $percent, $rowsPerSecond, $etaText)
}
Write-Progress -Activity "MathCraft OpenStax Mixed OCR" -Completed

Write-Host "[combine] $combinedPath"
if (Test-Path -LiteralPath $combinedPath) {
    Remove-Item -LiteralPath $combinedPath -Force
}
Set-Content -LiteralPath $shardListPath -Value $expectedShardPaths -Encoding UTF8
foreach ($path in $expectedShardPaths) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Expected shard is missing: $path"
    }
}
& $python $combineScript --list-file $shardListPath --output $combinedPath

Write-Host "[analyze] $runDir"
& $python $analyzeScript `
    --results $combinedPath `
    --manifest $manifestPath `
    --output-dir $runDir

$combinedRows = (Get-Content -LiteralPath $combinedPath | Measure-Object -Line).Lines
Write-Host "[done] rows=$combinedRows combined=$combinedPath report=$(Join-Path $runDir 'openstax_report.md')"

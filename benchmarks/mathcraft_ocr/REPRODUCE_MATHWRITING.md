# Reproduce MathWriting Test

MathWriting is used as an independent handwritten formula benchmark. The
protocol is fixed to the public test split, human samples only, offline raster
images, and the dataset-provided normalized LaTeX labels as ground truth.

Large parquet files, exported images, full JSONL results, render outputs, and
official CDM outputs stay under:

```text
E:\MathCraftBenchData
```

## Inputs

Expected local parquet:

```text
E:\MathCraftBenchData\raw\mathwriting\test-00000-of-00001-694f317d8b634199.parquet
```

The manifest generator validates:

```text
split_tag = test
data_type = human
```

Generated fixed-test assets:

```text
E:\MathCraftBenchData\manifests\mathwriting_test.jsonl
E:\MathCraftBenchData\raw\mathwriting\test_images
```

## Run MathCraft GPU

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_mathwriting_test.ps1
```

Defaults:

```text
Provider:   gpu
ShardSize:  100
Rows:       7,644
Resume:     completed shards are skipped
Progress:   Write-Progress plus per-shard ETA
```

Formal output after a full run:

```text
E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_full.jsonl
E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_subset_metrics.csv
E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_report.md
E:\MathCraftBenchData\runs\mathwriting_test_gpu\cdm_input\mathwriting_test_full_cdm.json
```

## Render Success

```powershell
E:\LaTexSnipper\tools\deps\python311\python.exe `
  E:\LaTexSnipper\benchmarks\mathcraft_ocr\reports\render_formula_success.py `
  --results E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\mathwriting_test.jsonl `
  --output-dir E:\MathCraftBenchData\runs\mathwriting_test_gpu\render_success
```

## Official CDM

The MathCraft run creates official CDM input automatically. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_mathwriting_official_cdm.ps1
```

For a bounded CDM validation:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_mathwriting_official_cdm.ps1 `
  -Limit 100 `
  -ShardSize 20 `
  -Pools 8
```

## Baseline Alignment

Only compare against MathWriting paper/public baselines when all of these hold:

- Same fixed test split.
- Same normalized LaTeX labels.
- Same offline raster-image setting.
- No online ink-stroke advantage unless a separate stroke-based protocol is clearly labeled.

The intended paper wording is that MathCraft reaches the top tier under this
aligned handwritten protocol, not that it is globally strongest across all HME
settings.

# Reproducing UniMER-Test Results

This document records the MathCraft OCR UniMER-Test experiment used for the
paper tables. Large datasets and run outputs are kept outside the repository.

## Environment

- Windows 11
- TeX Live 2024 for render checks
- Python runtime: `tools\deps\python311\python.exe`
- ONNX provider requested: `gpu`
- Observed active provider: `CUDAExecutionProvider`

Install benchmark-only metric dependencies into the development runtime:

```powershell
.\tools\deps\python311\python.exe -m pip install rapidfuzz evaluate
```

## Data Root

Use a local data root:

```text
E:\MathCraftBenchData
```

The scripts download `UniMER-Test.zip` from the public Hugging Face dataset
`wanderkid/UniMER_Dataset` and write manifests/results below this data root.

## Run MathCraft OCR

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_unimer_test.ps1
```

The runner is sharded and resumable. Completed shard files are skipped; partial
shards are rerun.

Main output:

```text
E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl
```

## Text Metrics

```powershell
.\tools\deps\python311\python.exe benchmarks\mathcraft_ocr\reports\analyze_unimer_results.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\unimer_test_gpu
```

This generates BLEU-4, normalized edit distance, exact-match, similarity, and
latency tables.

## Render Consistency Fallback

This is a local render-consistency fallback for paper analysis, not CDM.

```powershell
.\tools\deps\python311\python.exe benchmarks\mathcraft_ocr\reports\render_unimer_samples.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated `
  --per-subset 20 `
  --min-similarity 0.95 `
  --keep-images
```

Create an HTML gallery:

```powershell
.\tools\deps\python311\python.exe benchmarks\mathcraft_ocr\visualization\make_render_gallery.py `
  --rows E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated\unimer_render_consistency_rows.csv `
  --image-dir E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated\rendered_pairs `
  --output E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated\render_gallery.html `
  --limit 40
```

## Official CDM Input

CDM expects a batch JSON file with `img_id`, `gt`, and `pred` fields. Convert the
full MathCraft UniMER-Test run to that schema:

```powershell
.\tools\deps\python311\python.exe benchmarks\mathcraft_ocr\reports\prepare_cdm_input.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json `
  --subset all
```

Subset conversion is also supported:

```powershell
.\tools\deps\python311\python.exe benchmarks\mathcraft_ocr\reports\prepare_cdm_input.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_cpe_cdm.json `
  --subset cpe
```

The generated JSON is intended for the official UniMERNet CDM implementation.
The official CDM runtime has external rendering and character-detection
dependencies; do not label local fallback metrics as CDM.

## Official CDM Runtime

Run the official UniMERNet CDM evaluator through the resumable benchmark entry:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_official_cdm.ps1
```

Defaults:

```text
Input:     E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json
Output:    E:\MathCraftBenchData\runs\cdm_official_unimer_full
CDM code:  E:\MathCraftBenchData\sources\UniMERNet_official\cdm
Python:    D:\Python312\python.exe
Pools:     8
ShardSize: 100
```

`tools\deps\python311` is the MathCraft development/runtime environment. The
official CDM clone is evaluated with the system Python above because the
isolated `tools\deps` runtime does not expose the official CDM source tree on
`sys.path`.

The runner is resumable. A shard is skipped when it has a local completion
marker from a successful official CDM process, or when legacy metrics contain
one detail row for every CDM input row in that shard. It writes:

```text
E:\MathCraftBenchData\runs\cdm_official_unimer_full\metrics_res.json
E:\MathCraftBenchData\runs\cdm_official_unimer_full\cdm_shard_summary.csv
```

The runner also writes `.mathcraft_cdm_complete.json` for each shard after the
official process exits successfully. This separates true runtime failure from
official CDM skips caused by GT formulas that do not render into character boxes;
the shard CSV records `expected_rows`, `evaluated_rows`, and `skipped_rows`.

For a bounded check:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_official_cdm.ps1 `
  -InputPath E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_all_20_cdm.json `
  -OutputDir E:\MathCraftBenchData\runs\cdm_official_unimer_20_runner `
  -ShardSize 10 `
  -Limit 20
```

Validated 20-row official CDM check:

```text
mean_score: 0.985
exp_rate:   0.700
details:    20 / 20
```

Use a bounded validation run before raising `-Pools` beyond 8 on Windows. The
local official CDM clone suppresses pdflatex output through
`subprocess.DEVNULL` instead of a shared shell redirection path to avoid
concurrent temp-file locks.

Validated official CDM pool checks after the Windows compatibility and progress
fixes:

```text
20 rows, Pools=4:  mean_score 0.985, exp_rate 0.700, details 20 / 20
100 rows, Pools=4: mean_score 0.990, exp_rate 0.790, details 100 / 100
100 rows, Pools=8: mean_score 0.990, exp_rate 0.790, details 100 / 100
100 rows, Pools=12: mean_score 0.990, exp_rate 0.790, details 100 / 100, slower than Pools=8
```

The local official CDM clone also suppresses noisy PIL transparency warnings and
prints `extract bbox` progress during the rendering/bbox stage.

Full official CDM run:

```text
Run:        E:\MathCraftBenchData\runs\cdm_official_unimer_full
Mean CDM:   0.929
ExpRate:    0.648
Expected:   23757
Evaluated:  23701
Skipped:    56
Shards:     238 / 238 complete
```

Generate compact source-controlled CDM tables:

```powershell
D:\Python312\python.exe E:\LaTexSnipper\benchmarks\mathcraft_ocr\reports\analyze_cdm_results.py `
  --metrics E:\MathCraftBenchData\runs\cdm_official_unimer_full\metrics_res.json `
  --input E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --shards E:\MathCraftBenchData\runs\cdm_official_unimer_full\cdm_shard_summary.csv `
  --output-dir E:\LaTexSnipper\benchmarks\mathcraft_ocr\results\unimer_test_gpu
```

## Source-Controlled Result Evidence

Small result tables are copied into:

```text
benchmarks/mathcraft_ocr/results/unimer_test_gpu
```

Do not commit `E:\MathCraftBenchData`, full JSONL outputs, downloaded datasets,
or rendered PNG pairs into the repository.

## Related Page-Level Data

OpenStax page-level scripts are documented in `README.md`. These runs complement
UniMER-Test with public mixed-page evidence and are not part of the UniMER-Test
accuracy table.

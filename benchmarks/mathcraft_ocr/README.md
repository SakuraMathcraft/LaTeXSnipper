# MathCraft OCR Benchmark

This benchmark suite runs MathCraft OCR only. It does not install, import, or execute third-party OCR models.

## Scope

- Formula-only OCR
- Mixed text/formula OCR
- PDF/page image recognition
- GPU formula benchmark on UniMER-Test
- GPU handwritten formula benchmark on MathWriting test
- Latency and structured output capture
- Render-success and render-consistency fallback analysis

## Out of scope

- No pix2tex, UniMERNet, Pix2Text, MinerU, Nougat, Texify, or VLM runtime setup
- No third-party model weight download
- No SOTA ranking table produced from mixed protocols

Third-party systems may appear only in related work or public-result context, with clear protocol differences.

## Data

Keep external datasets and large run artifacts outside the repository:

```text
E:\MathCraftBenchData
```

Manifest files live under:

```text
benchmarks/mathcraft_ocr/datasets/manifests
```

Each manifest is JSONL and follows `schemas/manifest.schema.json`.

## MathWriting Test

MathWriting provides an independent handwritten formula benchmark. The local
protocol is fixed to the public test split, human samples only, offline raster
images, and dataset-provided normalized LaTeX labels as ground truth.

Run MathCraft GPU:

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_mathwriting_test.ps1
```

The runner creates:

```text
E:\MathCraftBenchData\manifests\mathwriting_test.jsonl
E:\MathCraftBenchData\raw\mathwriting\test_images
E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_full.jsonl
E:\MathCraftBenchData\runs\mathwriting_test_gpu\cdm_input\mathwriting_test_full_cdm.json
```

It also writes exact, BLEU-4, normalized edit distance, and latency summaries
after the full JSONL is combined. Render success is computed separately:

```powershell
python benchmarks\mathcraft_ocr\reports\render_formula_success.py `
  --results E:\MathCraftBenchData\runs\mathwriting_test_gpu\mathwriting_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\mathwriting_test.jsonl `
  --output-dir E:\MathCraftBenchData\runs\mathwriting_test_gpu\render_success
```

Run official CDM on MathWriting predictions:

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_mathwriting_official_cdm.ps1
```

Baseline comparisons must be restricted to the same split, normalized label, and
offline rasterization protocol.

## UniMER-Test

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_unimer_test.ps1
```

The script downloads UniMER-Test from Hugging Face when needed, creates the manifest,
runs MathCraft OCR with the GPU provider, resumes completed shards, and combines shard
outputs without re-encoding JSONL content.

Analyze text metrics:

```powershell
python benchmarks\mathcraft_ocr\reports\analyze_unimer_results.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\unimer_test_gpu
```

Analyze render-consistency fallback samples:

```powershell
python benchmarks\mathcraft_ocr\reports\render_unimer_samples.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated `
  --per-subset 20 `
  --min-similarity 0.95 `
  --keep-images
```

Prepare official CDM batch JSON input:

```powershell
python benchmarks\mathcraft_ocr\reports\prepare_cdm_input.py `
  --results E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl `
  --manifest E:\MathCraftBenchData\manifests\unimer_test_full.jsonl `
  --output E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_full_cdm.json `
  --subset all
```

The generated JSON follows the official CDM batch fields `img_id`, `gt`, and
`pred`. The local render-consistency fallback is not reported as CDM.

Run the official UniMERNet CDM runtime with resumable shards:

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_official_cdm.ps1
```

The CDM runner uses the official `evaluation.py` from the local UniMERNet clone
under `E:\MathCraftBenchData\sources\UniMERNet_official\cdm`. It intentionally
uses the system Python configured for that official runtime; MathCraft OCR
inference remains on `tools\deps\python311\python.exe`. The default official
CDM pool count is 8 on the local Windows evaluation host.

For a quick validation run:

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_official_cdm.ps1 `
  -InputPath E:\MathCraftBenchData\runs\unimer_test_gpu\cdm_input\unimer_test_all_20_cdm.json `
  -OutputDir E:\MathCraftBenchData\runs\cdm_official_unimer_20_runner `
  -ShardSize 10 `
  -Limit 20 `
  -Pools 8
```

On Windows, validate any higher pool count on a bounded run first. The local
official CDM clone suppresses pdflatex output through `subprocess.DEVNULL`
instead of a shared shell redirection path to avoid concurrent temp-file locks.
It also filters noisy PIL transparency warnings and prints `extract bbox`
progress during the official rendering/bbox stage.
Each successful shard writes a local completion marker, and the shard summary
records `expected_rows`, `evaluated_rows`, and `skipped_rows` so official CDM
render skips are not confused with interrupted runs.

The full official CDM UniMER-Test run is complete:

```text
Run:        E:\MathCraftBenchData\runs\cdm_official_unimer_full
Mean CDM:   0.929
ExpRate:    0.648
Expected:   23757
Evaluated:  23701
Skipped:    56
```

Compact official CDM tables suitable for source control are stored in:

```text
benchmarks/mathcraft_ocr/results/unimer_test_gpu
```

Large JSONL files, downloaded data, and rendered PNG pairs remain under
`E:\MathCraftBenchData`.

## OpenStax Page Images

OpenStax pages provide a public page-level stress set for mixed mathematical
document recognition. They are used for qualitative, structural, and runtime analysis, not
for exact-match formula accuracy because no page-level ground truth is included.

Run the default systematic mixed-page benchmark:

```powershell
powershell -ExecutionPolicy Bypass -File benchmarks\mathcraft_ocr\run_openstax_pages.ps1
```

The runner creates a manifest, renders selected OpenStax PDF pages, runs mixed
OCR with resumable page shards, combines completed shards, and writes page-level
summary tables. The default page set contains 200 pages at 144 DPI:

```text
calculus_v1:40-89+120-169,college_algebra:60-109+180-229
```

Use `-Pages`, `-Dpi`, `-ShardSize`, `-StartOffset`, and `-Limit` to create
larger or smaller public mixed-document runs.

Formal result tables suitable for source control are stored in:

```text
benchmarks/mathcraft_ocr/results/openstax_mixed_gpu_144dpi
```

Generate OpenStax block-overlay figure assets from the formal run:

```powershell
python benchmarks\mathcraft_ocr\visualization\make_openstax_block_gallery.py `
  --results E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_mixed_gpu_144dpi_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\figures\block_gallery `
  --limit 6
```

Generated OpenStax page images and overlays remain under `E:\MathCraftBenchData`
because they are derived from licensed OpenStax PDF content.

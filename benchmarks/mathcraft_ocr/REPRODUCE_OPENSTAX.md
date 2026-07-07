# Reproducing OpenStax Mixed-Page Results

OpenStax pages are used as a public mixed mathematical document benchmark for
page-level OCR behavior, layout reconstruction, runtime, and qualitative
evidence. They do not provide formula-level ground truth labels.

## Default Systematic Run

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_openstax_pages.ps1
```

Default settings:

- Provider: `gpu`
- DPI: `144`
- Shard size: `1` page
- Pages: `calculus_v1:40-89+120-169,college_algebra:60-109+180-229`
- Run id: `openstax_mixed_gpu_144dpi`

The script is resumable. Completed shard files are skipped; partial shards are
rerun. This makes it safe to stop the terminal and continue later with the same
command.

## Outputs

```text
E:\MathCraftBenchData\manifests\openstax_mixed_gpu_144dpi.jsonl
E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_mixed_gpu_144dpi_full.jsonl
E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_report.md
E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_summary.csv
E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_page_metrics.csv
```

Small source-control evidence tables are mirrored to:

```text
E:\LaTexSnipper\benchmarks\mathcraft_ocr\results\openstax_mixed_gpu_144dpi
```

Current formal run summary:

- Pages: 200
- Failures: 0
- Empty outputs: 0
- Median latency: 6650.7 ms
- Average blocks per page: 70.4
- Average formula blocks per page: 24.2

## Block Visualization

Generate paper-oriented block overlay panels from the formal run:

```powershell
E:\LaTexSnipper\tools\deps\python311\python.exe `
  E:\LaTexSnipper\benchmarks\mathcraft_ocr\visualization\make_openstax_block_gallery.py `
  --results E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_mixed_gpu_144dpi_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\figures\block_gallery `
  --limit 6
```

The generated PNG panels and HTML gallery remain in `E:\MathCraftBenchData`
because the page images are rendered from OpenStax PDFs.

## Smaller Trial

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_openstax_pages.ps1 `
  -Pages "calculus_v1:120-124,college_algebra:80-84" `
  -RunId "openstax_trial_gpu_144dpi"
```

## Larger Run

Use explicit page ranges and keep `-ShardSize 1` for best resume behavior:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_openstax_pages.ps1 `
  -Pages "calculus_v1:20-219,college_algebra:20-219" `
  -RunId "openstax_400pages_gpu_144dpi"
```

Large JSONL outputs, rendered page images, and downloaded PDFs remain under
`E:\MathCraftBenchData` and should not be committed.

# MathCraft OCR Literature and Public Data Inventory

Reviewed: 2026-07-06

This inventory records the paper evidence that is already reproducible, the
public datasets still worth adding, and the claims each source can support. The
benchmark repository should contain scripts, schemas, reports, and compact
tables. Downloaded PDFs, rendered pages, large JSONL files, and generated figure
assets stay under `E:\MathCraftBenchData`.

## Current Evidence Status

| Evidence line | Status | Local artifact | Paper use |
| --- | --- | --- | --- |
| UniMER-Test formula OCR | Formal run complete | `E:\MathCraftBenchData\runs\unimer_test_gpu\unimer_test_gpu_full.jsonl` | Main formula-recognition benchmark |
| UniMER-Test render consistency | Formal auxiliary complete | `E:\MathCraftBenchData\runs\unimer_test_gpu\render_exact_underestimated` | Show exact-match underestimation cases |
| OpenStax mixed pages | Formal run complete | `E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi` | Main mixed-document evidence |
| OpenStax block visualizations | Regenerable figure assets complete | `E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\figures\block_gallery` | Qualitative structure-recovery figures |
| MathWriting | Formal run complete | `E:\MathCraftBenchData\runs\mathwriting_test_gpu` | Independent handwritten benchmark and exact-match stress evidence |
| CROHME | Candidate only | Not downloaded as formal benchmark | Standard HME comparison if data access is cleared |
| CDM | Official full run complete | `E:\MathCraftBenchData\runs\cdm_official_unimer_full` | Full UniMER-Test render-aware evidence: mean CDM 0.929, ExpRate@CDM 0.648 |

## Formal Public Benchmarks

### UniMER-Test

Source: [UniMERNet paper](https://arxiv.org/abs/2404.15254),
[UniMER_Dataset](https://huggingface.co/datasets/wanderkid/UniMER_Dataset).

Local manifest:

```text
E:\MathCraftBenchData\manifests\unimer_test_full.jsonl
```

Scale:

| Subset | Count | Role |
| --- | ---: | --- |
| SPE | 6,762 | Simple printed expressions |
| CPE | 5,921 | Complex printed expressions |
| SCE | 4,742 | Screen-captured expressions |
| HWE | 6,332 | Handwritten expressions |
| Total | 23,757 | Full UniMER-Test |

Current MathCraft result:

```text
E:\LaTexSnipper\benchmarks\mathcraft_ocr\results\unimer_test_gpu
```

Use in paper:

- Report exact, BLEU-4, normalized edit distance, render success, and render
  consistency.
- Treat HWE as existing handwritten evidence, but do not claim a complete
  handwritten-formula study until an independent HME benchmark is added.
- Do not write a global SOTA claim from UniMER-Test alone. UniMERNet, CDM, and
  later image-to-markup papers use different metric emphasis and protocols.

### MathWriting Test

Primary reference: [MathWriting: A Dataset For Handwritten Mathematical
Expression Recognition](https://arxiv.org/abs/2404.10690).

Local protocol:

| Field | Value |
| --- | --- |
| Split | `test` |
| Data type | `human` |
| Samples | 7,644 |
| Input mode | Offline raster image |
| Ground truth | Dataset-provided normalized LaTeX |
| License | CC BY-NC-SA 4.0 |

Local manifest:

```text
E:\MathCraftBenchData\manifests\mathwriting_test.jsonl
```

Run entry:

```powershell
powershell -ExecutionPolicy Bypass -File E:\LaTexSnipper\benchmarks\mathcraft_ocr\run_mathwriting_test.ps1
```

Current MathCraft result:

| Metric | Value |
| --- | ---: |
| Samples | 7,644 |
| Provider | CUDAExecutionProvider |
| Failures / empty outputs | 0 / 0 |
| Compact exact | 11.75% |
| BLEU-4 | 0.5467 |
| Avg char NED | 0.3547 |
| Prediction render success | 98.63% |
| Official CDM mean | 0.750 |
| Official CDM ExpRate | 0.168 |
| Official CDM evaluated / skipped | 7,644 / 0 |

Use in paper:

- Report exact match, BLEU-4, normalized edit distance, render success, and
  optional official CDM.
- Compare only to public baselines that use the same test split, normalized
  labels, and offline rasterization setting.
- Do not use this run to claim handwritten SOTA. Use it as independent
  handwriting stress evidence and as another case where renderability/CDM gives
  more information than exact match alone.

Public baseline context from the MathWriting paper Table 6:

| Model | Test CER | Test EM | Test <= 1 dist | Protocol note |
| --- | ---: | ---: | ---: | --- |
| OCR API | 7.17 | 53 | 68 | Bitmap input; reported as partly trained on MathWriting |
| CTC Transformer | 5.49 | 60 | 72 | Online sequence model |
| PaLI | 5.95 | 64 | 73 | Large VLM baseline |
| PaLIGemma | 5.97 | 69 | 77 | 3B VLM baseline |

These numbers are public-result context. Under the aligned normalized-label
exact-match protocol, MathCraft's current offline raster result is below these
handwritten baselines; the paper should not blur this with the stronger UniMER
printed-formula evidence.

### OpenStax Mixed-Document Pages

Source pages are rendered from public OpenStax PDFs:

- [Calculus Volume 1](https://openstax.org/details/books/calculus-volume-1)
- [College Algebra](https://openstax.org/details/books/college-algebra)

Local formal run:

```text
E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi
```

Default protocol:

| Field | Value |
| --- | --- |
| Provider | GPU |
| DPI | 144 |
| Pages | `calculus_v1:40-89+120-169,college_algebra:60-109+180-229` |
| Page count | 200 |
| Failures | 0 |
| Empty outputs | 0 |
| Median latency | 6650.7 ms |
| Average blocks/page | 70.4 |
| Average formula blocks/page | 24.2 |

Source-control evidence:

```text
E:\LaTexSnipper\benchmarks\mathcraft_ocr\results\openstax_mixed_gpu_144dpi
```

Figure-generation entry:

```powershell
E:\LaTexSnipper\tools\deps\python311\python.exe `
  E:\LaTexSnipper\benchmarks\mathcraft_ocr\visualization\make_openstax_block_gallery.py `
  --results E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\openstax_mixed_gpu_144dpi_full.jsonl `
  --output-dir E:\MathCraftBenchData\runs\openstax_mixed_gpu_144dpi\figures\block_gallery `
  --limit 6
```

Use in paper:

- Present as a public mixed mathematical document benchmark for page-level OCR,
  layout reconstruction, formula/text separation, and runtime.
- Do not report exact formula accuracy because page-level formula ground truth is
  absent.
- Use block overlays as qualitative evidence, with OpenStax attribution.
- Keep generated page images out of the repository unless the target venue and
  license requirements are reviewed.

## Metrics and Claims

| Metric | Status | Use |
| --- | --- | --- |
| Exact match | Implemented | Formula-level strict text correctness |
| BLEU-4 | Implemented | Comparison with formula OCR literature; secondary |
| Character/token NED | Implemented | Robust text-similarity evidence |
| Render success | Implemented | Whether predicted LaTeX is usable |
| Render consistency fallback | Implemented | Evidence for exact-match underestimation |
| CDM | Official full run complete | Strong render-aware evidence that exact match underestimates visual correctness |
| Block count / formula block count | Implemented for OpenStax | Mixed-document structural density and runtime |
| Block F1 / reading-order accuracy | Not implemented | Requires page-level ground truth annotations |

Claim policy:

- Current evidence supports: "strong public formula-recognition results" and
  "systematic mixed-document runtime/structure evidence."
- Current evidence does not yet support: "global SOTA across mathematical OCR."
- A defensible SOTA claim needs at least one of:
  - Same-protocol third-party baseline runs.
  - Official CDM or a clearly separated render-aware metric matching recent
    formula-recognition literature.
  - An additional public handwritten benchmark beyond UniMER-HWE.

## Candidate Additions

### CDM / Render-Aware Formula Evaluation

Primary reference: [Image Over Text: Transforming Formula Recognition Evaluation
with Character Detection Matching](https://arxiv.org/abs/2409.03643).

Priority: high.

Action:

- Use the official UniMERNet CDM implementation from the local clone under
  `E:\MathCraftBenchData\sources\UniMERNet_official\cdm`.
- Convert MathCraft outputs into the official `img_id` / `gt` / `pred` batch
  format before running the official CDM scorer.
- Keep the current render-consistency fallback under a different name; it is
  supporting evidence, not CDM.
- Use CDM-style results to explain cases where text exact match penalizes
  visually equivalent math.

### CROHME

Reference: [CROHME 2019 Competition Report](https://www.cs.rit.edu/~rlaz/files/CROHME%2BTFD%E2%80%932019.pdf).

Priority: medium.

Action:

- Confirm official access and redistribution limits before downloading.
- Use only if the data access path is clean enough for reproducibility.
- Report ExpRate only if the target representation and normalization are
  protocol-compatible.

### HME100K

Priority: lower than MathWriting/CROHME.

Action:

- Use only after license and data-source stability are verified.
- Treat as supplementary handwritten evidence, not the core paper benchmark.

## Related Work Scope

| Work/System | Use in paper | Local runtime status |
| --- | --- | --- |
| UniMERNet | Dataset, formula OCR baseline context | Not run locally |
| CDM | Render-aware metric and evaluation critique | Official full UniMER-Test run complete |
| Nougat | Scientific document OCR related work | Not run locally |
| MinerU | Document parsing and layout/formula extraction related work | Not run locally |
| Pix2Text / Texify / pix2tex | Related work for mixed or formula OCR | Not run locally |

Third-party public numbers must be cited as public-result context unless the
models are rerun under the same local protocol.

## License and Publication Notes

| Source | Repository policy |
| --- | --- |
| UniMER-Test | Keep generated compact reports in repo; keep full data/results under `E:\MathCraftBenchData` |
| OpenStax | Keep scripts and compact metrics in repo; keep rendered page images and overlays local unless publication license review is complete |
| MathWriting | Keep scripts and compact metrics in repo; keep parquet, images, full results, and CDM render artifacts under `E:\MathCraftBenchData` |
| CROHME/HME100K | Do not add to formal benchmark until license/access is recorded |
| Project `test_pdf` assets | Internal regression only unless the original PDF source is public and attributable |

Required ledger fields for every new public source:

```json
{
  "source_id": "openstax_calculus_v1",
  "name": "Calculus Volume 1",
  "url": "https://openstax.org/details/books/calculus-volume-1",
  "license": "recorded source license",
  "allowed_use": ["non-commercial evaluation", "paper figures with attribution"],
  "forbidden_or_unclear": ["model training", "commercial redistribution"],
  "attribution": "OpenStax, Rice University",
  "checked_at": "2026-07-05"
}
```

## Next Work Queue

1. Use UniMER printed subsets and official CDM as the primary evidence for the
   printed-formula SOTA/top-tier claim.
2. Use MathWriting as independent handwritten stress evidence, not as a
   handwritten SOTA claim.
3. Align all public baseline numbers strictly by split, normalized label, and
   input setting before writing any rank statement.
4. Keep OpenStax as mixed-document evidence unless page-level ground truth is
   introduced.

# MathCraft OCR Design

## Goal

`MathCraft OCR` is the LaTeXSnipper-owned OCR runtime that replaces the fragile implicit model lifecycle in `mathcraft` with explicit, testable model management.

The v1 scope is deliberately narrow:

1. Use ONNX Runtime only for active inference.
2. Keep model cache, model checks, warmup, provider selection, and worker calls explicit.
3. Use one standard model cache root: `%APPDATA%\MathCraft\models` or `MATHCRAFT_HOME\models`.
4. Runtime reads only the standard MathCraft cache root and does not scan upstream OCR cache locations.
5. Do not keep unused PyTorch-only layout/table models in the active MathCraft v1 manifest.

## Current Status

Implemented:

1. `mathcraft_ocr` package skeleton:
   - `manifest`
   - `cache`
   - `downloader`
   - `providers`
   - `doctor`
   - `runtime`
   - `adapters`
   - `serialization`
   - `worker`
   - `cli`
2. Standard MathCraft model IDs and directories:
   - `mathcraft-formula-det`
   - `mathcraft-formula-rec`
   - `mathcraft-text-det`
   - `mathcraft-text-rec`
   - `mathcraft-text-det-lite-en`
   - `mathcraft-text-rec-lite-en`
3. Formula recognition path:
   - formula detection through ONNX
   - formula recognition through ONNX encoder/decoder sessions
4. Mixed recognition path:
   - formula detection
   - Chinese/English text detection and recognition
   - line grouping and inline formula merging
5. Process-level ONNX session caching.
6. JSONL resident worker for future UI/backend integration.
7. Lightweight tests for manifest, cache inspection, warmup, formula/mixed runtime flow, layout merging, and worker serialization.

Not in v1 active runtime:

1. PyTorch-only document layout weights.
2. Table extraction weights without a pure ONNX path.

If document layout or table extraction becomes a priority, use a separate plan instead of forcing these PyTorch-era weights back into MathCraft v1.

## Model Cache Layout

```text
%APPDATA%\MathCraft\models\
  mathcraft-formula-det\
    mathcraft-mfd.onnx
  mathcraft-formula-rec\
    config.json
    encoder_model.onnx
    decoder_model.onnx
    generation_config.json
    preprocessor_config.json
    special_tokens_map.json
    tokenizer.json
    tokenizer_config.json
  mathcraft-text-det\
    ch_PP-OCRv5_det_server_infer.onnx
  mathcraft-text-rec\
    ch_PP-OCRv5_server_rec_infer.onnx
    ppocr_keys_v1.txt
  mathcraft-text-det-lite-en\
    ppocr\
      en_PP-OCRv3_det_infer.onnx
  mathcraft-text-rec-lite-en\
    ppocr\
      en_PP-OCRv3_rec_infer.onnx
    en_dict.txt
```

Directory names are MathCraft-owned. Internal file names remain upstream names so that model provenance, source archives, and future checksum verification stay clear.

## Runtime Profiles

`formula` requires:

1. `mathcraft-formula-det`
2. `mathcraft-formula-rec`

`mixed` defaults to the high-accuracy Chinese/English profile:

1. `mathcraft-formula-det`
2. `mathcraft-formula-rec`
3. `mathcraft-text-det`
4. `mathcraft-text-rec`

English-lite fallback uses:

1. `mathcraft-text-det-lite-en`
2. `mathcraft-text-rec-lite-en`

## Provider Policy

MathCraft uses ONNX Runtime providers as the source of truth.

1. Prefer CUDA when explicitly requested and runtime creation succeeds.
2. Fall back to `CPUExecutionProvider` when CUDA provider is unavailable or broken.
3. Use ONNX Runtime provider availability to decide OCR mode.
4. Surface provider details through `doctor()` and worker responses.

## Integration Plan

Next step is application integration, but it should not replace the existing mathcraft path in one step.

Recommended sequence:

1. Add a MathCraft backend wrapper beside the current mathcraft wrapper.
2. Talk to `mathcraft_ocr.worker` through a resident JSONL subprocess, matching the current subprocess isolation strategy.
3. Add a hidden config or environment switch first, for example `LATEXSNIPPER_MATHCRAFT_OCR=1`.
4. Route formula and mixed recognition through MathCraft only when the switch is enabled.
5. Run real UI capture regression on formula, mixed English, mixed Chinese, and noisy screenshots.
6. Add a visible settings option only after the hidden path is stable.

The UI should expose:

1. active backend: mathcraft or MathCraft
2. active provider: CPU or CUDA provider
3. model cache completeness
4. a repair/download action if cache is incomplete

## Validation Commands

From the repository root:

```cmd
set PYTHONPATH=E:\LaTexSnipper
src\deps\python311\python.exe -m mathcraft_ocr.cli models check
src\deps\python311\python.exe -m mathcraft_ocr.cli doctor --provider cpu
src\deps\python311\python.exe -m mathcraft_ocr.cli warmup --profile formula --provider cpu
src\deps\python311\python.exe -m mathcraft_ocr.cli warmup --profile mixed --provider cpu
```

When running from a shell that does not honor `PYTHONPATH`, use:

```cmd
src\deps\python311\python.exe -c "import sys; sys.path.insert(0, r'E:\LaTexSnipper'); from mathcraft_ocr.cli import main; raise SystemExit(main(['doctor','--provider','cpu']))"
```

## Maintenance Rules

1. New model IDs must be MathCraft-owned names.
2. Upstream filenames can stay unchanged inside a MathCraft model directory.
3. Every model in the manifest must have explicit required files.
4. Do not infer cache completeness from directory existence.
5. Keep runtime cache resolution limited to the standard MathCraft model root.
6. Add tests whenever a new model profile, provider behavior, or worker action is introduced.

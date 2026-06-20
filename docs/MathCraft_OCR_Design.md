# MathCraft OCR Design

## Scope

`MathCraft OCR` is the LaTeXSnipper-owned OCR runtime and PyPI package for local ONNX-based formula, text, mixed document, and PDF page recognition.

The active package is `mathcraft-ocr` from `pyproject.toml`. It exposes the `mathcraft` and `mathcraft-ocr` console commands and is also used by the desktop application through the built-in model path.

Current design goals:

1. Use ONNX Runtime for active inference.
2. Keep model cache checks, downloads, provider selection, warmup, and worker calls explicit.
3. Use one standard model cache root per platform: `%APPDATA%\MathCraft\models` on Windows, `${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models` on Linux, and `~/Library/Application Support/LaTeXSnipper/MathCraft/models` on macOS. `MATHCRAFT_HOME` can explicitly override the root.
4. Keep the active manifest limited to models that are required by the current ONNX runtime.
5. Keep the standalone package independent from the desktop UI modules under `src/`.

## Active Package Modules

The current `mathcraft_ocr` package is organized as:

- `manifest`, `cache`, `downloader`: model manifest loading, cache inspection, repair, and download.
- `providers`, `hardware`, `errors`, `error_patterns`: ONNX provider policy and diagnostics.
- `adapters`: detector/recognizer adapters for formula and text models.
- `runtime`, `worker`, `api`, `cli`: runtime orchestration, resident worker, public API, and command-line entry points.
- `layout`, `formula_lines`, `serialization`, `results`, `profiles`: structured block output, line grouping, JSON conversion, and recognition profiles.
- `debug_blocks`, `doctor`: local diagnostics and regression/debug helpers.

## Active Model Set

The active manifest is `mathcraft_ocr/manifests/models.v1.json`. It contains four model IDs:

| Model ID | Purpose | Key files |
| --- | --- | --- |
| `mathcraft-formula-det` | Formula region detection | `mathcraft-mfd.onnx` |
| `mathcraft-formula-rec` | Formula-to-LaTeX recognition | `encoder_model.onnx`, `decoder_model.onnx`, tokenizer/config files |
| `mathcraft-text-det` | Multilingual text detection | `ppocrv5_mobile_det.onnx` |
| `mathcraft-text-rec` | Multilingual text recognition | `ppocrv5_mobile_rec.onnx`, `ppocrv5_keys.txt` |

The model archive sources currently point to MathCraft Models `v1.0.0`.

## Runtime Profiles

Profiles are defined in `mathcraft_ocr/profiles.py`:

| Profile | Required models | Output intent |
| --- | --- | --- |
| `formula` | `mathcraft-formula-det`, `mathcraft-formula-rec` | Formula screenshot to LaTeX |
| `text` | `mathcraft-text-det`, `mathcraft-text-rec` | Text OCR |
| `mixed` | all four active models | Mixed text/formula document output |

The desktop app uses MathCraft mixed mode for PDF recognition because PDF pages need both prose and formulas to be recovered into a usable document.

## Cache Layout

Typical Windows cache layout:

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
    ppocrv5_mobile_det.onnx
  mathcraft-text-rec\
    ppocrv5_mobile_rec.onnx
    ppocrv5_keys.txt
```

Directory names are MathCraft-owned. Internal filenames match the shipped archives so source provenance and checksum verification stay clear.

## Provider Policy

MathCraft uses ONNX Runtime providers as the source of truth:

1. Prefer CUDA only when requested and session creation succeeds.
2. Fall back to `CPUExecutionProvider` when CUDA is unavailable or broken.
3. Surface provider details through `doctor`, warmup results, worker responses, and desktop UI status.
4. Support `MATHCRAFT_FORCE_ORT_CPU=1` for users who need to disable GPU inference.

## Desktop Integration

The desktop application exposes MathCraft through the Settings window as the built-in model. Users can choose formula, mixed, or text recognition type for normal screenshots/images. Handwriting uses mixed recognition for local handwritten text and formula preservation. PDF recognition prompts for page count, output format, and DPI; built-in PDF recognition switches to mixed mode when needed.

Dependency installation and repair are owned by the dependency wizard. Model cache inspection and opening the MathCraft cache directory are available from the settings/runtime UI. External model providers remain separate from the built-in MathCraft path.

## Validation Commands

Run checks with the project dependency Python from the repository root:

```cmd
tools\deps\python311\python.exe -m mathcraft_ocr.cli models check
tools\deps\python311\python.exe -m mathcraft_ocr.cli doctor --provider cpu
tools\deps\python311\python.exe -m mathcraft_ocr.cli warmup --profile formula --provider cpu
tools\deps\python311\python.exe -m mathcraft_ocr.cli warmup --profile mixed --provider cpu
```

When a shell does not include the repository root on `PYTHONPATH`, run:

```cmd
tools\deps\python311\python.exe -c "import sys; sys.path.insert(0, r'E:\LaTexSnipper'); from mathcraft_ocr.cli import main; raise SystemExit(main(['doctor','--provider','cpu']))"
```

## Maintenance Rules

1. Every model in the manifest must have explicit required files and checksums.
2. Do not infer cache completeness from directory existence.
3. Do not add inactive model IDs or PyTorch-only weights to the active manifest.
4. Keep `mathcraft_ocr` independent from desktop UI modules under `src/`.
5. Add tests whenever a model profile, provider rule, serialization contract, or worker action changes.
6. Each MathCraft model update must be reflected in the PyPI package metadata and published as part of the release process.

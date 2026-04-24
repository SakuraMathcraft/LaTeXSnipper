# MathCraft OCR

MathCraft OCR is an ONNX-only OCR runtime for mathematical documents. It provides formula recognition, text recognition, mixed text/formula page OCR, explicit model-cache management, and structured block output for downstream Markdown or TeX document engines.

The package is developed for LaTeXSnipper but is usable as a standalone Python library.

## Features

- ONNX Runtime inference only; no active PyTorch OCR runtime.
- Formula OCR: image to LaTeX.
- Text OCR: multilingual PP-OCRv5 mobile detector/recognizer.
- Mixed OCR: formula detection, text masking, batched recognition, and layout merge.
- Manifest-driven model cache with SHA-256 file checks.
- Automatic repair for missing or incomplete model directories.
- CPU/GPU provider selection through ONNX Runtime.
- JSONL worker mode for GUI or service integration.

## Installation

CPU backend:

```bash
pip install "mathcraft-ocr[cpu]"
```

GPU backend:

```bash
pip install "mathcraft-ocr[gpu]"
```

Install only one backend extra in a clean environment. `onnxruntime` and `onnxruntime-gpu` should not be mixed in the same environment.

Python 3.10-3.12 use the LaTeXSnipper-tested ONNX Runtime 1.19 line. Python 3.13 uses newer ONNX Runtime wheels because 1.19.x is not published for Python 3.13.

## Quick Start

```python
from mathcraft_ocr import MathCraftRuntime

runtime = MathCraftRuntime(provider_preference="auto")
result = runtime.recognize_mixed("page.png")

print(result.text)
for block in result.blocks:
    print(block.role, block.kind, block.text[:80])
```

Formula-only recognition:

```python
from mathcraft_ocr import MathCraftRuntime

runtime = MathCraftRuntime(provider_preference="cpu")
formula = runtime.recognize_formula("formula.png")
print(formula.text)
```

## CLI

Check model cache:

```bash
mathcraft models check
```

Inspect runtime:

```bash
mathcraft doctor --provider auto
```

Warm up models:

```bash
mathcraft warmup --profile mixed --provider auto
```

Recognize an image:

```bash
mathcraft ocr page.png --profile mixed --provider auto --output result.md
mathcraft ocr formula.png --profile formula --json
```

Run JSONL worker mode:

```bash
mathcraft worker --provider auto
```

## Model Cache

MathCraft reads models from:

```text
%APPDATA%\MathCraft\models
```

or from a custom root:

```bash
set MATHCRAFT_HOME=D:\MathCraft\models
```

Model artifacts are downloaded from the MathCraft-Models release assets declared in `mathcraft_ocr/manifests/models.v1.json`.

## Runtime Profiles

| Profile | Models | Output |
| --- | --- | --- |
| `formula` | formula detector + formula recognizer | LaTeX string |
| `text` | text detector + text recognizer | OCR text and text blocks |
| `mixed` | formula detector + formula recognizer + text detector + text recognizer | Markdown-ready structured blocks |

## Provider Selection

`provider_preference` accepts:

- `auto`: prefer CUDA when available and valid, otherwise CPU.
- `cpu`: force CPU.
- `gpu`: request CUDA-capable ONNX Runtime.

The actual provider is available on results through the `provider` field.

## Development

Run tests from the repository root:

```bash
python test/test_mathcraft_ocr.py
python test/test_mathcraft_document_engine.py
```

Build package artifacts:

```bash
python -m pip wheel . --no-deps -w release_assets/mathcraft-ocr-package/dist
python -m build --outdir release_assets/mathcraft-ocr-package/dist
```

## License

MIT. See `LICENSE`.

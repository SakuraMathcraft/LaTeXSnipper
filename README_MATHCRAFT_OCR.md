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
- Resumable model downloads for interrupted first-run cache repair.
- CPU/GPU provider selection through ONNX Runtime.
- JSONL worker mode for GUI or service integration.

## Installation

These commands install the standalone library into your selected Python environment. LaTeXSnipper desktop installers already include their inference Python, dependencies and models.

CPU backend:

```powershell
pip install "mathcraft-ocr[cpu]"
```

GPU backend:

```powershell
pip install "mathcraft-ocr[gpu]"
```

CUDA 12 backend:

```powershell
pip install "mathcraft-ocr[gpu-cu12]"
```

Windows DirectML backend:

```powershell
pip install "mathcraft-ocr[directml]"
```

Intel OpenVINO backend on Windows or Linux:

```powershell
pip install "mathcraft-ocr[openvino]"
```

Install only one backend extra in a clean environment. The CPU, CUDA/TensorRT, DirectML, and OpenVINO ONNX Runtime distributions must not be mixed in the same environment. The standard `onnxruntime` macOS wheel includes CoreML EP support.

For a standalone GPU environment, select the backend extra matching your runtime requirements; the supported ONNX Runtime version ranges are declared in `pyproject.toml`. Provide the native libraries required by that backend. Desktop GPU editions deploy their own locked CUDA/cuDNN libraries, and their CPU/GPU edition is selected through the installer.

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

```powershell
mathcraft models check
```

Inspect runtime:

```powershell
mathcraft doctor --provider auto
```

Warm up models:

```powershell
mathcraft warmup --profile mixed --provider auto
```

Recognize an image:

```powershell
mathcraft ocr "./examples/page.png" --profile mixed --provider auto --output result.md
mathcraft ocr "./examples/page.png" --profile mixed --provider auto --output-dir "./outputs"
mathcraft ocr "./examples/formula.png" --profile formula --provider auto --json
```

Run JSONL worker mode:

```powershell
mathcraft worker --provider auto
```

Each JSONL request must include `"protocol": 1` and a non-empty string `id`, for example:

```json
{"protocol":1,"id":"warmup-1","action":"warmup","profile":"formula"}
```

Responses include the same protocol and request ID, an `ok` flag, and either a `result` or an `error` object. Errors retain their exception type, message, and traceback.

Worker input, output, and diagnostics use UTF-8 on every platform. Hosts must encode requests and decode responses as UTF-8; protocol data is decoded strictly so invalid bytes are reported instead of silently changing recognition text. CLI console output and exported text files also use UTF-8.

## Model Cache

MathCraft reads models from a platform-specific default user data root:

```text
Windows: %APPDATA%\MathCraft\models
macOS: ~/Library/Application Support/LaTeXSnipper/MathCraft/models
Linux: ${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models
```

or from a custom root:

```powershell
$env:MATHCRAFT_HOME="./models"
mathcraft doctor --provider auto
```

Persist the custom root for future PowerShell sessions:

```powershell
setx MATHCRAFT_HOME "./models"
```

Restore the default user cache root:

```powershell
[Environment]::SetEnvironmentVariable("MATHCRAFT_HOME", $null, "User")
Remove-Item Env:\MATHCRAFT_HOME -ErrorAction SilentlyContinue
mathcraft doctor --provider auto
```

Open a new PowerShell window after removing the persistent variable. The default root is:

```text
Windows: %APPDATA%\MathCraft\models
macOS: ~/Library/Application Support/LaTeXSnipper/MathCraft/models
Linux: ${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models
```

Model artifacts are downloaded from the MathCraft-Models release assets declared in `mathcraft_ocr/manifests/models.v1.json`.

Packaged desktop workers use only the installed model component and disable automatic model downloads. Application updates replace only the application layer; use the complete desktop installer to restore missing or damaged inference environments and models. Source desktop workers use the platform default cache; standalone library and CLI cache settings and automatic downloads remain independent. See the [user data map](https://github.com/SakuraMathcraft/LaTeXSnipper/blob/main/docs/user_data_storage.md).

## Runtime Profiles

| Profile | Models | Output |
| --- | --- | --- |
| `formula` | formula recognizer | LaTeX string |
| `text` | text detector + text recognizer | OCR text and text blocks |
| `mixed` | formula detector + formula recognizer + text detector + text recognizer | Markdown-ready structured blocks |

Each profile verifies its model files before initialization and reuses the
initialized sessions and verified paths for subsequent recognition requests.
`check_models()` and `mathcraft models check` always verify current file contents.
Restart the process after replacing model resources to load the updated files.
Formula decoder sessions expose only the last token's logits through an in-memory
graph transformation; model files and weights on disk remain unchanged.

When a custom manifest omits a model required by the selected profile, `warmup()`
reports its ID in `missing_models` and recognition raises `ModelCacheError`.
Add the model's file records, SHA-256 digests and download sources to the manifest.
Automatic downloads repair missing or corrupt files for declared models; they
cannot supply models that the manifest does not describe.

## Provider Selection

`provider_preference` accepts:

- `auto`: prefer CUDA, then a platform accelerator, and finally CPU; TensorRT remains explicit because of its first-use engine build cost.
- `cpu`: force CPU.
- `gpu`: request the first available supported accelerator.
- `cuda`: request CUDA.
- `tensorrt` or `trt`: request TensorRT, followed by CUDA and CPU for unsupported nodes.
- `directml` or `dml`: request DirectML.
- `coreml`: request CoreML.
- `openvino`: request OpenVINO.

Advanced callers can pass an explicit ordered provider list and provider options:

```python
runtime = MathCraftRuntime(
    providers=[
        (
            "TensorrtExecutionProvider",
            {
                "device_id": 0,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": "./trt-cache",
            },
        ),
        ("CUDAExecutionProvider", {"device_id": 0}),
    ]
)
```

`auto` deliberately prefers CUDA over TensorRT because TensorRT can spend substantial time building an engine on first use. Select `tensorrt` explicitly when its native runtime is installed; enable its engine cache for repeated startup performance.

The actual provider is available on recognition results through the `provider` field. Doctor and warmup reports also expose `device_id`, `device_name`, `device_uuid`, and `device_verified` under `provider_info`. GPU sessions bind the reported `device_id` explicitly; `device_verified` becomes true only after the runtime confirms the device used by initialized inference sessions.

## Development

Run tests from the repository root:

```powershell
# Run from the repository root
python -m pytest test/test_mathcraft_ocr.py test/test_mathcraft_document_engine.py test/test_formula_inference.py -q
```

Build package artifacts:

```powershell
# Run from the repository root
python -m build --no-isolation --outdir .\release_assets\mathcraft-ocr-package\dist .
```

## License

GPL-3.0-only. See `LICENSE`.

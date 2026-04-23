# LaTeXSnipper

LaTeXSnipper is a Windows desktop math workspace for capture, recognition, editing,
computation, handwriting, and document workflows.

## Recognition Runtime

The internal recognition path uses MathCraft OCR:

- formula recognition through ONNX formula detection and recognition models
- mixed text/formula recognition through ONNX text and formula components
- local worker isolation for stable GUI startup and responsive UI behavior
- model metadata managed by `mathcraft_ocr/manifests/models.v1.json`

External model services remain independent from the internal MathCraft OCR runtime.

## Project Structure

```text
LaTeXSnipper/
|-- mathcraft_ocr/
|   |-- api.py
|   |-- cli.py
|   |-- manifest.py
|   |-- runtime.py
|   |-- worker.py
|   `-- adapters/
|-- src/
|   |-- main.py
|   |-- deps_bootstrap.py
|   |-- settings_window.py
|   |-- updater.py
|   |-- backend/
|   |   |-- capture_overlay.py
|   |   |-- model.py
|   |   |-- model_factory.py
|   |   `-- platform/
|   |-- editor/
|   |-- handwriting/
|   |-- assets/
|   |-- core/
|   |-- models/
|   `-- ui/
|-- docs/
|-- test/
|-- build/
|-- LaTeXSnipper.spec
|-- requirements.txt
|-- requirements-build.txt
|-- version_info.txt
`-- readme.md
```

## Development

```powershell
cd E:\LaTexSnipper
src\deps\python311\python.exe src\main.py
```

Useful checks:

```powershell
src\deps\python311\python.exe -m ruff check --select F src mathcraft_ocr test
src\deps\python311\python.exe -m pyright
src\deps\python311\python.exe test\test_mathcraft_ocr.py
src\deps\python311\python.exe test\test_core_verify_and_ocr_cache.py
```

## License

MIT

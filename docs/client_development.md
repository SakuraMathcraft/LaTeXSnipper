# Client development and release builds

Choose any supported Python environment and select it in your IDE. Activate that environment before running `python -m pip`, tests, or the app. No interpreter directory is prescribed by the repository. `.venv` is only a convenient example; keep other local environment directories outside the checkout or in your personal Git exclusions.

From the repository root, install `requirements.txt` on Windows, `requirements-linux.txt` on Linux, or `requirements-macos.txt` on macOS. Install `ruff`, `pytest`, and `pyright` in the same environment when needed. Run `python src/main.py` for development and `python -m pytest test` for tests. Pyright accepts `--pythonpath` to select the interpreter explicitly.

Client installers are built by `.github/workflows/release.yml`, triggered by release tags or workflow dispatch. The scripts and PyInstaller specs in the repository are workflow build inputs, not a second developer packaging setup.

- Windows: Actions installs build dependencies into the interpreter provided by `actions/setup-python`, and prepares a separate clean Python seed in `RUNNER_TEMP`. The build script takes `-BundledPythonPath` explicitly and validates that it is inside that temporary directory before normalization. The spec requires `LATEXSNIPPER_BUNDLED_PYTHON`; missing input fails the build. The installer retains its internal `deps/python311` runtime for end-user dependency management. SignPath signing remains in the workflow.
- Linux/macOS: packaging uses the runner Python on PATH and installs the platform build requirements there. No extra development environment is created in the checkout or collected into the package.
- Inno Setup locates the repository relative to its script. No drive letter or personal tool installation is required.

Benchmark scripts locate the repository relative to their own files. Pass `-DataRoot` for datasets and results, `-PythonPath` for inference or `-Python` for official CDM if a different interpreter is needed. CDM tools are found on PATH; `-PathPrepend` accepts extra tool directories. See [benchmark instructions](../benchmarks/mathcraft_ocr/README.md).

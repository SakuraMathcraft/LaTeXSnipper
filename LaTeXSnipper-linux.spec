# -*- mode: python ; coding: utf-8 -*-
"""
LaTeXSnipper PyInstaller spec for Linux.

Build:
    pyinstaller LaTeXSnipper-linux.spec
"""

import os
import sys
import shutil
import json
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Workaround for deep import graph
sys.setrecursionlimit(max(5000, sys.getrecursionlimit() * 5))

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
ROOT = Path(SPECPATH)
SRC = ROOT / "src"
APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")
BUNDLE_MATHCRAFT_MODELS = os.environ.get("LATEXSNIPPER_BUNDLE_MATHCRAFT_MODELS", "0") == "1"
BUILD_CHANNEL = os.environ.get("LATEXSNIPPER_DISTRIBUTION_CHANNEL", "github").strip().lower()
STORE_PRODUCT_ID = os.environ.get("LATEXSNIPPER_STORE_PRODUCT_ID", "").strip()

if BUILD_CHANNEL not in {"github", "store"}:
    raise SystemExit(f"[SPEC] invalid LATEXSNIPPER_DISTRIBUTION_CHANNEL: {BUILD_CHANNEL!r}")

print(f"[SPEC] distribution channel: {BUILD_CHANNEL}")
print(f"[SPEC] output name: {APP_NAME}")

# ---------------------------------------------------------------------------
# Generate distribution channel metadata
# ---------------------------------------------------------------------------
generated_root = ROOT / "build" / "generated"
generated_root.mkdir(parents=True, exist_ok=True)
distribution_channel_file = generated_root / "distribution_channel.json"
distribution_channel_file.write_text(
    json.dumps({"channel": BUILD_CHANNEL, "store_product_id": STORE_PRODUCT_ID}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

extra_datas: list[tuple[str, str]] = []
extra_binaries: list[tuple[str, str]] = []

extra_datas.append((str(distribution_channel_file), "."))

# ---------------------------------------------------------------------------
# PyQt6 / Qt6 resources
# ---------------------------------------------------------------------------
PYQT6_DIR = Path(PyQt6.__file__).resolve().parent
QT6_DIR = PYQT6_DIR / "Qt6"

# Qt resource directories
QT6_RESOURCES = QT6_DIR / "resources"
QT6_LOCALES = QT6_DIR / "translations" / "qtwebengine_locales"
QT6_BIN = QT6_DIR / "bin"
QT6_LIBEXEC = QT6_DIR / "libexec"
QT6_PLUGINS = QT6_DIR / "plugins"
QT6_QML = QT6_DIR / "qml"

if QT6_RESOURCES.exists():
    extra_datas.append((str(QT6_RESOURCES), "PyQt6/Qt6/resources"))
    print("[SPEC] include Qt6 resources")

if QT6_LOCALES.exists():
    extra_datas.append((str(QT6_LOCALES), "PyQt6/Qt6/translations/qtwebengine_locales"))
    print("[SPEC] include Qt6 locales")

# Qt WebEngine process binary
for webengine_bin in [
    QT6_LIBEXEC / "QtWebEngineProcess",
    QT6_BIN / "QtWebEngineProcess",
]:
    if webengine_bin.exists():
        extra_binaries.append((str(webengine_bin), "PyQt6/Qt6/libexec"))
        print(f"[SPEC] include QtWebEngineProcess: {webengine_bin}")
        break

# Qt plugins
if QT6_PLUGINS.exists():
    extra_datas.append((str(QT6_PLUGINS), "PyQt6/Qt6/plugins"))
    print("[SPEC] include Qt6 plugins")

# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------
def _collect_tree_as_datas(src_root: Path, dest_prefix: str):
    """Collect a directory tree as PyInstaller datas tuples."""
    out = []
    if not src_root.exists():
        return out
    for p in src_root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in {".pyc", ".pyo"} or "__pycache__" in p.parts:
            continue
        rel_parent = p.relative_to(src_root).parent
        if str(rel_parent) == ".":
            dest_dir = dest_prefix
        else:
            dest_dir = f"{dest_prefix}/{str(rel_parent).replace(os.sep, '/')}"
        out.append((str(p), dest_dir))
    return out


# ---------------------------------------------------------------------------
# MathCraft OCR package
# ---------------------------------------------------------------------------
MATHCRAFT_OCR_SRC = ROOT / "mathcraft_ocr"
if MATHCRAFT_OCR_SRC.exists():
    extra_datas += _collect_tree_as_datas(MATHCRAFT_OCR_SRC, "mathcraft_ocr")
    print(f"[SPEC] include MathCraft OCR package: {MATHCRAFT_OCR_SRC}")

# ---------------------------------------------------------------------------
# Optional MathCraft model bundle
# ---------------------------------------------------------------------------
def _resolve_mathcraft_models_root() -> Path | None:
    """Locate local MathCraft model files for the offline build variant."""
    env_root = os.environ.get("MATHCRAFT_MODELS_ROOT", "").strip()
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(ROOT / "MathCraft" / "models")
    # Linux: check ~/.MathCraft/models and ~/.mathcraft/models
    home = Path.home()
    candidates.append(home / ".MathCraft" / "models")
    candidates.append(home / ".mathcraft" / "models")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


if BUNDLE_MATHCRAFT_MODELS:
    mathcraft_models_root = _resolve_mathcraft_models_root()
    if mathcraft_models_root is None:
        raise SystemExit("[SPEC] MathCraft offline build: no model root found.")
    extra_datas += _collect_tree_as_datas(mathcraft_models_root, "MathCraft/models")
    print(f"[SPEC] include bundled MathCraft models: {mathcraft_models_root}")

# ---------------------------------------------------------------------------
# certifi certificate bundle
# ---------------------------------------------------------------------------
extra_datas += collect_data_files("certifi")

# ---------------------------------------------------------------------------
# Optional bundled Python runtime
# ---------------------------------------------------------------------------
BUNDLED_PY311 = ROOT / "src" / "deps" / "python311"
if BUNDLED_PY311.exists():
    extra_datas += _collect_tree_as_datas(BUNDLED_PY311, "deps/python311")
    print(f"[SPEC] include bundled python311: {BUNDLED_PY311}")

BUNDLED_DEPS_STATE = ROOT / "src" / "deps" / ".deps_state.json"
if BUNDLED_DEPS_STATE.exists():
    extra_datas.append((str(BUNDLED_DEPS_STATE), "deps"))

# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------
ASSETS_DIR = SRC / "assets"
if ASSETS_DIR.exists():
    extra_datas.append((str(ASSETS_DIR), "assets"))
    print("[SPEC] include assets")

# advanced_cas.py (用作 CAS worker)
ADV_CAS = SRC / "editor" / "advanced_cas.py"
if ADV_CAS.exists():
    extra_datas.append((str(ADV_CAS), "editor"))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[] + extra_binaries,
    datas=[] + extra_datas,
    hiddenimports=[
        # PyQt6 / WebEngine
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",

        # QFluentWidgets
        "qfluentwidgets",
        "qfluentwidgets.common",
        "qfluentwidgets.components",
        "qframelesswindow",

        # Base dependencies
        "PIL",
        "PIL.Image",
        "pyperclip",
        "psutil",
        "requests",
        "charset_normalizer",
        "packaging",
        "json",
        "threading",
        "queue",
        "urllib.request",
        "subprocess",

        # Linux-specific optional imports
        "pynput",
        "pynput.keyboard",
        "pynput.mouse",
        "dbus",
        "gi",
        "gi.repository",
        "gi.repository.GLib",
        "gi.repository.GObject",

        # Application submodules
        "editor",
        "editor.workbench_bridge",
        "editor.workbench_window",
        "editor.advanced_cas",
        "editor.latex_snippet_panel",
        "bootstrap",
        "bootstrap.deps_bootstrap",
        "bootstrap.deps_pip_runner",
        "bootstrap.deps_python_runtime",
        "bootstrap.deps_qt_compat",
        "bootstrap.deps_state",
        "exporting",
        "exporting.formula_converters",
        "exporting.formula_export",
        "exporting.pandoc_exporter",
        "preview",
        "preview.content_preview",
        "preview.math_preview",
        "preview.smart_preview",
        "pypandoc",
        "runtime",
        "runtime.app_paths",
        "runtime.config_manager",
        "runtime.distribution",
        "runtime.history_store",
        "runtime.pandoc_runtime",
        "runtime.startup_dependency_flow",
        "runtime.startup_gui_deps",
        "runtime.webengine_runtime",
        "ui",
        "ui.edit_formula_dialog",
        "ui.favorites_window",
        "ui.formula_export_menu",
        "ui.pdf_result_window",
        "ui.window_helpers",
        "workers",
        "workers.recognition_workers",
        "handwriting",
        "handwriting.handwriting_window",
        "handwriting.ink_canvas",
        "handwriting.recognizer",
        "handwriting.stroke_store",
        "handwriting.tools",
        "handwriting.types",

        # Dynamic imports used by mathcraft_ocr / rapidocr
        "onnxruntime",
        "onnxruntime.capi",
        "onnx",
        "shapely",
        "pyclipper",
        "omegaconf",
        "yaml",
        "cv2",
        "numpy",
        "lxml",
        "fitz",
        "matplotlib",
        "latex2mathml",
        "pydantic_core",
        "markupsafe",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy ML frameworks managed outside the main process
        "transformers",
        "onnxruntime-gpu",
        "tensorflow",
        "keras",
        "scipy",
        "pandas",
        "google",
        "google.protobuf",
        "aiohttp",
        "frozenlist",
        "multidict",
        "propcache",
        "yarl",
        "ctranslate2",
        "setuptools",
        "pkg_resources",

        # Unused standard-library modules
        "tkinter",
        "unittest",
        "test",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)

# ---------------------------------------------------------------------------
# PYZ
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# EXE
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,             # Linux 上不适用 .ico
)

# ---------------------------------------------------------------------------
# COLLECT (onedir 输出)
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# ---------------------------------------------------------------------------
# Post-build pruning
# ---------------------------------------------------------------------------
def _prune_collect_tree_linux(dist_root: Path):
    """Remove unneeded files from the collected output."""
    if not dist_root.exists():
        return

    remove_names = {"Pythonwin", "setuptools", "google"}
    remove_prefixes = (
        "aiohttp", "frozenlist", "multidict", "propcache", "yarl",
        "ctranslate2", "regex",
        "safetensors", "sentencepiece",
    )
    for child in dist_root.iterdir():
        try:
            name = child.name
            if child.is_dir() and (
                name in remove_names
                or name.endswith(".dist-info")
                or any(name == prefix or name.startswith(f"{prefix}.") for prefix in remove_prefixes)
            ):
                shutil.rmtree(child, ignore_errors=True)
                print(f"[SPEC] pruned: {child.name}")
        except Exception as exc:
            print(f"[SPEC] prune skip {child}: {exc}")


_prune_collect_tree_linux(Path(DISTPATH) / APP_NAME / "_internal")

print(f"\n[SPEC] build complete: {Path(DISTPATH) / APP_NAME}")

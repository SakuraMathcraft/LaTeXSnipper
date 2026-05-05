# -*- mode: python ; coding: utf-8 -*-
"""
LaTeXSnipper PyInstaller spec.

Build command:
    pyinstaller LaTeXSnipper.spec
    pyinstaller LaTeXSnipper.offline.spec

This spec bundles required resources/dependencies so the app can run on target machines.
"""

import os
import sys
import shutil
import json
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files

# Workaround for deep import graph on Windows (PyInstaller recursion guard)
sys.setrecursionlimit(max(5000, sys.getrecursionlimit() * 5))

# Project roots
ROOT = Path(SPECPATH)
SRC = ROOT / "src"
APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")
BUNDLE_MATHCRAFT_MODELS = os.environ.get("LATEXSNIPPER_BUNDLE_MATHCRAFT_MODELS", "0") == "1"
BUILD_CHANNEL = os.environ.get("LATEXSNIPPER_DISTRIBUTION_CHANNEL", "github").strip().lower()
STORE_PRODUCT_ID = os.environ.get("LATEXSNIPPER_STORE_PRODUCT_ID", "").strip()
BUNDLED_DEPS_DIR_ENV = os.environ.get("LATEXSNIPPER_BUNDLED_DEPS_DIR", "").strip()
BUNDLE_PYTHON_INSTALLER = os.environ.get("LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER", "1").strip() != "0"
if BUILD_CHANNEL not in {"github", "store"}:
    raise SystemExit(f"[SPEC] invalid LATEXSNIPPER_DISTRIBUTION_CHANNEL: {BUILD_CHANNEL!r}")

# PyQt6 Qt6 resource folders (WebEngine runtime assets)
PYQT6_DIR = Path(PyQt6.__file__).resolve().parent
QT6_DIR = PYQT6_DIR / "Qt6"
QT6_RESOURCES = QT6_DIR / "resources"
QT6_LOCALES = QT6_DIR / "translations" / "qtwebengine_locales"
QT6_BIN = QT6_DIR / "bin"

extra_datas = []
extra_binaries = []
generated_root = ROOT / "build" / "generated"
generated_root.mkdir(parents=True, exist_ok=True)
distribution_channel_file = generated_root / "distribution_channel.json"
distribution_channel_file.write_text(
    json.dumps(
        {
            "channel": BUILD_CHANNEL,
            "store_product_id": STORE_PRODUCT_ID,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
extra_datas.append((str(distribution_channel_file), "."))
print(f"[SPEC] distribution channel: {BUILD_CHANNEL}")
if BUILD_CHANNEL == "store" and not STORE_PRODUCT_ID:
    print("[SPEC] store product id is not set; Store build will open the Store updates page.")
if QT6_RESOURCES.exists():
    extra_datas.append((str(QT6_RESOURCES), "PyQt6/Qt6/resources"))
if QT6_LOCALES.exists():
    extra_datas.append((str(QT6_LOCALES), "PyQt6/Qt6/translations/qtwebengine_locales"))
if (QT6_BIN / "QtWebEngineProcess.exe").exists():
    extra_binaries.append((str(QT6_BIN / "QtWebEngineProcess.exe"), "PyQt6/Qt6/bin"))


def _collect_pywin32_system32_binaries():
    """Collect pythoncom/pywintypes runtime DLLs for frozen app."""
    bins = []
    seen = set()
    for p in map(Path, sys.path):
        cand = p / "pywin32_system32"
        if not cand.exists():
            continue
        for pattern in ("pythoncom*.dll", "pywintypes*.dll"):
            for dll in cand.glob(pattern):
                item = (str(dll), "pywin32_system32")
                if item not in seen:
                    bins.append(item)
                    seen.add(item)
    return bins


extra_binaries += _collect_pywin32_system32_binaries()

# Data files for bundled minimal runtime
extra_datas += collect_data_files("certifi")


def _collect_tree_as_datas(src_root: Path, dest_prefix: str):
    """Convert a directory tree into PyInstaller datas 2-tuples."""
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


MATHCRAFT_OCR_SRC = ROOT / "mathcraft_ocr"
if MATHCRAFT_OCR_SRC.exists():
    extra_datas += _collect_tree_as_datas(MATHCRAFT_OCR_SRC, "mathcraft_ocr")
    print(f"[SPEC] include MathCraft OCR package: {MATHCRAFT_OCR_SRC}")
else:
    print(f"[SPEC] MathCraft OCR package not found, skip: {MATHCRAFT_OCR_SRC}")


def _resolve_mathcraft_models_root() -> Path | None:
    """Locate local MathCraft model files for the offline build variant."""
    env_root = os.environ.get("MATHCRAFT_MODELS_ROOT", "").strip()
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(ROOT / "MathCraft" / "models")
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        candidates.append(Path(appdata) / "MathCraft" / "models")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


if BUNDLE_MATHCRAFT_MODELS:
    mathcraft_models_root = _resolve_mathcraft_models_root()
    if mathcraft_models_root is None:
        raise SystemExit(
            "[SPEC] MathCraft offline build requested, but no model root was found. "
            "Set MATHCRAFT_MODELS_ROOT or place models under MathCraft/models."
        )
    else:
        extra_datas += _collect_tree_as_datas(mathcraft_models_root, "MathCraft/models")
        print(f"[SPEC] include bundled MathCraft models: {mathcraft_models_root}")
else:
    print("[SPEC] MathCraft models are not bundled in this build.")


def _prune_collect_tree(dist_root: Path):
    """Remove weakly-related runtime artifacts from final onedir output."""
    if not dist_root.exists():
        return
    remove_names = {"Pythonwin", "setuptools", "google"}
    remove_prefixes = (
        "aiohttp",
        "frozenlist",
        "multidict",
        "propcache",
        "yarl",
        "ctranslate2",
        "cv2",
        "rapidocr",
        "numpy",
        "numpy.libs",
        "lxml",
        "fitz",
        "matplotlib",
        "latex2mathml",
        "contourpy",
        "fontTools",
        "kiwisolver",
        "shapely",
        "pyclipper",
        "yaml",
        "markupsafe",
        "pydantic_core",
        "regex",
        "safetensors",
        "sentencepiece",
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
        except Exception as exc:
            print(f"[SPEC] prune skip {child}: {exc}")

    _prune_bundled_python_site_packages(dist_root)
    _prune_qt_webengine_payload(dist_root)


def _prune_qt_webengine_payload(dist_root: Path):
    """Trim optional Qt WebEngine payload while keeping runtime-critical files."""
    qt_roots = [
        dist_root / "PyQt6" / "Qt6",
        dist_root / "Qt6",
    ]
    for qt_root in qt_roots:
        if not qt_root.exists():
            continue

        resources_dir = qt_root / "resources"
        if resources_dir.exists():
            for pattern in ("*.debug.pak", "*.debug.bin"):
                for child in resources_dir.glob(pattern):
                    try:
                        child.unlink(missing_ok=True)
                        print(f"[SPEC] pruned Qt WebEngine debug resource: {child.relative_to(dist_root)}")
                    except Exception as exc:
                        print(f"[SPEC] prune Qt WebEngine debug resource skip {child}: {exc}")

        locales_dir = qt_root / "translations" / "qtwebengine_locales"
        if locales_dir.exists():
            keep_locales = {"en-US.pak", "en-GB.pak", "zh-CN.pak", "zh-TW.pak"}
            for child in locales_dir.glob("*.pak"):
                if child.name in keep_locales:
                    continue
                try:
                    child.unlink(missing_ok=True)
                    print(f"[SPEC] pruned Qt WebEngine locale: {child.relative_to(dist_root)}")
                except Exception as exc:
                    print(f"[SPEC] prune Qt WebEngine locale skip {child}: {exc}")


def _prune_bundled_python_site_packages(dist_root: Path):
    """Keep bundled python311 as an installer/runtime seed, not as a dependency layer."""
    site_packages = dist_root / "deps" / "python311" / "Lib" / "site-packages"
    if not site_packages.exists():
        return

    keep_names = {
        "_distutils_hack",
        "distutils-precedence.pth",
        "packaging",
        "pip",
        "pkg_resources",
        "README.txt",
        "setuptools",
        "wheel",
    }
    keep_prefixes = (
        "packaging-",
        "pip-",
        "setuptools-",
        "wheel-",
    )

    for child in site_packages.iterdir():
        try:
            name = child.name
            if name in keep_names or any(name.startswith(prefix) for prefix in keep_prefixes):
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            print(f"[SPEC] pruned bundled python package: {child.relative_to(dist_root)}")
        except Exception as exc:
            print(f"[SPEC] prune bundled python package skip {child}: {exc}")

    scripts_dir = dist_root / "deps" / "python311" / "Scripts"
    if scripts_dir.exists():
        for child in scripts_dir.iterdir():
            try:
                name = child.name.lower()
                if name.startswith(("pip", "easy_install", "wheel")):
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
                print(f"[SPEC] pruned bundled python script: {child.relative_to(dist_root)}")
            except Exception as exc:
                print(f"[SPEC] prune bundled python script skip {child}: {exc}")


def _resolve_bundled_deps_root() -> Path:
    if BUNDLED_DEPS_DIR_ENV:
        return Path(BUNDLED_DEPS_DIR_ENV).expanduser()
    return ROOT


# Bundle dependency runtime. Store builds pass a clean CPU-only deps root here.
BUNDLED_DEPS_ROOT = _resolve_bundled_deps_root()
BUNDLED_PY311 = BUNDLED_DEPS_ROOT / "python311"
if BUNDLED_PY311.exists():
    extra_datas += _collect_tree_as_datas(BUNDLED_PY311, "deps/python311")
    print(f"[SPEC] include bundled python311: {BUNDLED_PY311}")
else:
    print(f"[SPEC] bundled python311 not found, skip: {BUNDLED_PY311}")

BUNDLED_DEPS_STATE = BUNDLED_DEPS_ROOT / ".deps_state.json"
if BUNDLED_DEPS_STATE.exists():
    extra_datas.append((str(BUNDLED_DEPS_STATE), "deps"))
    print(f"[SPEC] include bundled deps state: {BUNDLED_DEPS_STATE}")
else:
    print(f"[SPEC] bundled deps state not found, skip: {BUNDLED_DEPS_STATE}")

# Optional offline Python installer. Store packages carry a complete CPU runtime
# and should not include a nested Python installer.
BUNDLED_PY_INSTALLER = ROOT / "python-3.11.0-amd64.exe"
optional_root_datas = []
if BUILD_CHANNEL != "store" and BUNDLE_PYTHON_INSTALLER and BUNDLED_PY_INSTALLER.exists():
    optional_root_datas.append((str(BUNDLED_PY_INSTALLER), "."))
    print(f"[SPEC] include bundled installer: {BUNDLED_PY_INSTALLER}")
elif BUILD_CHANNEL == "store":
    print("[SPEC] store build skips bundled Python installer.")
elif not BUNDLE_PYTHON_INSTALLER:
    print("[SPEC] bundled Python installer disabled by LATEXSNIPPER_BUNDLE_PYTHON_INSTALLER=0.")
else:
    print(f"[SPEC] bundled installer not found, skip: {BUNDLED_PY_INSTALLER}")


a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[] + extra_binaries,
    datas=[
        # Resource folders
        (str(SRC / "assets"), "assets"),

        # Code folders
        (str(SRC / "backend"), "backend"),
        (str(SRC / "bootstrap"), "bootstrap"),
        (str(SRC / "editor"), "editor"),
        (str(SRC / "exporting"), "exporting"),
        (str(SRC / "handwriting"), "handwriting"),
        (str(SRC / "core"), "core"),
        (str(SRC / "preview"), "preview"),
        (str(SRC / "runtime"), "runtime"),
        (str(SRC / "ui"), "ui"),
        (str(SRC / "workers"), "workers"),
    ] + optional_root_datas + extra_datas,
    hiddenimports=[
        # PyQt6 / WebEngine core
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",

        # QFluentWidgets
        "qfluentwidgets",
        "qfluentwidgets.common",
        "qfluentwidgets.components",
        "qframelesswindow",

        # pywin32 / COM runtime
        "pythoncom",
        "pywintypes",
        "win32api",
        "win32con",
        "win32gui",
        "win32com",
        "win32com.client",
        "win32comext",
        "win32comext.shell",
        "win32comext.shell.shell",
        "win32comext.shell.shellcon",
        "win32timezone",

        # Base deps
        "PIL",
        "PIL.Image",
        "pyperclip",
        "psutil",
        "requests",
        "charset_normalizer",
        "charset_normalizer.api",
        "charset_normalizer.models",
        "charset_normalizer.md",
        "charset_normalizer.md__mypyc",
        "packaging",
        "json",
        "threading",
        "queue",
        "urllib.request",
        "subprocess",

        # WebEngine formula preview
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",

        "editor",
        "editor.workbench_bridge",
        "editor.workbench_window",
        "editor.advanced_cas",
        "bootstrap",
        "bootstrap.deps_bootstrap",
        "bootstrap.deps_pip_runner",
        "bootstrap.deps_python_runtime",
        "bootstrap.deps_qt_compat",
        "bootstrap.deps_state",
        "exporting",
        "exporting.formula_converters",
        "exporting.formula_export",
        "preview",
        "preview.content_preview",
        "preview.math_preview",
        "preview.smart_preview",
        "runtime",
        "runtime.app_paths",
        "runtime.config_manager",
        "runtime.distribution",
        "runtime.history_store",
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Runtime deps are managed by the MathCraft dependency environment.
        "_polars_runtime_32",
        "_polars_runtime_64",
        "_polars_runtime_compat",
        "transformers",
        "onnxruntime",
        "onnxruntime-gpu",
        "tensorflow",
        "keras",
        "scipy",
        "pandas",
        "numpy",
        "numpy.distutils",
        "onnx",
        "cv2",
        "rapidocr",
        "google",
        "google.protobuf",
        "aiohttp",
        "frozenlist",
        "multidict",
        "propcache",
        "yarl",
        "ctranslate2",
        "lxml",
        "fitz",
        "matplotlib",
        "latex2mathml",
        "contourpy",
        "fontTools",
        "kiwisolver",
        "shapely",
        "pyclipper",
        "yaml",
        "markupsafe",
        "pydantic_core",
        "regex",
        "safetensors",
        "sentencepiece",
        "Pythonwin",
        "win32ui",
        "setuptools",
        "pkg_resources",

        # Unused modules
        "tkinter",
        "unittest",
        "test",
        "tests",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

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
    console=False,  # default: no console window; debug console can be opened at runtime by app setting
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SRC / "assets" / "icon.ico") if (SRC / "assets" / "icon.ico").exists() else None,
    version=str(ROOT / "version_info.txt") if (ROOT / "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

_prune_collect_tree(Path(DISTPATH) / APP_NAME / "_internal")

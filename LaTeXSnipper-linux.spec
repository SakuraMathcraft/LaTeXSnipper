# -*- mode: python ; coding: utf-8 -*-
"""
LaTeXSnipper PyInstaller spec for Linux.

Build:
    pyinstaller LaTeXSnipper-linux.spec
"""

import os
import sys
import shutil
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
SCRIPTS = ROOT / "scripts"
APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")
if str(SCRIPTS) in sys.path:
    sys.path.remove(str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS))

from linux_hotkey_packaging import collect_linux_hotkey_modules
from payload_pruning import prune_qt_payload

print(f"[SPEC] output name: {APP_NAME}")


LINUX_HOTKEY_HIDDENIMPORTS = collect_linux_hotkey_modules(collect_submodules)
print(f"[SPEC] include Linux hotkey modules: {len(LINUX_HOTKEY_HIDDENIMPORTS)}")

extra_datas: list[tuple[str, str]] = []
extra_binaries: list[tuple[str, str]] = []
extra_datas.append((str(ROOT / "VERSION"), "."))

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
# ---------------------------------------------------------------------------
# certifi certificate bundle
# ---------------------------------------------------------------------------
extra_datas += collect_data_files("certifi")

# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------
ASSETS_DIR = SRC / "assets"
if ASSETS_DIR.exists():
    extra_datas.append((str(ASSETS_DIR), "assets"))
    print("[SPEC] include assets")

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
        *LINUX_HOTKEY_HIDDENIMPORTS,
        "dbus",
        "gi",
        "gi.repository",
        "gi.repository.GLib",
        "gi.repository.GObject",

        # Application submodules
        "editor",
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
        "runtime.webengine_runtime",
        "ui",
        "ui.edit_formula_dialog",
        "ui.favorites_window",
        "ui.formula_export_menu",
        "ui.pdf_result_window",
        "ui.window_helpers",
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
        # Inference dependencies belong to the independent inference component.
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
    icon=None,
)

# ---------------------------------------------------------------------------
# COLLECT
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
        "ctranslate2", "cv2", "rapidocr",
        "numpy", "numpy.libs",
        "shapely", "pyclipper",
        "yaml", "markupsafe", "pydantic_core",
        "regex", "safetensors", "sentencepiece",
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

    prune_qt_payload(dist_root)


_prune_collect_tree_linux(Path(DISTPATH) / APP_NAME / "_internal")

print(f"\n[SPEC] build complete: {Path(DISTPATH) / APP_NAME}")

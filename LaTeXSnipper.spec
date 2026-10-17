# -*- mode: python ; coding: utf-8 -*-
"""
LaTeXSnipper PyInstaller spec.

Build command:
    pyinstaller LaTeXSnipper.spec

This spec bundles required resources/dependencies so the app can run on target machines.
"""

import os
import sys
import shutil
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files

# Workaround for deep import graph on Windows (PyInstaller recursion guard)
sys.setrecursionlimit(max(5000, sys.getrecursionlimit() * 5))

# Project roots
ROOT = Path(SPECPATH)
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT / "scripts"))
from payload_pruning import prune_qt_payload
from runtime.product_version import PRODUCT_VERSION, write_windows_version_info

APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")
VERSION_INFO_PATH = ROOT / "build" / "version_info.txt"
write_windows_version_info(VERSION_INFO_PATH, PRODUCT_VERSION)

# PyQt6 Qt6 resource folders (WebEngine runtime assets)
PYQT6_DIR = Path(PyQt6.__file__).resolve().parent
QT6_DIR = PYQT6_DIR / "Qt6"
QT6_RESOURCES = QT6_DIR / "resources"
QT6_LOCALES = QT6_DIR / "translations" / "qtwebengine_locales"
QT6_BIN = QT6_DIR / "bin"

extra_datas = []
extra_binaries = []
extra_datas.append((str(ROOT / "VERSION"), "."))
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

    prune_qt_payload(dist_root)


a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC), str(ROOT)],
    binaries=[] + extra_binaries,
    datas=[
        (str(SRC / "assets"), "assets"),
    ] + extra_datas,
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
    version=str(VERSION_INFO_PATH),
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

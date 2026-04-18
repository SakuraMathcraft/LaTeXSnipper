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

# PyQt6 Qt6 resource folders (WebEngine runtime assets)
PYQT6_DIR = Path(PyQt6.__file__).resolve().parent
QT6_DIR = PYQT6_DIR / "Qt6"
QT6_RESOURCES = QT6_DIR / "resources"
QT6_LOCALES = QT6_DIR / "translations" / "qtwebengine_locales"
QT6_BIN = QT6_DIR / "bin"

extra_datas = []
extra_binaries = []
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
        rel_parent = p.relative_to(src_root).parent
        if str(rel_parent) == ".":
            dest_dir = dest_prefix
        else:
            dest_dir = f"{dest_prefix}/{str(rel_parent).replace(os.sep, '/')}"
        out.append((str(p), dest_dir))
    return out


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
        "psutil",
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


def _prune_bundled_python_site_packages(dist_root: Path):
    """Keep bundled python311 as an installer/runtime seed, not as a dependency layer."""
    site_packages = dist_root / "deps" / "python311" / "Lib" / "site-packages"
    if not site_packages.exists():
        return

    keep_names = {
        "_distutils_hack",
        "distutils-precedence.pth",
        "pip",
        "pkg_resources",
        "README.txt",
        "setuptools",
        "wheel",
    }
    keep_prefixes = (
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


# Bundle root python311 folder (offline dependency deployment)
BUNDLED_PY311 = ROOT / "python311"
if BUNDLED_PY311.exists():
    extra_datas += _collect_tree_as_datas(BUNDLED_PY311, "deps/python311")
    print(f"[SPEC] include bundled python311: {BUNDLED_PY311}")
else:
    print(f"[SPEC] bundled python311 not found, skip: {BUNDLED_PY311}")

# Optional offline Python installer
BUNDLED_PY_INSTALLER = ROOT / "python-3.11.0-amd64.exe"
optional_root_datas = []
if BUNDLED_PY_INSTALLER.exists():
    optional_root_datas.append((str(BUNDLED_PY_INSTALLER), "."))
    print(f"[SPEC] include bundled installer: {BUNDLED_PY_INSTALLER}")
else:
    print(f"[SPEC] bundled installer not found, skip: {BUNDLED_PY_INSTALLER}")


a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[] + extra_binaries,
    datas=[
        # Resource folders
        (str(SRC / "assets"), "assets"),

        # Code folders
        (str(SRC / "backend"), "backend"),
        (str(SRC / "editor"), "editor"),
        (str(SRC / "handwriting"), "handwriting"),
        (str(SRC / "ui"), "ui"),
        (str(SRC / "core"), "core"),
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

        # Shared torch runtime module
        "backend.torch_runtime",
        "editor",
        "editor.workbench_bridge",
        "editor.workbench_window",
        "editor.advanced_cas",
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
    runtime_hooks=[str(SRC / "runtime_hook_env.py")] if (SRC / "runtime_hook_env.py").exists() else [],
    excludes=[
        # Large deps (installed via dependency wizard)
        "torch",
        "torchvision",
        "torchaudio",
        "pix2text",
        "pix2tex",
        "unimernet",
        "timm",
        "wandb",
        "polars",
        "pyarrow",
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
        "google",
        "google.protobuf",
        "aiohttp",
        "frozenlist",
        "multidict",
        "propcache",
        "yarl",
        "ctranslate2",
        "psutil",
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
    name="LaTeXSnipper",
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
    name="LaTeXSnipper",
)

_prune_collect_tree(Path(DISTPATH) / "LaTeXSnipper" / "_internal")

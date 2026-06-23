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
from PyInstaller.utils.hooks import collect_data_files

# Workaround for deep import graph
sys.setrecursionlimit(max(5000, sys.getrecursionlimit() * 5))

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
ROOT = Path(SPECPATH)
SRC = ROOT / "src"
APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")

print(f"[SPEC] output name: {APP_NAME}")

extra_datas: list[tuple[str, str]] = []
extra_binaries: list[tuple[str, str]] = []

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
        # Runtime deps are managed by the user dependency environment.
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
        "numpy", "numpy.libs", "lxml", "fitz",
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

    _prune_bundled_python_runtime(dist_root)
    _prune_qt_webengine_payload(dist_root)


def _prune_bundled_python_runtime(dist_root: Path):
    """Trim an embedded dependency Python seed when present."""
    py_roots = [
        dist_root / "deps" / "python311",
        dist_root / "python311",
    ]
    remove_relatives = (
        "include",
        "libs",
        "tcl",
        "NEWS.txt",
        "Lib/ensurepip",
        "Lib/venv",
        "Lib/idlelib",
        "Lib/lib2to3",
        "Lib/pydoc_data",
        "Lib/tkinter",
        "Lib/turtledemo",
        "Lib/unittest",
        "Lib/ctypes/test",
        "Lib/distutils/tests",
        "Lib/doctest.py",
        "Lib/pdb.py",
        "Lib/pydoc.py",
        "Lib/turtle.py",
        "DLLs/_ctypes_test.pyd",
        "DLLs/_testbuffer.pyd",
        "DLLs/_testcapi.pyd",
        "DLLs/_testconsole.pyd",
        "DLLs/_testimportmultiple.pyd",
        "DLLs/_testinternalcapi.pyd",
        "DLLs/_testmultiphase.pyd",
        "DLLs/_tkinter.pyd",
        "DLLs/tcl86t.dll",
        "DLLs/tk86t.dll",
        "DLLs/py.ico",
        "DLLs/pyc.ico",
        "DLLs/pyd.ico",
        "DLLs/python_lib.cat",
        "DLLs/python_tools.cat",
    )
    for py_root in py_roots:
        if not py_root.exists():
            continue
        for relative in remove_relatives:
            target = py_root / relative
            if not target.exists():
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
            except Exception:
                pass
        lib_root = py_root / "Lib"
        if lib_root.exists():
            for cache_dir in lib_root.rglob("__pycache__"):
                shutil.rmtree(cache_dir, ignore_errors=True)


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
            for name in ("qtwebengine_devtools_resources.pak",):
                child = resources_dir / name
                if child.exists():
                    try:
                        child.unlink(missing_ok=True)
                    except Exception:
                        pass
            for pattern in ("*.debug.pak", "*.debug.bin"):
                for child in resources_dir.glob(pattern):
                    try:
                        child.unlink(missing_ok=True)
                    except Exception:
                        pass

        qml_dir = qt_root / "qml"
        if qml_dir.exists():
            shutil.rmtree(qml_dir, ignore_errors=True)

        translations_dir = qt_root / "translations"
        if translations_dir.exists():
            keep_translation_markers = ("_zh_CN", "_zh_TW", "_en")
            for child in translations_dir.iterdir():
                if child.name == "qtwebengine_locales":
                    continue
                if child.is_file() and child.suffix.lower() == ".qm" and any(
                    marker in child.stem for marker in keep_translation_markers
                ):
                    continue
                try:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
                except Exception:
                    pass

        locales_dir = qt_root / "translations" / "qtwebengine_locales"
        if locales_dir.exists():
            keep_locales = {"en-US.pak", "en-GB.pak", "zh-CN.pak", "zh-TW.pak"}
            for child in locales_dir.glob("*.pak"):
                if child.name in keep_locales:
                    continue
                try:
                    child.unlink(missing_ok=True)
                except Exception:
                    pass

        bin_dir = qt_root / "bin"
        if bin_dir.exists():
            removable_bins = {
                "Qt6Pdf.dll",
                "Qt6PdfQuick.dll",
                "Qt6WebEngineQuick.dll",
                "Qt6WebEngineQuickDelegatesQml.dll",
                "Qt6Quick3D.dll",
                "Qt6Quick3DAssetImport.dll",
                "Qt6Quick3DAssetUtils.dll",
                "Qt6Quick3DEffects.dll",
                "Qt6Quick3DHelpers.dll",
                "Qt6Quick3DHelpersImpl.dll",
                "Qt6Quick3DParticles.dll",
                "Qt6Quick3DPhysics.dll",
                "Qt6Quick3DPhysicsHelpers.dll",
                "Qt6Quick3DRuntimeRender.dll",
                "Qt6Quick3DSpatialAudio.dll",
                "Qt6Quick3DUtils.dll",
                "Qt6Quick3DXr.dll",
                "Qt6Multimedia.dll",
                "Qt6MultimediaQuick.dll",
                "Qt6Sensors.dll",
                "Qt6SensorsQuick.dll",
                "Qt6RemoteObjects.dll",
                "Qt6RemoteObjectsQml.dll",
                "Qt6SerialPort.dll",
                "Qt6TextToSpeech.dll",
                "Qt6StateMachine.dll",
                "Qt6StateMachineQml.dll",
                "Qt6QuickTest.dll",
                "Qt6Test.dll",
                "Qt6WebSockets.dll",
                "Qt6SpatialAudio.dll",
                "Qt6QuickControls2Imagine.dll",
                "Qt6QuickControls2ImagineStyleImpl.dll",
                "Qt6QuickControls2Material.dll",
                "Qt6QuickControls2MaterialStyleImpl.dll",
                "Qt6QuickControls2Universal.dll",
                "Qt6QuickControls2UniversalStyleImpl.dll",
            }
            for name in removable_bins:
                child = bin_dir / name
                if child.exists():
                    try:
                        child.unlink(missing_ok=True)
                    except Exception:
                        pass


_prune_collect_tree_linux(Path(DISTPATH) / APP_NAME / "_internal")

print(f"\n[SPEC] build complete: {Path(DISTPATH) / APP_NAME}")

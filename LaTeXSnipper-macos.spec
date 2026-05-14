# -*- mode: python ; coding: utf-8 -*-
"""
LaTeXSnipper PyInstaller spec for macOS.

Build:
    pyinstaller LaTeXSnipper-macos.spec
"""

import os
import sys
import shutil
import json
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
BUILD_CHANNEL = os.environ.get("LATEXSNIPPER_DISTRIBUTION_CHANNEL", "github").strip().lower()
STORE_PRODUCT_ID = os.environ.get("LATEXSNIPPER_STORE_PRODUCT_ID", "").strip()
ICON_ICNS_ENV = os.environ.get("LATEXSNIPPER_ICON_ICNS", "").strip()
ICON_ICNS = Path(ICON_ICNS_ENV).expanduser() if ICON_ICNS_ENV else SRC / "assets" / "icon.icns"
if not ICON_ICNS.exists():
    ICON_ICNS = None

if BUILD_CHANNEL not in {"github", "store"}:
    raise SystemExit(f"[SPEC] invalid LATEXSNIPPER_DISTRIBUTION_CHANNEL: {BUILD_CHANNEL!r}")

print(f"[SPEC] platform: macOS")
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

QT6_RESOURCES = QT6_DIR / "resources"
QT6_LOCALES = QT6_DIR / "translations" / "qtwebengine_locales"
QT6_PLUGINS = QT6_DIR / "plugins"
QT6_QML = QT6_DIR / "qml"

if QT6_RESOURCES.exists():
    extra_datas.append((str(QT6_RESOURCES), "PyQt6/Qt6/resources"))
    print("[SPEC] include Qt6 resources")

if QT6_LOCALES.exists():
    extra_datas.append((str(QT6_LOCALES), "PyQt6/Qt6/translations/qtwebengine_locales"))
    print("[SPEC] include Qt6 locales")

# Qt WebEngine process bundle
qt_webengine_framework = QT6_DIR / "lib" / "QtWebEngineCore.framework"
if qt_webengine_framework.exists():
    helpers_dir = qt_webengine_framework / "Helpers"
    if helpers_dir.exists():
        extra_datas.append((str(helpers_dir), "PyQt6/Qt6/lib/QtWebEngineCore.framework/Helpers"))
        print("[SPEC] include QtWebEngineCore Helpers")
    # QtWebEngineProcess.app path
    process_app = helpers_dir / "QtWebEngineProcess.app"
    if process_app.exists():
        extra_datas.append((str(process_app), "PyQt6/Qt6/lib/QtWebEngineCore.framework/Helpers"))
        print("[SPEC] include QtWebEngineProcess.app")
else:
    # Fallback: check Qt6/libexec
    QT6_LIBEXEC = QT6_DIR / "libexec"
    for webengine_bin in [
        QT6_LIBEXEC / "QtWebEngineProcess",
        QT6_DIR / "bin" / "QtWebEngineProcess",
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

        # macOS global hotkeys
        "pynput",
        "pynput.keyboard",
        "pynput.mouse",

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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ML runtimes are managed outside the main process
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
        "setuptools",
        "pkg_resources",

        # Platform-independent exclusions
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
    icon=str(ICON_ICNS) if ICON_ICNS is not None else None,
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
# BUNDLE
# ---------------------------------------------------------------------------
app_bundle = BUNDLE(
    coll,
    name=APP_NAME + ".app",
    icon=str(ICON_ICNS) if ICON_ICNS is not None else None,
    bundle_identifier="com.mathcraft.latexsnipper",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSHighResolutionCapable": True,
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": "LaTeXSnipper",
        "CFBundleIdentifier": "com.mathcraft.latexsnipper",
        "CFBundleVersion": "2.3.2",
        "CFBundleShortVersionString": "2.3.2",
        "NSHumanReadableCopyright": "Copyright 2026 Mathcraft",
        "CFBundleDocumentTypes": [],
        "LSMinimumSystemVersion": "11.0",
    },
)

# ---------------------------------------------------------------------------
# Post-build pruning
# ---------------------------------------------------------------------------
def _prune_collect_tree_macos(dist_root: Path):
    """Remove unneeded runtime payload from the app bundle."""
    if not dist_root.exists():
        return
    remove_names = {"Pythonwin", "setuptools", "google"}
    remove_prefixes = (
        "aiohttp", "frozenlist", "multidict", "propcache", "yarl",
        "ctranslate2", "cv2", "rapidocr",
        "numpy", "numpy.libs", "lxml", "fitz",
        "matplotlib", "latex2mathml",
        "contourpy", "fontTools", "kiwisolver",
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
        except Exception as exc:
            print(f"[SPEC] prune skip {child}: {exc}")

    _prune_qt_webengine_payload(dist_root)


def _prune_qt_webengine_payload(dist_root: Path):
    """Trim optional Qt WebEngine payload."""
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
                    except Exception:
                        pass

        locales_dir = qt_root / "translations" / "qtwebengine_locales"
        if locales_dir.exists():
            keep_locales = {"en-US.pak", "en-GB.pak", "zh-CN.pak", "zh-TW.pak"}
            for child in locales_dir.glob("*.pak"):
                if child.name not in keep_locales:
                    try:
                        child.unlink(missing_ok=True)
                    except Exception:
                        pass


_prune_collect_tree_macos(Path(DISTPATH) / APP_NAME / "_internal")

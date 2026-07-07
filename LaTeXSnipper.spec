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
APP_NAME = os.environ.get("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipper")
BUNDLED_DEPS_DIR_ENV = os.environ.get("LATEXSNIPPER_BUNDLED_DEPS_DIR", "").strip()

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
    _prune_bundled_python_runtime(dist_root)
    _prune_qt_webengine_payload(dist_root)


def _prune_qt_webengine_payload(dist_root: Path):
    """Trim optional Qt WebEngine payload while keeping runtime-critical files."""
    qt_roots = [
        dist_root / "PyQt6" / "Qt6",
        dist_root / "Qt6",
    ]

    def _qt_name_aliases(stem: str) -> set[str]:
        aliases = {stem}
        if stem.startswith("Qt6"):
            aliases.add("Qt" + stem[3:])
        return aliases

    def _remove_optional_qt_libraries(qt_root: Path, stems: set[str]) -> None:
        for library_dir in (qt_root / "bin", qt_root / "lib"):
            if not library_dir.exists():
                continue
            for stem in stems:
                for alias in _qt_name_aliases(stem):
                    candidates = [
                        library_dir / f"{alias}.dll",
                        library_dir / f"lib{alias}.so",
                        library_dir / f"lib{alias}.dylib",
                        library_dir / f"{alias}.dylib",
                        library_dir / f"{alias}.framework",
                    ]
                    candidates.extend(library_dir.glob(f"lib{alias}.so.*"))
                    for child in candidates:
                        if not child.exists():
                            continue
                        try:
                            if child.is_dir():
                                shutil.rmtree(child, ignore_errors=True)
                            else:
                                child.unlink(missing_ok=True)
                            print(f"[SPEC] pruned optional Qt library: {child.relative_to(dist_root)}")
                        except Exception as exc:
                            print(f"[SPEC] prune optional Qt library skip {child}: {exc}")

    def _remove_optional_qt_plugins(plugins_dir: Path, relative_paths: set[Path]) -> None:
        for relative_path in relative_paths:
            plugin_dir = plugins_dir / relative_path.parent
            if not plugin_dir.exists():
                continue
            stem = relative_path.stem
            for child in (
                plugin_dir / f"{stem}.dll",
                plugin_dir / f"lib{stem}.so",
                plugin_dir / f"lib{stem}.dylib",
                plugin_dir / f"{stem}.dylib",
            ):
                if not child.exists():
                    continue
                try:
                    child.unlink(missing_ok=True)
                    print(f"[SPEC] pruned optional Qt plugin: {child.relative_to(dist_root)}")
                except Exception as exc:
                    print(f"[SPEC] prune optional Qt plugin skip {child}: {exc}")

    for qt_root in qt_roots:
        if not qt_root.exists():
            continue

        resources_dir = qt_root / "resources"
        if resources_dir.exists():
            removable_resources = (
                "qtwebengine_devtools_resources.pak",
            )
            for name in removable_resources:
                child = resources_dir / name
                if child.exists():
                    try:
                        child.unlink(missing_ok=True)
                        print(f"[SPEC] pruned Qt WebEngine resource: {child.relative_to(dist_root)}")
                    except Exception as exc:
                        print(f"[SPEC] prune Qt WebEngine resource skip {child}: {exc}")
            for pattern in ("*.debug.pak", "*.debug.bin"):
                for child in resources_dir.glob(pattern):
                    try:
                        child.unlink(missing_ok=True)
                        print(f"[SPEC] pruned Qt WebEngine debug resource: {child.relative_to(dist_root)}")
                    except Exception as exc:
                        print(f"[SPEC] prune Qt WebEngine debug resource skip {child}: {exc}")

        qml_dir = qt_root / "qml"
        if qml_dir.exists():
            shutil.rmtree(qml_dir, ignore_errors=True)
            print(f"[SPEC] pruned Qt QML modules: {qml_dir.relative_to(dist_root)}")

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
                    print(f"[SPEC] pruned Qt translation: {child.relative_to(dist_root)}")
                except Exception as exc:
                    print(f"[SPEC] prune Qt translation skip {child}: {exc}")

        locales_dir = qt_root / "translations" / "qtwebengine_locales"
        if locales_dir.exists():
            keep_locales = {"en-US.pak", "zh-CN.pak"}
            for child in locales_dir.glob("*.pak"):
                if child.name in keep_locales:
                    continue
                try:
                    child.unlink(missing_ok=True)
                    print(f"[SPEC] pruned Qt WebEngine locale: {child.relative_to(dist_root)}")
                except Exception as exc:
                    print(f"[SPEC] prune Qt WebEngine locale skip {child}: {exc}")

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
                if not child.exists():
                    continue
                try:
                    child.unlink(missing_ok=True)
                    print(f"[SPEC] pruned optional Qt binary: {child.relative_to(dist_root)}")
                except Exception as exc:
                    print(f"[SPEC] prune optional Qt binary skip {child}: {exc}")
            _remove_optional_qt_libraries(qt_root, {Path(name).stem for name in removable_bins})

        plugins_dir = qt_root / "plugins"
        removable_plugins = {
            Path("generic/qtuiotouchplugin.dll"),
            Path("imageformats/qicns.dll"),
            Path("imageformats/qpdf.dll"),
            Path("imageformats/qtga.dll"),
            Path("imageformats/qwbmp.dll"),
            Path("platforms/qminimal.dll"),
            Path("platforms/qoffscreen.dll"),
            Path("position/qtposition_nmea.dll"),
            Path("position/qtposition_positionpoll.dll"),
            Path("position/qtposition_winrt.dll"),
        }
        for relative_path in removable_plugins:
            child = plugins_dir / relative_path
            if not child.exists():
                continue
            try:
                child.unlink(missing_ok=True)
                print(f"[SPEC] pruned optional Qt plugin: {child.relative_to(dist_root)}")
            except Exception as exc:
                print(f"[SPEC] prune optional Qt plugin skip {child}: {exc}")
        _remove_optional_qt_plugins(plugins_dir, removable_plugins)


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


def _prune_bundled_python_runtime(dist_root: Path):
    """Trim the embedded dependency Python to the pieces needed for pip/runtime."""
    py_root = dist_root / "deps" / "python311"
    if not py_root.exists():
        return

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
    for relative in remove_relatives:
        target = py_root / relative
        if not target.exists():
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
            print(f"[SPEC] pruned bundled Python runtime artifact: {target.relative_to(dist_root)}")
        except Exception as exc:
            print(f"[SPEC] prune bundled Python runtime artifact skip {target}: {exc}")

    lib_root = py_root / "Lib"
    if lib_root.exists():
        for cache_dir in lib_root.rglob("__pycache__"):
            shutil.rmtree(cache_dir, ignore_errors=True)


def _resolve_bundled_deps_root() -> Path:
    if BUNDLED_DEPS_DIR_ENV:
        return Path(BUNDLED_DEPS_DIR_ENV).expanduser()
    return ROOT


# Bundle dependency runtime.
BUNDLED_DEPS_ROOT = _resolve_bundled_deps_root()
BUNDLED_PY311 = BUNDLED_DEPS_ROOT / "python311"
if BUNDLED_PY311.exists():
    extra_datas += _collect_tree_as_datas(BUNDLED_PY311, "deps/python311")
    print(f"[SPEC] include bundled python311: {BUNDLED_PY311}")
else:
    print(f"[SPEC] bundled python311 not found, skip: {BUNDLED_PY311}")

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
        "editor.workbench_bridge",
        "editor.workbench_window",
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
        "handwriting.pdf_view_fitz",
        "handwriting.pdf_view_poppler",
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

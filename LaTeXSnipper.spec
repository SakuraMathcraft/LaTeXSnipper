"""Freeze only locked third-party modules and the stable business-code host."""

import json
import sys
from pathlib import Path

import PyQt6
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT / "scripts"))
from qt_payload import prune_qt_payload

sys.setrecursionlimit(max(5000, sys.getrecursionlimit() * 5))
system = {"win32": "windows", "linux": "linux", "darwin": "macos"}[sys.platform]
contract = json.loads((ROOT / "packaging/runtime/gui-imports.json").read_text(encoding="utf-8"))
hidden = contract["modules"] + contract[system]
for package in contract["packages"]:
    hidden += collect_submodules(package, filter=lambda name: not {"test", "tests"}.intersection(name.split(".")))
# Include the standard library so new business imports do not require a new host.
excluded = ["tkinter", "_tkinter", "turtle", "turtledemo", "idlelib", "ensurepip", "venv",
            "test", "tests", "Pythonwin", "win32ui", "setuptools", "pkg_resources", "distutils"]
excluded += [name for name in sys.stdlib_module_names if name.startswith("_test") or name.endswith("_test")]
hidden += sorted(sys.stdlib_module_names - set(excluded))
for package in ("asyncio", "collections", "concurrent", "ctypes", "email", "encodings", "html", "http",
                "importlib", "json", "logging", "multiprocessing", "sqlite3", "urllib", "xml", "xmlrpc", "zoneinfo", "wsgiref"):
    hidden += collect_submodules(package)
if system == "linux":
    from linux_hotkey_packaging import collect_linux_hotkey_modules
    hidden += collect_linux_hotkey_modules(collect_submodules)

datas = collect_data_files("certifi")
qt = Path(PyQt6.__file__).resolve().parent / "Qt6"
for source, destination in ((qt / "resources", "PyQt6/Qt6/resources"),
                            (qt / "translations/qtwebengine_locales", "PyQt6/Qt6/translations/qtwebengine_locales")):
    if source.exists():
        datas.append((str(source), destination))
if system == "macos":
    helpers = qt / "lib/QtWebEngineCore.framework/Helpers"
    if helpers.exists():
        datas.append((str(helpers), "PyQt6/Qt6/lib/QtWebEngineCore.framework/Helpers"))
binaries = []
if system == "windows":
    for directory in map(Path, sys.path):
        for pattern in ("pythoncom*.dll", "pywintypes*.dll"):
            binaries += [(str(path), "pywin32_system32") for path in (directory / "pywin32_system32").glob(pattern)]
a = Analysis([str(ROOT / "packaging/runtime/gui_entry.py")],
             pathex=[], binaries=binaries, datas=datas, hiddenimports=hidden,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=excluded + ["numpy", "onnxruntime", "cv2", "torch", "transformers", "rapidocr",
                                  "scipy", "pandas", "matplotlib", "tensorflow", "keras", "onnx", "pytest"],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LaTeXSnipper",
          debug=False, strip=False, upx=False, console=False,
          codesign_identity=None, entitlements_file=None,
          icon=str(ROOT / "src/assets/icon.ico") if system == "windows" else None)
COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LaTeXSnipper")
prune_qt_payload(Path(DISTPATH) / "LaTeXSnipper/_internal")

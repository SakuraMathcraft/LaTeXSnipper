"""Native runtime environment defaults and isolated dependency-process startup."""

from __future__ import annotations

import os
import sys


def configure_native_runtime_environment() -> None:
    """Set conservative native-library defaults before GUI or OCR imports."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
    os.environ.setdefault("ORT_NO_AZURE_EP", "1")
    os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    os.environ.setdefault("ORT_DISABLE_AZURE", "1")


def isolated_python_code(code: str) -> str:
    """Reset inherited Windows DLL search state inside the child, before native imports.

    Never change the GUI process's SetDllDirectory state. Keep dependency Python
    and user CUDA paths, but remove the frozen GUI's root and Qt paths.
    """
    if sys.platform != "win32":
        return code
    bundle = getattr(sys, "_MEIPASS", None)
    bundle_root = os.path.normcase(os.path.abspath(bundle)) if bundle else ""
    qt_roots = (
        [os.path.join(bundle_root, name) for name in ("pyqt6", "qt6")]
        if bundle_root else []
    )
    return (
        "import ctypes, os\n"
        "_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "_set_dll_directory = _kernel32.SetDllDirectoryW\n"
        "_set_dll_directory.argtypes = [ctypes.c_wchar_p]\n"
        "_set_dll_directory.restype = ctypes.c_int\n"
        "if not _set_dll_directory(None):\n"
        "    raise ctypes.WinError(ctypes.get_last_error())\n"
        f"_gui_root = {bundle_root!r}\n"
        f"_qt_roots = {qt_roots!r}\n"
        "_paths = []\n"
        "for _entry in os.environ.get('PATH', '').split(os.pathsep):\n"
        "    _key = os.path.normcase(os.path.abspath(_entry.strip().strip(chr(34))))\n"
        "    if _gui_root and (_key == _gui_root or any(\n"
        "        _key == _root or _key.startswith(_root + os.sep) for _root in _qt_roots\n"
        "    )):\n"
        "        continue\n"
        "    _paths.append(_entry)\n"
        "os.environ['PATH'] = os.pathsep.join(_paths)\n"
        + code
    )

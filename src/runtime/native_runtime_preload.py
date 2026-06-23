"""Process-wide native runtime preloads that must run before Qt creates an app."""

from __future__ import annotations

import importlib
import importlib.util
import os

_ONNXRUNTIME_PRELOADED = False


def configure_native_runtime_environment() -> None:
    """Set conservative native-library defaults before GUI or OCR imports."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
    os.environ.setdefault("ORT_NO_AZURE_EP", "1")
    os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    os.environ.setdefault("ORT_DISABLE_AZURE", "1")


def preload_onnxruntime_before_qt() -> bool:
    """
    Preload onnxruntime before QApplication/QGuiApplication is created.

    On Windows, Qt's GUI initialization can load native libraries in an order
    that makes a later onnxruntime-gpu import fail inside its extension module.
    Importing onnxruntime first keeps both Qt and ONNX Runtime usable in the
    same process. Missing or broken optional MathCraft dependencies are handled
    later by the dependency wizard, so this preloader never raises.
    """
    global _ONNXRUNTIME_PRELOADED
    if _ONNXRUNTIME_PRELOADED:
        return True

    configure_native_runtime_environment()
    try:
        if importlib.util.find_spec("onnxruntime") is None:
            return False
        importlib.import_module("onnxruntime")
    except Exception:
        return False

    _ONNXRUNTIME_PRELOADED = True
    return True

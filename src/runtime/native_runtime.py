"""Native runtime environment defaults."""

from __future__ import annotations

import os


def configure_native_runtime_environment() -> None:
    """Set conservative native-library defaults before GUI or OCR imports."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
    os.environ.setdefault("ORT_NO_AZURE_EP", "1")
    os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    os.environ.setdefault("ORT_DISABLE_AZURE", "1")

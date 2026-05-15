"""Earliest runtime guards used before importing the main GUI stack."""

from __future__ import annotations

import datetime
import faulthandler
import os
import pathlib

from runtime.linux_graphics_runtime import apply_linux_graphics_fallbacks
from runtime.startup_gui_deps import early_ensure_pyqt6_and_pywin32

_CRASH_FH = None


def pre_bootstrap_runtime() -> None:
    """Apply process-wide safeguards before the heavier startup modules load."""
    global _CRASH_FH

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
    os.environ.setdefault("ORT_NO_AZURE_EP", "1")

    apply_linux_graphics_fallbacks()
    early_ensure_pyqt6_and_pywin32()

    log_dir = pathlib.Path.home() / ".latexsnipper" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash-native.log"

    try:
        _CRASH_FH = open(crash_log, "a", encoding="utf-8", buffering=1)
        _CRASH_FH.write(f"\n=== LaTeXSnipper start {datetime.datetime.now().isoformat()} ===\n")
        faulthandler.enable(all_threads=True, file=_CRASH_FH)
    except Exception:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

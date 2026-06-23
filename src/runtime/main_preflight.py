"""Earliest runtime guards used before importing the main GUI stack."""

from __future__ import annotations

import datetime
import faulthandler
import os

from runtime.linux_graphics_runtime import apply_linux_graphics_fallbacks
from runtime.app_paths import app_log_dir
from runtime.native_runtime_preload import (
    configure_native_runtime_environment,
    preload_onnxruntime_before_qt,
)
from runtime.startup_gui_deps import early_ensure_pyqt6_and_pywin32

_CRASH_FH = None


def pre_bootstrap_runtime() -> None:
    """Apply process-wide safeguards before the heavier startup modules load."""
    global _CRASH_FH

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    configure_native_runtime_environment()

    apply_linux_graphics_fallbacks()
    early_ensure_pyqt6_and_pywin32()
    preload_onnxruntime_before_qt()

    log_dir = app_log_dir()
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

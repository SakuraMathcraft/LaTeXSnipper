"""Earliest runtime guards used before importing the main GUI stack."""

from __future__ import annotations

import datetime
import faulthandler
import os

from runtime.linux_graphics_runtime import apply_linux_graphics_fallbacks
from runtime.app_paths import app_log_dir
from runtime.log_lifecycle import CRASH_LOG_BACKUP_COUNT, CRASH_LOG_MAX_BYTES, rotate_before_append
from runtime.native_runtime import configure_native_runtime_environment

_CRASH_FH = None


def pre_bootstrap_runtime() -> None:
    """Apply process-wide safeguards before the heavier startup modules load."""
    global _CRASH_FH

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    configure_native_runtime_environment()

    apply_linux_graphics_fallbacks()

    log_dir = app_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash-native.log"
    rotate_before_append(
        crash_log,
        max_bytes=CRASH_LOG_MAX_BYTES,
        backup_count=CRASH_LOG_BACKUP_COUNT,
    )

    try:
        _CRASH_FH = open(crash_log, "a", encoding="utf-8", buffering=1)
        _CRASH_FH.write(f"\n=== LaTeXSnipper start {datetime.datetime.now().isoformat()} ===\n")
        faulthandler.enable(all_threads=True, file=_CRASH_FH)
    except Exception:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

"""Bounded retention helpers for application-owned log files."""

from __future__ import annotations

import re
import time
from pathlib import Path


APP_LOG_MAX_BYTES = 2 * 1024 * 1024
APP_LOG_BACKUP_COUNT = 3
CRASH_LOG_MAX_BYTES = 2 * 1024 * 1024
CRASH_LOG_BACKUP_COUNT = 2
FALLBACK_LOG_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_FALLBACK_LOG_NAME = re.compile(r"app-\d+\.log(?:\.\d+)?$")


def rotate_before_append(path: Path, *, max_bytes: int, backup_count: int) -> bool:
    """Rotate a plain append-only file before opening it when it reached its limit."""
    if max_bytes <= 0 or backup_count <= 0:
        return False
    try:
        if not path.is_file() or path.stat().st_size < max_bytes:
            return False

        oldest = path.with_name(f"{path.name}.{backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(backup_count - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.is_file():
                source.replace(path.with_name(f"{path.name}.{index + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        return False


def cleanup_stale_fallback_logs(
    log_dir: Path,
    *,
    max_age_seconds: float = FALLBACK_LOG_MAX_AGE_SECONDS,
    now: float | None = None,
) -> int:
    """Remove expired per-process logs left by the app.log sharing fallback."""
    if max_age_seconds < 0:
        return 0
    cutoff = (time.time() if now is None else float(now)) - max_age_seconds
    removed = 0
    try:
        candidates = tuple(log_dir.iterdir())
    except OSError:
        return 0
    for path in candidates:
        if not path.is_file() or _FALLBACK_LOG_NAME.fullmatch(path.name) is None:
            continue
        try:
            if path.stat().st_mtime > cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed

"""Standard stream recovery helpers."""

from __future__ import annotations

import os
import sys

from runtime.runtime_logging import TeeWriter


def ensure_std_streams() -> None:
    """Restore stdout and stderr only when they are missing, closed, or unusable."""

    def _is_bad(stream) -> bool:
        if stream is None:
            return True
        if not hasattr(stream, "write"):
            return True
        if getattr(stream, "closed", False):
            return True
        if isinstance(stream, TeeWriter):
            return stream._closed
        return False

    if _is_bad(getattr(sys, "stdout", None)):
        if hasattr(sys, "__stdout__") and sys.__stdout__ is not None and not getattr(sys.__stdout__, "closed", False):
            sys.stdout = sys.__stdout__

    if _is_bad(getattr(sys, "stderr", None)):
        if hasattr(sys, "__stderr__") and sys.__stderr__ is not None and not getattr(sys.__stderr__, "closed", False):
            sys.stderr = sys.__stderr__

    if _is_bad(getattr(sys, "stdout", None)):
        try:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass

    if _is_bad(getattr(sys, "stderr", None)):
        if not _is_bad(getattr(sys, "stdout", None)):
            sys.stderr = sys.stdout
        else:
            try:
                sys.stderr = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                pass

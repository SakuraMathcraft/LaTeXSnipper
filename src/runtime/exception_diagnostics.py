"""Format local and child-process exceptions for persistent diagnostics."""

from __future__ import annotations

import traceback


def format_exception_diagnostics(exc: BaseException) -> str:
    detail = "".join(traceback.format_exception(exc)).rstrip()
    remote = str(getattr(exc, "remote_traceback", "") or "").strip()
    if remote:
        detail += f"\nOCR worker traceback:\n{remote}"
    return detail

"""GUI controller for the optional runtime log window."""

from __future__ import annotations

import json
import os
import sys

from PyQt6.QtWidgets import QApplication

from runtime.app_paths import app_config_path
from runtime.runtime_logging import runtime_log_path
from ui.runtime_log_dialog import RuntimeLogDialog

_RUNTIME_LOG_DIALOG: RuntimeLogDialog | None = None

def show_runtime_log_window(parent=None):
    global _RUNTIME_LOG_DIALOG
    app = QApplication.instance() or QApplication(sys.argv)
    log_path = runtime_log_path()
    if _RUNTIME_LOG_DIALOG is None:
        _RUNTIME_LOG_DIALOG = RuntimeLogDialog(log_path, parent=parent)
    try:
        _RUNTIME_LOG_DIALOG.show()
        _RUNTIME_LOG_DIALOG.raise_()
        _RUNTIME_LOG_DIALOG.activateWindow()
    except Exception:
        pass
    try:
        app.processEvents()
    except Exception:
        pass

    return _RUNTIME_LOG_DIALOG


def refresh_runtime_log_dialog_theme(force: bool = True) -> None:
    try:
        if _RUNTIME_LOG_DIALOG is not None and hasattr(_RUNTIME_LOG_DIALOG, "_apply_theme_styles"):
            _RUNTIME_LOG_DIALOG._apply_theme_styles(force=force)
    except Exception:
        pass


def apply_runtime_log_window_preference(force: bool = False):
    """Apply the preference for the scrollable GUI runtime-log window."""
    def _read_runtime_log_window_pref(default: bool = False) -> bool:
        try:
            cfg = app_config_path()
            if not cfg.exists():
                return default
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return default
            raw = data.get("show_runtime_log", default)
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            if isinstance(raw, str):
                return raw.strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            pass
        return default

    env_pref = os.environ.get("LATEXSNIPPER_SHOW_RUNTIME_LOG")
    if env_pref is not None:
        want = env_pref.strip().lower() in ("1", "true", "yes", "on")
    else:
        want = _read_runtime_log_window_pref(default=False)
    want = bool(force or want)
    os.environ["LATEXSNIPPER_SHOW_RUNTIME_LOG"] = "1" if want else "0"

    if not want:
        try:
            if _RUNTIME_LOG_DIALOG is not None:
                _RUNTIME_LOG_DIALOG.hide()
        except Exception:
            pass
        return

    show_runtime_log_window()

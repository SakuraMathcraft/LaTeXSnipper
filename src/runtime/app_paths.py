"""Application path helpers shared by runtime, logging, and packaging code."""

from __future__ import annotations

import os
import pathlib
import sys

CONFIG_FILENAME = "LaTeXSnipper_config.json"
APP_STATE_DIRNAME = ".latexsnipper"

_APP_LOG_DIR_CACHE: pathlib.Path | None = None


def resource_path(relative_path):
    """Return an absolute resource path for source and PyInstaller modes."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def app_state_dir() -> pathlib.Path:
    p = pathlib.Path.home() / APP_STATE_DIRNAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def app_log_dir() -> pathlib.Path:
    """Return a writable log directory, falling back when the profile log dir is locked."""
    global _APP_LOG_DIR_CACHE
    if _APP_LOG_DIR_CACHE is not None:
        return _APP_LOG_DIR_CACHE

    import tempfile

    candidates = [
        app_state_dir() / "logs",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(pathlib.Path(local_app_data) / "LaTeXSnipper" / "logs")
    candidates.append(pathlib.Path(tempfile.gettempdir()) / "LaTeXSnipper" / "logs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write-test-{os.getpid()}.tmp"
            probe.write_text("ok", encoding="utf-8")
            try:
                probe.unlink()
            except Exception:
                pass
            _APP_LOG_DIR_CACHE = candidate
            return candidate
        except Exception:
            continue

    fallback = pathlib.Path(tempfile.gettempdir())
    _APP_LOG_DIR_CACHE = fallback
    return fallback


def app_config_path() -> pathlib.Path:
    return app_state_dir() / CONFIG_FILENAME


def get_app_root() -> pathlib.Path:
    """Return the PyInstaller internal root or the source directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent


def is_packaged_mode() -> bool:
    if hasattr(sys, "_MEIPASS"):
        return True
    return "_internal" in str(get_app_root()).lower()

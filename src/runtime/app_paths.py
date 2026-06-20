"""Application path helpers shared by runtime, logging, and packaging code."""

from __future__ import annotations

import os
import pathlib
import sys

CONFIG_FILENAME = "LaTeXSnipper_config.json"
APP_STATE_DIRNAME = ".latexsnipper"
APP_NAME = "LaTeXSnipper"

_APP_LOG_DIR_CACHE: pathlib.Path | None = None
_APP_STATE_DIR_CACHE: pathlib.Path | None = None


def resource_path(relative_path):
    """Return an absolute resource path for source and PyInstaller modes."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return str(get_app_root() / relative_path)


def app_state_dir() -> pathlib.Path:
    global _APP_STATE_DIR_CACHE
    if _APP_STATE_DIR_CACHE is not None:
        return _APP_STATE_DIR_CACHE

    if sys.platform == "darwin":
        p = pathlib.Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        p = pathlib.Path.home() / APP_STATE_DIRNAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _APP_STATE_DIR_CACHE = p
    return p


def app_log_dir() -> pathlib.Path:
    """Return a writable log directory, falling back when the profile log dir is locked."""
    global _APP_LOG_DIR_CACHE
    if _APP_LOG_DIR_CACHE is not None:
        return _APP_LOG_DIR_CACHE

    import tempfile

    candidates = []
    if sys.platform == "darwin":
        candidates.append(pathlib.Path.home() / "Library" / "Logs" / APP_NAME)
    candidates.append(app_state_dir() / "logs")
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(pathlib.Path(local_app_data) / APP_NAME / "logs")
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


def app_temp_dir() -> pathlib.Path:
    import tempfile

    p = pathlib.Path(tempfile.gettempdir()) / APP_NAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def app_config_path() -> pathlib.Path:
    return app_state_dir() / CONFIG_FILENAME


def get_app_root() -> pathlib.Path:
    """Return the PyInstaller internal root or the source directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent.parent


def is_packaged_mode() -> bool:
    if hasattr(sys, "_MEIPASS"):
        return True
    return "_internal" in str(get_app_root()).lower()

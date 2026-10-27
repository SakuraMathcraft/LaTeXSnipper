"""Application path helpers shared by runtime, logging, and packaging code."""

from __future__ import annotations

import pathlib
import sys

CONFIG_FILENAME = "LaTeXSnipper_config.json"
APP_STATE_DIRNAME = ".latexsnipper"
APP_NAME = "LaTeXSnipper"
APP_DESKTOP_ID = "latexsnipper"
APP_SUPPORT_NAME = APP_NAME

_APP_LOG_DIR_CACHE: pathlib.Path | None = None
_APP_STATE_DIR_CACHE: pathlib.Path | None = None


def resource_path(relative_path):
    """Return an absolute resource path for source and PyInstaller modes."""
    if getattr(sys, "frozen", False) and pathlib.PurePosixPath(relative_path).parts[
        :2
    ] == ("assets", "MathJax"):
        from runtime.installed_resources import installed_resources

        resources = installed_resources()
        assert resources is not None
        return str(resources.directory("runtime") / relative_path)
    return str(get_app_root() / relative_path)


def app_state_dir() -> pathlib.Path:
    global _APP_STATE_DIR_CACHE
    if _APP_STATE_DIR_CACHE is not None:
        return _APP_STATE_DIR_CACHE

    if sys.platform == "darwin":
        p = pathlib.Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME
    else:
        p = pathlib.Path.home() / APP_STATE_DIRNAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    _APP_STATE_DIR_CACHE = p
    return p


def app_cache_dir() -> pathlib.Path:
    if sys.platform == "darwin":
        p = pathlib.Path.home() / "Library" / "Caches" / APP_SUPPORT_NAME
    else:
        p = app_state_dir() / "cache"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def app_log_dir() -> pathlib.Path:
    """Return the platform log directory."""
    global _APP_LOG_DIR_CACHE
    if _APP_LOG_DIR_CACHE is not None:
        return _APP_LOG_DIR_CACHE

    if sys.platform == "darwin":
        p = pathlib.Path.home() / "Library" / "Logs" / APP_SUPPORT_NAME
    else:
        p = app_state_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    _APP_LOG_DIR_CACHE = p
    return p


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
    """Return the installed business resource root or the source directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        from runtime.installed_resources import installation_root

        return installation_root(pathlib.Path(sys.executable)) / "application"
    return pathlib.Path(__file__).resolve().parent.parent


def is_packaged_mode() -> bool:
    if hasattr(sys, "_MEIPASS"):
        return True
    return "_internal" in str(get_app_root()).lower()

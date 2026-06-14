"""Application path helpers shared by runtime, logging, and packaging code."""

from __future__ import annotations

import os
import pathlib
import shutil
import sys

CONFIG_FILENAME = "LaTeXSnipper_config.json"
APP_STATE_DIRNAME = ".latexsnipper"

_APP_LOG_DIR_CACHE: pathlib.Path | None = None
_APP_LOG_DIR_CACHE_HOME: pathlib.Path | None = None


def _legacy_app_state_dir() -> pathlib.Path:
    return pathlib.Path.home() / APP_STATE_DIRNAME


def _macos_app_support_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Application Support" / "LaTeXSnipper"


def _macos_cache_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Caches" / "LaTeXSnipper"


def _macos_log_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Logs" / "LaTeXSnipper"


def _copy_if_missing(src: pathlib.Path, dest: pathlib.Path) -> None:
    if not src.is_file() or dest.exists():
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except Exception:
        pass


def _migrate_macos_small_state(state_dir: pathlib.Path) -> None:
    legacy = _legacy_app_state_dir()
    if not legacy.is_dir() or legacy == state_dir:
        return

    for name in ("history.json", "favorites.json", "latex_settings.json"):
        _copy_if_missing(legacy / name, state_dir / name)

    legacy_config = legacy / CONFIG_FILENAME
    target_config = state_dir / CONFIG_FILENAME
    if not legacy_config.is_file() or target_config.exists():
        return
    try:
        import json

        data = json.loads(legacy_config.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            path_rewrites = {
                "history_path": "history.json",
                "favorites_path": "favorites.json",
            }
            for key, filename in path_rewrites.items():
                value = data.get(key)
                if isinstance(value, str) and pathlib.Path(value).expanduser() == legacy / filename:
                    data[key] = str(state_dir / filename)
            target_config.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return
    except Exception:
        pass
    _copy_if_missing(legacy_config, target_config)


def resource_path(relative_path):
    """Return an absolute resource path for source and PyInstaller modes."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return str(get_app_root() / relative_path)


def app_state_dir() -> pathlib.Path:
    if sys.platform == "darwin":
        p = _macos_app_support_dir()
    else:
        p = _legacy_app_state_dir()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if sys.platform == "darwin":
        _migrate_macos_small_state(p)
    return p


def app_cache_dir() -> pathlib.Path:
    if sys.platform == "darwin":
        p = _macos_cache_dir()
    else:
        p = app_state_dir() / "cache"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def app_log_dir() -> pathlib.Path:
    """Return a writable log directory, falling back when the profile log dir is locked."""
    global _APP_LOG_DIR_CACHE, _APP_LOG_DIR_CACHE_HOME
    home = pathlib.Path.home()
    if _APP_LOG_DIR_CACHE is not None and _APP_LOG_DIR_CACHE_HOME == home:
        return _APP_LOG_DIR_CACHE

    import tempfile

    candidates = [
        _macos_log_dir() if sys.platform == "darwin" else app_state_dir() / "logs",
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
            _APP_LOG_DIR_CACHE_HOME = home
            return candidate
        except Exception:
            continue

    fallback = pathlib.Path(tempfile.gettempdir())
    _APP_LOG_DIR_CACHE = fallback
    _APP_LOG_DIR_CACHE_HOME = home
    return fallback


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

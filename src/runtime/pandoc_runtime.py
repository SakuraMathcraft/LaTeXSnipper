"""Pandoc runtime path persistence."""

from __future__ import annotations

import json
from pathlib import Path

from runtime.app_paths import app_config_path

PANDOC_EXECUTABLE_CONFIG_KEY = "pandoc_executable_path"


def load_configured_pandoc_path() -> Path | None:
    """Return the configured pandoc executable path if it exists."""
    try:
        cfg_path = app_config_path()
        if not cfg_path.exists():
            return None
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        raw = str(data.get(PANDOC_EXECUTABLE_CONFIG_KEY, "") or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        if path.is_file():
            return path
    except Exception:
        return None
    return None


def save_configured_pandoc_path(path: str | Path) -> None:
    """Persist a validated pandoc executable path for future environments."""
    try:
        target = Path(path).expanduser()
        if not target.is_file():
            return
        cfg_path = app_config_path()
        data = {}
        if cfg_path.exists():
            try:
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        data[PANDOC_EXECUTABLE_CONFIG_KEY] = str(target.resolve())
        cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def clear_configured_pandoc_path() -> None:
    """Remove the persisted pandoc executable path."""
    try:
        cfg_path = app_config_path()
        if not cfg_path.exists():
            return
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return
        if PANDOC_EXECUTABLE_CONFIG_KEY not in loaded:
            return
        loaded.pop(PANDOC_EXECUTABLE_CONFIG_KEY, None)
        cfg_path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return

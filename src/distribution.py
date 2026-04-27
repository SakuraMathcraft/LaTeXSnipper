from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_VERSION = "v2.3.2"

CHANNEL_GITHUB = "github"
CHANNEL_STORE = "store"
_VALID_CHANNELS = {CHANNEL_GITHUB, CHANNEL_STORE}
_DEFAULT_CHANNEL = CHANNEL_GITHUB
_CHANNEL_FILE = "distribution_channel.json"


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
    except Exception:
        pass
    try:
        roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    try:
        roots.append(Path.cwd())
    except Exception:
        pass
    return roots


def _load_channel_file() -> dict[str, Any]:
    for root in _candidate_roots():
        path = root / _CHANNEL_FILE
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


def _normalize_channel(value: object) -> str:
    channel = str(value or "").strip().lower()
    return channel if channel in _VALID_CHANNELS else ""


_CHANNEL_CONFIG = _load_channel_file()


def distribution_channel() -> str:
    env_channel = _normalize_channel(os.environ.get("LATEXSNIPPER_DISTRIBUTION_CHANNEL"))
    if env_channel:
        return env_channel
    file_channel = _normalize_channel(_CHANNEL_CONFIG.get("channel"))
    return file_channel or _DEFAULT_CHANNEL


def is_store_distribution() -> bool:
    return distribution_channel() == CHANNEL_STORE


def store_product_id() -> str:
    env_value = str(os.environ.get("LATEXSNIPPER_STORE_PRODUCT_ID", "") or "").strip()
    if env_value:
        return env_value
    return str(_CHANNEL_CONFIG.get("store_product_id", "") or "").strip()


def store_update_uri() -> str:
    product_id = store_product_id()
    if product_id:
        return f"ms-windows-store://pdp/?productid={product_id}"
    return "ms-windows-store://downloadsandupdates"

"""User-configurable global hotkey policy."""

from __future__ import annotations

DEFAULT_HOTKEY = "Ctrl+F"
HOTKEY_HELP_TEXT = "Ctrl+字母 或 Ctrl+Shift+字母"


def normalize_hotkey(value: str | None) -> str | None:
    """Return a canonical supported hotkey, or None when unsupported."""
    if not value:
        return None
    parts = [part.strip().upper() for part in str(value).split("+") if part.strip()]
    if len(parts) not in {2, 3}:
        return None

    key_parts = [part for part in parts if part not in {"CTRL", "CONTROL", "SHIFT"}]
    if len(key_parts) != 1:
        return None
    key = key_parts[0]
    if len(key) != 1 or not ("A" <= key <= "Z"):
        return None

    has_ctrl = any(part in {"CTRL", "CONTROL"} for part in parts)
    has_shift = "SHIFT" in parts
    allowed_parts = {"CTRL", "CONTROL", "SHIFT", key}
    if not has_ctrl or any(part not in allowed_parts for part in parts):
        return None
    if len(set(parts)) != len(parts):
        return None

    return f"Ctrl+Shift+{key}" if has_shift else f"Ctrl+{key}"


def normalize_hotkey_or_default(value: str | None) -> str:
    """Return a supported hotkey, falling back to the default."""
    return normalize_hotkey(value) or DEFAULT_HOTKEY


def is_supported_hotkey(value: str | None) -> bool:
    """Return whether value is allowed by the user-facing hotkey policy."""
    return normalize_hotkey(value) is not None

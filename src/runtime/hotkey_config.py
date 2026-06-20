"""User-configurable global hotkey policy."""

from __future__ import annotations

import sys


def _is_macos(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def hotkey_modifier_label(platform: str | None = None) -> str:
    return "Command" if _is_macos(platform) else "Ctrl"


def default_hotkey(platform: str | None = None) -> str:
    return f"{hotkey_modifier_label(platform)}+F"


def hotkey_help_text(platform: str | None = None) -> str:
    modifier = hotkey_modifier_label(platform)
    return f"{modifier}+字母 或 {modifier}+Shift+字母"


DEFAULT_HOTKEY = default_hotkey()
HOTKEY_HELP_TEXT = hotkey_help_text()


def normalize_hotkey(value: str | None, platform: str | None = None) -> str | None:
    """Return a canonical supported hotkey, or None when unsupported."""
    if not value:
        return None
    parts = [part.strip().upper() for part in str(value).split("+") if part.strip()]
    if len(parts) not in {2, 3}:
        return None

    primary_modifiers = {"COMMAND", "CMD", "META"} if _is_macos(platform) else {"CTRL", "CONTROL"}
    key_parts = [part for part in parts if part not in {*primary_modifiers, "SHIFT"}]
    if len(key_parts) != 1:
        return None
    key = key_parts[0]
    if len(key) != 1 or not ("A" <= key <= "Z"):
        return None

    has_primary_modifier = any(part in primary_modifiers for part in parts)
    has_shift = "SHIFT" in parts
    allowed_parts = {*primary_modifiers, "SHIFT", key}
    if not has_primary_modifier or any(part not in allowed_parts for part in parts):
        return None
    if len(set(parts)) != len(parts):
        return None

    modifier = hotkey_modifier_label(platform)
    return f"{modifier}+Shift+{key}" if has_shift else f"{modifier}+{key}"


def normalize_hotkey_or_default(value: str | None, platform: str | None = None) -> str:
    """Return a supported hotkey, falling back to the default."""
    return normalize_hotkey(value, platform=platform) or default_hotkey(platform)


def is_supported_hotkey(value: str | None, platform: str | None = None) -> bool:
    """Return whether value is allowed by the user-facing hotkey policy."""
    return normalize_hotkey(value, platform=platform) is not None

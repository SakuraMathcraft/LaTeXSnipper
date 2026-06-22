"""User-configurable global hotkey policy."""

from __future__ import annotations

DEFAULT_HOTKEY = "Ctrl+F"
MACOS_DEFAULT_HOTKEY = "Meta+F"
HOTKEY_HELP_TEXT = "Ctrl+字母 或 Ctrl+Shift+字母"
MACOS_HOTKEY_HELP_TEXT = "Command+字母 或 Option+Command+字母"

_MACOS_RESERVED_COMMAND_KEYS = {"H", "M", "Q", "W"}
_MACOS_RESERVED_COMMAND_NON_LETTERS = {"SPACE", "TAB", "3", "4", "5"}
_MACOS_EDITING_COMMAND_KEYS = {"A", "C", "V", "X", "Z"}


def _platform_name(platform: str | None = None) -> str:
    if platform is None:
        return ""
    return str(platform or "").strip().lower()


def _is_macos(platform: str | None = None) -> bool:
    return _platform_name(platform) == "darwin"


def default_hotkey(platform: str | None = None) -> str:
    return MACOS_DEFAULT_HOTKEY if _is_macos(platform) else DEFAULT_HOTKEY


def hotkey_help_text(platform: str | None = None) -> str:
    return MACOS_HOTKEY_HELP_TEXT if _is_macos(platform) else HOTKEY_HELP_TEXT


def normalize_hotkey(value: str | None, platform: str | None = None) -> str | None:
    """Return a canonical supported hotkey, or None when unsupported."""
    if _is_macos(platform):
        return _normalize_macos_hotkey(value)
    return _normalize_ctrl_hotkey(value)


def _normalize_ctrl_hotkey(value: str | None) -> str | None:
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


def _normalize_macos_token(part: str) -> str:
    token = part.strip().upper()
    if token in {"CMD", "COMMAND", "META", "WIN"}:
        return "META"
    if token in {"ALT", "OPTION"}:
        return "ALT"
    if token == "SHIFT":
        return "SHIFT"
    if token in {"SPACE", "TAB"}:
        return token
    return token


def _normalize_macos_hotkey(value: str | None) -> str | None:
    if not value:
        return None
    parts = [_normalize_macos_token(part) for part in str(value).split("+") if part.strip()]
    if len(parts) not in {2, 3, 4}:
        return None
    if len(set(parts)) != len(parts):
        return None

    key_parts = [part for part in parts if part not in {"META", "ALT", "SHIFT"}]
    if len(key_parts) != 1:
        return None
    key = key_parts[0]

    has_command = "META" in parts
    has_option = "ALT" in parts
    has_shift = "SHIFT" in parts
    if not has_command:
        return None
    if key in _MACOS_RESERVED_COMMAND_KEYS or key in _MACOS_RESERVED_COMMAND_NON_LETTERS:
        return None
    if not has_option and key in _MACOS_EDITING_COMMAND_KEYS:
        return None
    if len(key) != 1 or not ("A" <= key <= "Z"):
        return None

    allowed_parts = {"META", "ALT", "SHIFT", key}
    if any(part not in allowed_parts for part in parts):
        return None
    modifiers = ["Meta"]
    if has_option:
        modifiers.append("Alt")
    if has_shift:
        modifiers.append("Shift")
    return "+".join([*modifiers, key])


def normalize_hotkey_or_default(value: str | None, platform: str | None = None) -> str:
    """Return a supported hotkey, falling back to the default."""
    return normalize_hotkey(value, platform) or default_hotkey(platform)


def is_supported_hotkey(value: str | None, platform: str | None = None) -> bool:
    """Return whether value is allowed by the user-facing hotkey policy."""
    return normalize_hotkey(value, platform) is not None


def display_hotkey(value: str | None, platform: str | None = None) -> str:
    """Return a user-facing hotkey label for the current platform."""
    normalized = normalize_hotkey_or_default(value, platform)
    if not _is_macos(platform):
        return normalized
    parts = [part.strip() for part in normalized.split("+") if part.strip()]
    key = parts[-1] if parts else ""
    labels = []
    if "Alt" in parts:
        labels.append("Option")
    if "Meta" in parts:
        labels.append("Command")
    if "Shift" in parts:
        labels.append("Shift")
    if key:
        labels.append(key)
    return "+".join(labels)

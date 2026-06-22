from runtime.hotkey_config import (
    DEFAULT_HOTKEY,
    default_hotkey,
    hotkey_help_text,
    is_supported_hotkey,
    normalize_hotkey,
    normalize_hotkey_or_default,
)


def _hotkey_dialog_source() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "src" / "ui" / "hotkey_dialog.py").read_text(encoding="utf-8")


def test_normalize_hotkey_accepts_ctrl_letter() -> None:
    assert normalize_hotkey("Ctrl+F") == "Ctrl+F"
    assert normalize_hotkey(" control + f ") == "Ctrl+F"


def test_normalize_hotkey_accepts_ctrl_shift_letter() -> None:
    assert normalize_hotkey("Ctrl+Shift+F") == "Ctrl+Shift+F"
    assert normalize_hotkey("Shift+Ctrl+f") == "Ctrl+Shift+F"


def test_normalize_hotkey_rejects_extra_modifiers_and_non_letters() -> None:
    assert normalize_hotkey("Ctrl+Alt+F") is None
    assert normalize_hotkey("Ctrl+1") is None
    assert normalize_hotkey("Ctrl+F1") is None
    assert normalize_hotkey("Shift+F") is None
    assert normalize_hotkey("Ctrl+Shift+Alt+F") is None


def test_normalize_hotkey_default() -> None:
    assert normalize_hotkey_or_default("Ctrl+Shift+A") == "Ctrl+Shift+A"
    assert normalize_hotkey_or_default("Alt+F") == DEFAULT_HOTKEY
    assert is_supported_hotkey("Ctrl+Shift+Z")
    assert not is_supported_hotkey("Meta+Z")


def test_macos_default_hotkey_uses_command_letter() -> None:
    assert default_hotkey("darwin") == "Meta+F"
    assert hotkey_help_text("darwin") == "Command/Option/Shift + 字母"
    assert normalize_hotkey_or_default("Ctrl+F", "darwin") == "Meta+F"


def test_macos_hotkey_accepts_command_letters_with_optional_modifiers() -> None:
    assert normalize_hotkey("Command+S", "darwin") == "Meta+S"
    assert normalize_hotkey("Command+Shift+L", "darwin") == "Meta+Shift+L"
    assert normalize_hotkey("command + option + l", "darwin") == "Meta+Alt+L"
    assert normalize_hotkey("Option+Command+C", "darwin") == "Meta+Alt+C"
    assert normalize_hotkey("Option+Command+Shift+L", "darwin") == "Meta+Alt+Shift+L"
    assert is_supported_hotkey("Meta+Alt+L", "darwin")


def test_macos_hotkey_rejects_system_and_editing_command_shortcuts() -> None:
    assert normalize_hotkey("Meta+C", "darwin") is None
    for shortcut in (
        "Command+Q",
        "Command+H",
        "Command+M",
        "Command+W",
        "Command+Space",
        "Command+Tab",
        "Shift+Command+4",
        "Command+A",
        "Command+C",
        "Command+V",
        "Command+X",
        "Command+Z",
    ):
        assert normalize_hotkey(shortcut, "darwin") is None


def test_macos_hotkey_dialog_does_not_require_option() -> None:
    dialog = _hotkey_dialog_source()

    assert "if has_command and not has_extra" in dialog
    assert 'modifiers.append("Shift")' in dialog

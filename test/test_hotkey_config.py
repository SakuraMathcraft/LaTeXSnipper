from runtime.hotkey_config import DEFAULT_HOTKEY, is_supported_hotkey, normalize_hotkey, normalize_hotkey_or_default


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

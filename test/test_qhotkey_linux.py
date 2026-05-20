from backend.qhotkey.qhotkey_linux import LinuxHotkey
from backend.qhotkey import _select_provider
from backend.qhotkey.qhotkey_macos import MacHotkey


def test_pynput_combo_uses_separate_modifier_brackets() -> None:
    mods, key = LinuxHotkey._parse("Ctrl+F")

    assert mods == {"ctrl"}
    assert key == "f"
    assert LinuxHotkey._pynput_combo(mods, key) == "<ctrl>+f"


def test_pynput_combo_supports_multiple_modifiers() -> None:
    mods, key = LinuxHotkey._parse("Ctrl+Shift+F")

    assert mods == {"ctrl", "shift"}
    assert key == "f"
    assert LinuxHotkey._pynput_combo(mods, key) == "<ctrl>+<shift>+f"


def test_macos_uses_native_provider_without_pynput_listener() -> None:
    provider, global_hotkey = _select_provider("darwin")

    assert provider.__name__ == "MacHotkey"
    assert provider.__module__ == "backend.qhotkey.qhotkey_macos"
    assert global_hotkey is None


def test_macos_hotkey_parses_ctrl_shift_letter() -> None:
    ctrl_mods, f_key = MacHotkey._parse("Ctrl+F")
    shifted_mods, z_key = MacHotkey._parse("Ctrl+Shift+Z")

    assert ctrl_mods == 0x1000
    assert f_key == 0x03
    assert shifted_mods == 0x1200
    assert z_key == 0x06

from backend.qhotkey.qhotkey_linux import LinuxHotkey


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

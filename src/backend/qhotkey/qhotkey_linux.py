"""Linux global hotkey provider using pynput.

Supports X11; Wayland global hotkeys are limited and may require
compositor-specific protocols. Falls back gracefully on failure.
"""

from __future__ import annotations

from typing import Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence


class LinuxHotkey(QObject):
    """Linux-compatible global hotkey using pynput.

    Provides the same interface as the Windows QHotkey class:
    - activated signal
    - setShortcut / register / unregister / is_registered / cleanup
    """

    activated = pyqtSignal()

    # Qt modifier → pynput key mapping
    _MOD_MAP = {
        Qt.KeyboardModifier.ControlModifier: "ctrl",
        Qt.KeyboardModifier.ShiftModifier: "shift",
        Qt.KeyboardModifier.AltModifier: "alt",
        Qt.KeyboardModifier.MetaModifier: "cmd",  # Super/Win key
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq_obj: Optional[QKeySequence] = None
        self._seq_str: Optional[str] = None
        self._registered = False
        self._listener = None
        self._pynput_available = False
        try:
            from pynput import keyboard as _pynput_keyboard  # type: ignore[reportMissingModuleSource]
            self._pynput_keyboard = _pynput_keyboard
            self._pynput_available = True
        except ImportError:
            self._pynput_keyboard = None

    def setShortcut(self, seq: QKeySequence) -> None:
        self._seq_obj = seq
        self._seq_str = self._qkeysequence_to_string(seq)

    @staticmethod
    def _qkeysequence_to_string(seq: QKeySequence) -> str:
        kc = seq[0]
        mods = kc.keyboardModifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        key = kc.key()
        if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
            parts.append(chr(ord("A") + (key - Qt.Key.Key_A.value)))
        elif Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
            parts.append(chr(ord("0") + (key - Qt.Key.Key_0.value)))
        elif Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F12.value:
            parts.append(f"F{key - Qt.Key.Key_F1.value + 1}")
        else:
            raise ValueError(f"Unsupported key: {key}")
        return "+".join(parts)

    @staticmethod
    def _parse(keyseq_str: str) -> tuple[set[str], str]:
        """Parse "Ctrl+Shift+F" → ({'ctrl','shift'}, 'f')."""
        ks = keyseq_str.upper().replace(" ", "")
        parts = ks.split("+")
        mods = set()
        key_part = None
        for p in parts:
            if p == "CTRL":
                mods.add("ctrl")
            elif p == "SHIFT":
                mods.add("shift")
            elif p == "ALT":
                mods.add("alt")
            elif p in ("WIN", "CMD", "META"):
                mods.add("cmd")
            else:
                key_part = p
        if not key_part or not mods:
            raise ValueError(f"Invalid hotkey: {keyseq_str}")
        return mods, key_part.lower()

    def register(self, seq: Union[QKeySequence, str, None] = None) -> None:
        if seq is not None:
            if isinstance(seq, str):
                seq = QKeySequence(seq)
            self.setShortcut(seq)
        if not self._seq_str:
            raise RuntimeError("No shortcut set")

        self.unregister()

        if not self._pynput_available:
            print("[Hotkey] pynput not available, global hotkey disabled")
            return

        mods, key = self._parse(self._seq_str)
        combo = "<" + "+".join(sorted(mods)) + "+" + key + ">"

        try:
            def on_activate():
                self.activated.emit()

            self._listener = self._pynput_keyboard.GlobalHotKeys(
                {combo: on_activate}
            )
            self._listener.start()
            self._registered = True
            print(f"[Hotkey] registered combo={combo} (pynput)")
        except Exception as e:
            print(f"[Hotkey] pynput registration failed: {e}")
            self._listener = None

    def unregister(self) -> None:
        self._registered = False
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as e:
                print(f"[Hotkey] pynput stop error: {e}")
            self._listener = None

    def is_registered(self) -> bool:
        return self._registered and self._listener is not None

    def cleanup(self) -> None:
        self.unregister()

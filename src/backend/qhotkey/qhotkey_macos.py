"""macOS hotkey provider.

The pynput listener used on Linux can destabilize packaged macOS builds when
started during GUI initialization. Keep the same provider interface, but do not
start a global keyboard listener on macOS.
"""

from __future__ import annotations

from typing import Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QKeySequence


class MacHotkey(QObject):
    """No-op global hotkey provider for macOS packaged builds."""

    activated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq_obj: Optional[QKeySequence] = None
        self._seq_str: Optional[str] = None

    def setShortcut(self, seq: QKeySequence) -> None:
        self._seq_obj = seq
        self._seq_str = seq.toString(QKeySequence.SequenceFormat.NativeText)

    def register(self, seq: Union[QKeySequence, str, None] = None) -> None:
        if seq is not None:
            if isinstance(seq, str):
                seq = QKeySequence(seq)
            self.setShortcut(seq)
        if not self._seq_str:
            raise RuntimeError("No shortcut set")
        print("[Hotkey] macOS global hotkey disabled")

    def unregister(self) -> None:
        return

    def is_registered(self) -> bool:
        return False

    def cleanup(self) -> None:
        self.unregister()

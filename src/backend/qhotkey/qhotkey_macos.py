"""macOS global hotkey provider using Carbon Event Manager."""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Any, Optional, Union

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence

_EVENT_CLASS_KEYBOARD = 0x6B657962  # b"keyb"
_EVENT_HOTKEY_PRESSED = 5
_EVENT_PARAM_DIRECT_OBJECT = 0x2D2D2D2D  # b"----"
_EVENT_PARAM_HOTKEY_ID = 0x686B6964  # b"hkid"
_HOTKEY_SIGNATURE = 0x4C545350  # b"LTSP"
_NO_ERR = 0

_CMD_KEY = 0x0100
_SHIFT_KEY = 0x0200
_OPTION_KEY = 0x0800
_CONTROL_KEY = 0x1000

_LETTER_KEYCODES = {
    "A": 0x00,
    "S": 0x01,
    "D": 0x02,
    "F": 0x03,
    "H": 0x04,
    "G": 0x05,
    "Z": 0x06,
    "X": 0x07,
    "C": 0x08,
    "V": 0x09,
    "B": 0x0B,
    "Q": 0x0C,
    "W": 0x0D,
    "E": 0x0E,
    "R": 0x0F,
    "Y": 0x10,
    "T": 0x11,
    "O": 0x1F,
    "U": 0x20,
    "I": 0x22,
    "P": 0x23,
    "L": 0x25,
    "J": 0x26,
    "K": 0x28,
    "N": 0x2D,
    "M": 0x2E,
}


class EventHotKeyID(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


class EventTypeSpec(ctypes.Structure):
    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


EventHandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


def _load_carbon() -> Any:
    path = ctypes.util.find_library("Carbon")
    if not path:
        raise RuntimeError("Carbon framework is not available")
    carbon = ctypes.CDLL(path)

    carbon.GetApplicationEventTarget.restype = ctypes.c_void_p

    carbon.InstallEventHandler.argtypes = [
        ctypes.c_void_p,
        EventHandlerProc,
        ctypes.c_uint32,
        ctypes.POINTER(EventTypeSpec),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    carbon.InstallEventHandler.restype = ctypes.c_int

    carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]
    carbon.RemoveEventHandler.restype = ctypes.c_int

    carbon.RegisterEventHotKey.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        EventHotKeyID,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    carbon.RegisterEventHotKey.restype = ctypes.c_int

    carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
    carbon.UnregisterEventHotKey.restype = ctypes.c_int

    carbon.GetEventParameter.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    carbon.GetEventParameter.restype = ctypes.c_int
    return carbon


class MacHotkey(QObject):
    """macOS-compatible global hotkey provider.

    Uses Carbon directly through ctypes. This avoids the pynput listener thread
    that can destabilize packaged macOS GUI startup.
    """

    activated = pyqtSignal()
    _next_id = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq_obj: Optional[QKeySequence] = None
        self._seq_str: Optional[str] = None
        self._carbon: Any | None = None
        self._handler_proc: Any | None = None
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_ref = ctypes.c_void_p()
        self._hotkey_id: int | None = None
        self._registered = False

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
            parts.append("Meta")
        key = kc.key()
        if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
            parts.append(chr(ord("A") + (key - Qt.Key.Key_A.value)))
        else:
            raise ValueError(f"Unsupported macOS hotkey key: {key}")
        return "+".join(parts)

    @staticmethod
    def _parse(keyseq_str: str) -> tuple[int, int]:
        ks = keyseq_str.upper().replace(" ", "")
        parts = ks.split("+")
        modifiers = 0
        key_part = None
        for part in parts:
            if part == "CTRL":
                modifiers |= _CONTROL_KEY
            elif part == "SHIFT":
                modifiers |= _SHIFT_KEY
            elif part == "ALT":
                modifiers |= _OPTION_KEY
            elif part in ("META", "CMD", "COMMAND", "WIN"):
                modifiers |= _CMD_KEY
            else:
                key_part = part
        if not key_part or not modifiers:
            raise ValueError(f"Invalid macOS hotkey: {keyseq_str}")
        key_code = _LETTER_KEYCODES.get(key_part)
        if key_code is None:
            raise ValueError(f"Unsupported macOS hotkey key: {key_part}")
        return modifiers, key_code

    @staticmethod
    def _qt_sequence_text(keyseq_str: str) -> str:
        parts = []
        for part in str(keyseq_str or "").split("+"):
            token = part.strip()
            if token.upper() in {"COMMAND", "CMD"}:
                parts.append("Meta")
            else:
                parts.append(token)
        return "+".join(part for part in parts if part)

    def _ensure_handler(self) -> None:
        if self._handler_ref.value:
            return
        carbon = self._carbon or _load_carbon()
        self._carbon = carbon

        def on_event(_next_handler, event, _user_data):
            hotkey_id = EventHotKeyID()
            status = carbon.GetEventParameter(
                event,
                _EVENT_PARAM_DIRECT_OBJECT,
                _EVENT_PARAM_HOTKEY_ID,
                None,
                ctypes.sizeof(hotkey_id),
                None,
                ctypes.byref(hotkey_id),
            )
            if (
                status == _NO_ERR
                and hotkey_id.signature == _HOTKEY_SIGNATURE
                and hotkey_id.id == self._hotkey_id
            ):
                QTimer.singleShot(0, self.activated.emit)
            return _NO_ERR

        event_spec = EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
        self._handler_proc = EventHandlerProc(on_event)
        handler_ref = ctypes.c_void_p()
        status = carbon.InstallEventHandler(
            carbon.GetApplicationEventTarget(),
            self._handler_proc,
            1,
            ctypes.byref(event_spec),
            None,
            ctypes.byref(handler_ref),
        )
        if status != _NO_ERR:
            self._handler_proc = None
            raise RuntimeError(f"macOS hotkey event handler install failed: {status}")
        self._handler_ref = handler_ref

    def register(self, seq: Union[QKeySequence, str, None] = None) -> None:
        if seq is not None:
            if isinstance(seq, str):
                seq = QKeySequence(self._qt_sequence_text(seq))
            self.setShortcut(seq)
        if not self._seq_str:
            raise RuntimeError("No shortcut set")
        self.unregister()
        modifiers, key_code = self._parse(self._seq_str)
        self._ensure_handler()
        carbon = self._carbon
        if carbon is None:
            raise RuntimeError("Carbon hotkey backend is not initialized")

        hotkey_id = MacHotkey._next_id
        MacHotkey._next_id += 1
        hotkey_ref = ctypes.c_void_p()
        status = carbon.RegisterEventHotKey(
            key_code,
            modifiers,
            EventHotKeyID(_HOTKEY_SIGNATURE, hotkey_id),
            carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(hotkey_ref),
        )
        if status != _NO_ERR:
            raise RuntimeError(f"macOS global hotkey registration failed: {status}")
        self._hotkey_id = hotkey_id
        self._hotkey_ref = hotkey_ref
        self._registered = True
        print(f"[Hotkey] registered id={self._hotkey_id} seq={self._seq_str} (macOS)")

    def unregister(self) -> None:
        if self._registered and self._hotkey_ref.value and self._carbon is not None:
            try:
                self._carbon.UnregisterEventHotKey(self._hotkey_ref)
                print(f"[Hotkey] unregistered id={self._hotkey_id} (macOS)")
            except Exception as exc:
                print(f"[Hotkey] macOS unregister error: {exc}")
        self._registered = False
        self._hotkey_ref = ctypes.c_void_p()
        self._hotkey_id = None

    def is_registered(self) -> bool:
        return self._registered and bool(self._hotkey_ref.value)

    def cleanup(self) -> None:
        self.unregister()
        if self._handler_ref.value and self._carbon is not None:
            try:
                self._carbon.RemoveEventHandler(self._handler_ref)
            except Exception as exc:
                print(f"[Hotkey] macOS handler cleanup error: {exc}")
        self._handler_ref = ctypes.c_void_p()
        self._handler_proc = None

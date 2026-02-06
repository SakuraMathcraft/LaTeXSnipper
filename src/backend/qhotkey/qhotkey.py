
import ctypes
import ctypes.wintypes
from typing import Optional, Union
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QAbstractNativeEventFilter, QAbstractEventDispatcher
from PyQt6.QtGui import QKeySequence

user32 = ctypes.windll.user32

MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
MOD_WIN     = 0x0008
WM_HOTKEY   = 0x0312


class WinHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner_getter):
        super().__init__()
        self._owner_getter = owner_getter  # lambda: GlobalHotkey

    def nativeEventFilter(self, eventType, message):
        if eventType != b"windows_generic_MSG":
            return False, 0
        try:
            try:
                addr = int(message)
            except Exception:
                return False, 0
            msg = ctypes.wintypes.MSG.from_address(addr)
            if msg.message == WM_HOTKEY:
                owner = self._owner_getter()
                if owner and owner._id is not None and msg.wParam == owner._id:
                    owner.activated.emit()
                    return True, 0
        except Exception as e:
            print("[Hotkey] nativeEventFilter error:", e)
        return False, 0


class GlobalHotkey(QObject):
    activated = pyqtSignal()
    _next_id = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id = None
        self._registered = False
        self._seq = None
        self._filter = WinHotkeyFilter(lambda: self)
        self._filter_installed = False

    def is_registered(self):
        return self._registered

    def _install_filter(self):
        if not self._filter_installed:
            disp = QAbstractEventDispatcher.instance()
            if disp:
                disp.installNativeEventFilter(self._filter)
                self._filter_installed = True

    def _remove_filter(self):
        if self._filter_installed:
            disp = QAbstractEventDispatcher.instance()
            if disp:
                try:
                    disp.removeNativeEventFilter(self._filter)
                except Exception:
                    pass
            self._filter_installed = False

    def _parse(self, keyseq_str: str):
        ks = keyseq_str.upper().replace(" ", "")
        parts = ks.split("+")
        mods = 0
        key_part = None
        for p in parts:
            if p == "CTRL":
                mods |= MOD_CONTROL
            elif p == "SHIFT":
                mods |= MOD_SHIFT
            elif p == "ALT":
                mods |= MOD_ALT
            elif p == "WIN":
                mods |= MOD_WIN
            else:
                key_part = p
        if not key_part or not mods:
            raise ValueError("快捷键格式不合法")
        if len(key_part) == 1 and 'A' <= key_part <= 'Z':
            vk = ord(key_part)
        elif len(key_part) == 1 and '0' <= key_part <= '9':
            vk = ord(key_part)
        elif key_part.startswith("F") and key_part[1:].isdigit():
            n = int(key_part[1:])
            if 1 <= n <= 12:
                vk = 0x70 + (n - 1)
            else:
                raise ValueError("不支持的功能键")
        else:
            raise ValueError("不支持的按键")
        return mods, vk

    def register(self, keyseq_str: str):
        self.unregister()
        mods, vk = self._parse(keyseq_str)
        hotkey_id = GlobalHotkey._next_id
        GlobalHotkey._next_id += 1
        if not user32.RegisterHotKey(None, hotkey_id, mods, vk):
            raise RuntimeError("注册全局热键失败")
        self._id = hotkey_id
        self._seq = keyseq_str
        self._registered = True
        self._install_filter()
        print(f"[Hotkey] registered id={self._id} seq={keyseq_str}")

    def unregister(self):
        if self._registered and self._id is not None:
            try:
                user32.UnregisterHotKey(None, self._id)
                print(f"[Hotkey] unregistered id={self._id}")
            except Exception as e:
                print("[Hotkey] unregister error:", e)
        self._registered = False
        self._id = None
        self._seq = None

    def cleanup(self):
        self.unregister()
        self._remove_filter()


class QHotkey(QObject):
    activated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq_obj: Optional[QKeySequence] = None
        self._seq_str: Optional[str] = None
        self._global = GlobalHotkey(self)
        self._global.activated.connect(self.activated.emit)

    def setShortcut(self, seq: QKeySequence):
        self._seq_obj = seq
        self._seq_str = self._qkeysequence_to_string(seq)

    def _qkeysequence_to_string(self, seq: QKeySequence) -> str:
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
            parts.append(chr(ord('A') + (key - Qt.Key.Key_A.value)))
        elif Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
            parts.append(chr(ord('0') + (key - Qt.Key.Key_0.value)))
        elif Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F12.value:
            parts.append(f"F{key - Qt.Key.Key_F1.value + 1}")
        else:
            raise ValueError("不支持的按键")
        return "+".join(parts)

    def register(self, seq: Union[QKeySequence, str, None] = None):
        if seq is not None:
            if isinstance(seq, str):
                seq = QKeySequence(seq)
            self.setShortcut(seq)
        if not self._seq_str:
            raise RuntimeError("未设置快捷键")
        self._global.register(self._seq_str)

    def unregister(self):
        self._global.unregister()

    def is_registered(self):
        return self._global.is_registered()

    def cleanup(self):
        self._global.cleanup()

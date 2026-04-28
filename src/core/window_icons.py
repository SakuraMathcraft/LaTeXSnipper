from __future__ import annotations

import ctypes
import os
from pathlib import Path


_NATIVE_ICON_HANDLES: list[int] = []


def apply_app_window_icon(win, icon_path: str | os.PathLike[str] | None) -> None:
    """Apply the app icon to a Qt window and the QApplication default icon."""
    if not icon_path:
        return
    path = Path(icon_path)
    if not path.exists():
        return
    try:
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication

        icon = QIcon(str(path))
        app = QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)
        if win is not None:
            win.setWindowIcon(icon)
    except Exception:
        pass


def schedule_native_dialog_icon(title: str, icon_path: str | os.PathLike[str] | None, attempts: int = 40):
    """Repeatedly apply the app icon to a native Windows dialog while it opens."""
    if os.name != "nt" or not icon_path:
        return None
    path = Path(icon_path)
    if not path.exists():
        return None
    try:
        from PyQt6.QtCore import QTimer
    except Exception:
        return None

    state = {"remaining": max(1, int(attempts))}
    timer = QTimer()
    timer.setInterval(50)

    def tick() -> None:
        _apply_native_dialog_icon(title, path)
        state["remaining"] -= 1
        if state["remaining"] <= 0:
            timer.stop()

    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(0, tick)
    return timer


def _apply_native_dialog_icon(title: str, icon_path: Path) -> None:
    hwnds = _find_current_process_windows(title)
    if not hwnds:
        return

    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    wm_seticon = 0x0080
    icon_small = 0
    icon_big = 1
    h_small = _load_icon(icon_path, user32.GetSystemMetrics(49), user32.GetSystemMetrics(50))
    h_big = _load_icon(icon_path, user32.GetSystemMetrics(11), user32.GetSystemMetrics(12))
    if not h_small and not h_big:
        return

    for hwnd in hwnds:
        if h_big:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, h_big)
        if h_small:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, h_small)


def _load_icon(icon_path: Path, width: int, height: int) -> int:
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    image_icon = 1
    lr_loadfromfile = 0x0010
    handle = user32.LoadImageW(
        0,
        str(icon_path),
        image_icon,
        int(width),
        int(height),
        lr_loadfromfile,
    )
    if handle:
        _NATIVE_ICON_HANDLES.append(int(handle))
    return int(handle or 0)


def _find_current_process_windows(title: str) -> list[int]:
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcessId.argtypes = []
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    current_pid = kernel32.GetCurrentProcessId()
    found: list[int] = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != current_pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if buffer.value == title:
            found.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    return found

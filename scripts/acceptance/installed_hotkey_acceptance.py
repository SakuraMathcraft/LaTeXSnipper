"""Check the installed application's native shortcut provider before updating."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time

from PyQt6.QtCore import QEventLoop, QTimer

from runtime.processes import independent_process_environment


def wait_for(predicate, timeout: float = 30) -> None:
    loop = QEventLoop()
    poll = QTimer()
    deadline = time.monotonic() + timeout
    poll.timeout.connect(
        lambda: loop.quit() if predicate() or time.monotonic() >= deadline else None
    )
    poll.start(10)
    if not predicate():
        loop.exec()
    poll.stop()
    if not predicate():
        raise TimeoutError("Native shortcut operation did not complete")


def activate_windows_shortcut() -> None:
    from ctypes import wintypes

    class KeyInput(ctypes.Structure):
        _fields_ = [
            ("vk", wintypes.WORD),
            ("scan", wintypes.WORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra", ctypes.c_size_t),
        ]

    class MouseInput(ctypes.Structure):
        _fields_ = [
            ("x", wintypes.LONG),
            ("y", wintypes.LONG),
            ("data", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("extra", ctypes.c_size_t),
        ]

    class InputValue(ctypes.Union):
        _fields_ = [("key", KeyInput), ("mouse", MouseInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("value", InputValue)]

    keys = (0x11, 0x10, 0x77)  # Ctrl+Shift+F8
    events = (Input * 6)(
        *(
            Input(1, InputValue(key=KeyInput(key, 0, flags, 0, 0)))
            for flags, sequence in ((0, keys), (2, reversed(keys)))
            for key in sequence
        )
    )
    send = ctypes.windll.user32.SendInput
    send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    send.restype = wintypes.UINT
    if send(len(events), events, ctypes.sizeof(Input)) != len(events):
        raise OSError("Windows rejected native shortcut input")


def activate_x11_shortcut() -> None:
    from Xlib import XK, X, display  # pyright: ignore[reportMissingModuleSource]
    from Xlib.ext import xtest  # pyright: ignore[reportMissingModuleSource]

    connection = display.Display()
    try:
        keys = [
            connection.keysym_to_keycode(XK.string_to_keysym(key))
            for key in ("Control_L", "Shift_L", "F8")
        ]
        for event, sequence in ((X.KeyPress, keys), (X.KeyRelease, reversed(keys))):
            for key in sequence:
                xtest.fake_input(connection, event, key)
        connection.sync()
    finally:
        connection.close()


def activate_wayland_shortcut() -> None:
    def call(path, method, *arguments):
        return subprocess.check_output(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.kde.kglobalaccel",
                "--object-path",
                path,
                "--method",
                method,
                *arguments,
            ],
            encoding="utf-8",
            timeout=10,
            env=independent_process_environment(),
        )

    components = call("/kglobalaccel", "org.kde.KGlobalAccel.allComponents")
    for path in re.findall(r"'(/[^']+)'", components):
        names = call(path, "org.kde.kglobalaccel.Component.shortcutNames")
        if "capture" in re.findall(r"'([^']+)'", names):
            call(path, "org.kde.kglobalaccel.Component.invokeShortcut", "capture")
            return
    raise RuntimeError("The Wayland desktop did not register the capture shortcut")


def validate_hotkeys(window) -> dict:
    provider = window.hotkey.hotkey_provider
    wait_for(provider.is_registered)
    provider.activated.disconnect(window.hotkey.on_hotkey_triggered)
    results, activations = [], []

    def registered(ok, error):
        results.append((ok, error))

    def activated():
        activations.append(True)

    provider.registration_finished.connect(registered)
    provider.activated.connect(activated)

    def register(shortcut):
        count = len(results)
        provider.register(shortcut)
        wait_for(lambda: len(results) > count)
        if not results[-1][0] or not provider.is_registered():
            raise RuntimeError(f"Installed shortcut registration failed: {results[-1]}")

    shortcuts = (
        ("Meta+Alt+Shift+K", "Meta+Alt+Shift+L")
        if sys.platform == "darwin"
        else ("Ctrl+Shift+F8", "Ctrl+Shift+F9")
    )
    try:
        register(shortcuts[0])
        register(shortcuts[1])
        provider.cleanup()
        if provider.is_registered():
            raise RuntimeError(
                "Installed shortcut cleanup did not unregister the shortcut"
            )
        register(shortcuts[0])
        activation = "not-injected-on-macos"
        if sys.platform != "darwin":
            if sys.platform == "win32":
                activate_windows_shortcut()
                activation = "SendInput"
            elif os.environ.get("XDG_SESSION_TYPE") == "wayland":
                activate_wayland_shortcut()
                activation = "KGlobalAccel-to-portal"
            else:
                activate_x11_shortcut()
                activation = "XTest"
            wait_for(lambda: bool(activations))
        return {
            "registered": True,
            "replaced": True,
            "unregistered": True,
            "activation": activation,
            "activation_received": bool(activations),
        }
    finally:
        provider.cleanup()
        provider.registration_finished.disconnect(registered)
        provider.activated.disconnect(activated)
        provider.activated.connect(window.hotkey.on_hotkey_triggered)
        provider.register(
            window.cfg.get("hotkey", "Meta+F" if sys.platform == "darwin" else "Ctrl+F")
        )
        wait_for(provider.is_registered)

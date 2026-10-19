"""Desktop integration checks, with native input enabled only by explicit opt-in."""

from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from localization.manager import install_application_translators, translate
from platform_services.linux_provider import LinuxSystemProvider
from platform_services.macos_provider import MacOSSystemProvider
from platform_services.protocols import TrayMenuHandlers
from platform_services.registry import PlatformCapabilityRegistry
from platform_services.windows_provider import WindowsSystemProvider
from ui.controllers import app_lifecycle

native_only = pytest.mark.skipif(
    os.environ.get("LATEXSNIPPER_PLATFORM_VALIDATION") != "1",
    reason="Native desktop checks require LATEXSNIPPER_PLATFORM_VALIDATION=1",
)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication(["LaTeXSnipper-platform-tests"])


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), "Desktop event did not arrive before the timeout"


@pytest.mark.parametrize("capture_active", [False, True])
def test_macos_close_dock_activation_and_quit(app, monkeypatch, capture_active):
    monkeypatch.setattr(app_lifecycle, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(app_lifecycle, "cleanup_runtime_log_session", lambda: None)
    monkeypatch.setattr(app_lifecycle, "_release_single_instance_lock", lambda: None)
    events = []
    view = QWidget()
    controller = app_lifecycle.AppLifecycleController(
        view,
        SimpleNamespace(_capture_start_pending=capture_active, overlay=None),
        None,
        SimpleNamespace(),
        SimpleNamespace(tray_icon=None),
        SimpleNamespace(show_window=lambda: (view.show(), events.append("show"))),
        (lambda: events.append("shutdown"),),
    )
    try:
        view.show()
        QTest.qWait(10)
        controller.install_platform_lifecycle_hooks()
        controller.closeEvent(QCloseEvent())
        assert not view.isVisible() and not controller._shutdown_done
        QApplication.sendEvent(app, QEvent(QEvent.Type.ApplicationActivate))
        QTest.qWait(20)
        assert events == ([] if capture_active else ["show"])
        controller.eventFilter(app, QEvent(QEvent.Type.Quit))
        assert controller._force_exit and events[-1] == "shutdown"
        controller._reactivate_from_dock()
        assert events[-1] == "shutdown"
    finally:
        controller.shutdown()
        view.close()
        view.deleteLater()


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
@pytest.mark.parametrize(
    "provider_type", [WindowsSystemProvider, LinuxSystemProvider, MacOSSystemProvider]
)
def test_status_menu_translations_and_actions(app, language, provider_type):
    events = []
    menu = QMenu()
    tray = SimpleNamespace(
        contextMenu=lambda: menu,
        setContextMenu=lambda value: setattr(tray, "menu", value),
        menu=menu,
    )
    callbacks = {
        "打开主窗口": lambda: events.append("open"),
        "截图识别（{hotkey}）": lambda: events.append("capture"),
        "设置...": lambda: events.append("settings"),
        "退出": lambda: events.append("quit"),
    }
    try:
        install_application_translators(app, language)
        provider_type().update_tray_menu(
            tray,
            "Ctrl+F",
            TrayMenuHandlers(
                on_open=callbacks["打开主窗口"],
                on_capture=callbacks["截图识别（{hotkey}）"],
                on_preferences=callbacks["设置..."],
                on_exit=callbacks["退出"],
            ),
        )
        actions = {action.text(): action for action in tray.menu.actions()}
        for source in callbacks:
            actions[translate(source).format(hotkey="Ctrl+F")].trigger()
        assert events == ["open", "capture", "settings", "quit"]
    finally:
        install_application_translators(app, "zh_CN")
        if tray.menu is not menu:
            tray.menu.deleteLater()
        menu.deleteLater()


@native_only
def test_native_hotkey_registration_replacement_and_cleanup(app):
    provider = PlatformCapabilityRegistry().create().hotkey
    failures = []
    provider.registration_finished.connect(
        lambda ok, error: failures.append(error) if not ok else None
    )
    shortcuts = (
        ("Meta+Alt+Shift+K", "Meta+Alt+Shift+L")
        if sys.platform == "darwin"
        else ("Ctrl+Shift+F8", "Ctrl+Shift+F9")
    )
    try:
        for shortcut in shortcuts:
            provider.register(shortcut)
            wait_for(lambda: provider.is_registered() or bool(failures))
            assert not failures, failures
            assert provider.is_registered()
        provider.cleanup()
        assert not provider.is_registered()
        provider.register(shortcuts[0])
        wait_for(lambda: provider.is_registered() or bool(failures))
        assert not failures, failures
        assert provider.is_registered()
    finally:
        provider.cleanup()


@native_only
@pytest.mark.skipif(
    sys.platform == "darwin",
    reason="Injected macOS input requires separate system permission; verify interactively",
)
def test_native_global_shortcut_receives_system_input(app):
    provider = PlatformCapabilityRegistry().create().hotkey
    activations = []
    provider.activated.connect(lambda: activations.append(True))
    try:
        provider.register("Ctrl+Shift+F8")
        wait_for(provider.is_registered)
        if sys.platform == "win32":
            import ctypes
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

            keys = (0x11, 0x10, 0x77)
            data = (Input * 6)(
                *(
                    Input(1, InputValue(key=KeyInput(key, 0, flags, 0, 0)))
                    for flags, sequence in ((0, keys), (2, reversed(keys)))
                    for key in sequence
                )
            )
            send = ctypes.windll.user32.SendInput
            send.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
            send.restype = wintypes.UINT
            assert send(len(data), data, ctypes.sizeof(Input)) == len(data)
        else:
            from Xlib import XK, X, display
            from Xlib.ext import xtest

            connection = display.Display()
            keys = [
                connection.keysym_to_keycode(XK.string_to_keysym(key))
                for key in ("Control_L", "Shift_L", "F8")
            ]
            try:
                for event, sequence in (
                    (X.KeyPress, keys),
                    (X.KeyRelease, reversed(keys)),
                ):
                    for key in sequence:
                        xtest.fake_input(connection, event, key)
                connection.sync()
            finally:
                connection.close()
        wait_for(lambda: bool(activations))
    finally:
        provider.cleanup()


@native_only
def test_native_status_icon_and_window_restore(app):
    provider = PlatformCapabilityRegistry().create().system
    view = QWidget()
    icon = app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon)
    tray = provider.create_tray(icon if not icon.isNull() else QIcon(), view)
    try:
        provider.activate_window(view)
        wait_for(view.isVisible)
        view.hide()
        provider.activate_window(view)
        wait_for(view.isVisible)
        assert not view.windowState() & Qt.WindowState.WindowMinimized
        assert tray.isVisible()
    finally:
        tray.hide()
        tray.deleteLater()
        view.close()
        view.deleteLater()

"""Check that a backgrounded macOS build stays in the menu bar during capture."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCloseEvent, QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget

from capture import overlay as overlay_module
from localization.manager import translate as tr
from platform_services import macos_provider
from ui.controllers import app_lifecycle
from ui.controllers.capture import CaptureController


@pytest.fixture
def app():
    return QApplication.instance() or QApplication(["LaTeXSnipper-background-tests"])


def build_capture_controller(view) -> CaptureController:
    return CaptureController(
        view,
        file_input=SimpleNamespace(eventFilter=lambda obj, event: False),
        models=SimpleNamespace(model=object()),
        recognition=SimpleNamespace(),
        screenshot_provider=SimpleNamespace(),
        system_provider=SimpleNamespace(),
        tasks=SimpleNamespace(is_busy=lambda source=None: False),
        display_mode=lambda: "auto",
        display_index=lambda: 0,
        tray_icon=lambda: None,
        can_capture=lambda: True,
    )


def build_lifecycle(view, capture, shown):
    return app_lifecycle.AppLifecycleController(
        view,
        capture,
        None,
        SimpleNamespace(),
        SimpleNamespace(tray_icon=None),
        SimpleNamespace(show_window=lambda: shown.append("show")),
        (),
    )


def test_capture_is_active_while_pending_or_overlay_is_open(app):
    view = QWidget()
    controller = build_capture_controller(view)
    try:
        assert controller.is_capturing() is False

        controller._capture_start_pending = True
        assert controller.is_capturing() is True

        controller._capture_start_pending = False
        controller.overlay = QWidget()
        assert controller.is_capturing() is True
    finally:
        view.deleteLater()


@pytest.mark.parametrize("cancelled", [False, True], ids=["rejected", "cancelled"])
def test_dock_activation_after_capture_ends(app, monkeypatch, cancelled):
    monkeypatch.setattr(app_lifecycle, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(app_lifecycle, "cleanup_runtime_log_session", lambda: None)
    monkeypatch.setattr(app_lifecycle, "_release_single_instance_lock", lambda: None)
    view = QWidget()
    capture = build_capture_controller(view)
    shown = []
    lifecycle = build_lifecycle(view, capture, shown)
    try:
        if cancelled:
            capture.overlay = QWidget()
            capture.on_capture_done(None)
        else:
            capture.can_capture = lambda: False
            capture.start_capture()

        lifecycle.eventFilter(app, QEvent(QEvent.Type.ApplicationActivate))
        app.processEvents()
        assert shown == ["show"]
    finally:
        lifecycle.shutdown()
        view.deleteLater()


@pytest.mark.parametrize("tray_available", [True, False])
def test_escape_does_not_reopen_hidden_main_window(app, tray_available):
    view = QWidget()
    overlay = QWidget()
    capture = build_capture_controller(view)
    capture.overlay = overlay
    overlay.installEventFilter(capture)
    notifications = []
    tray = object() if tray_available else None
    capture.tray_icon = lambda: tray
    capture.system_provider = SimpleNamespace(
        activate_window=lambda window: window.show(),
        show_notification=lambda tray, title, text, **kwargs: notifications.append(
            (tray, title, text, kwargs)
        ),
    )
    try:
        overlay.show()
        QApplication.sendEvent(
            overlay,
            QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
            ),
        )
        app.processEvents()

        assert not capture.is_capturing()
        assert not overlay.isVisible()
        assert not view.isVisible()
        if tray_available:
            assert notifications == [
                (
                    tray,
                    tr("已取消截图"),
                    tr("未创建识别任务。"),
                    {"critical": False, "timeout_ms": 2400},
                )
            ]
        else:
            assert notifications == []
    finally:
        overlay.close()
        view.close()


@pytest.mark.parametrize("capture_active", [False, True])
def test_dock_activation_respects_capture_state(app, monkeypatch, capture_active):
    monkeypatch.setattr(app_lifecycle, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(app_lifecycle, "cleanup_runtime_log_session", lambda: None)
    monkeypatch.setattr(app_lifecycle, "_release_single_instance_lock", lambda: None)
    shown = []
    view = QWidget()
    capture = SimpleNamespace(is_capturing=lambda: capture_active)
    controller = build_lifecycle(view, capture, shown)
    try:
        controller._reactivate_from_dock()
        assert shown == ([] if capture_active else ["show"])
    finally:
        controller.shutdown()
        view.deleteLater()


@pytest.mark.parametrize(
    ("background", "expected"),
    [(True, ["show"]), (False, ["show", "raise"])],
)
def test_overlay_activation_never_calls_activate_window(
    monkeypatch, background, expected
):
    class FakeOverlay:
        def __init__(self):
            self.calls = []
            self.background = background

        def prepare_background_presentation(self):
            self.calls.append("prepare")
            return self.background

        def show(self):
            self.calls.append("show")

        def raise_(self):
            self.calls.append("raise")

        def activateWindow(self):
            self.calls.append("activate")

    monkeypatch.setattr(macos_provider, "ScreenCaptureOverlay", FakeOverlay)
    overlay = FakeOverlay()
    macos_provider.MacOSSystemProvider().activate_window(overlay)
    # raise_ maps to makeKeyAndOrderFront and would activate the application.
    assert overlay.calls == ["prepare", *expected]
    assert "activate" not in overlay.calls


def test_regular_window_activation_still_raises_foreground():
    class FakeWindow:
        def __init__(self):
            self.calls = []

        def isMinimized(self):
            return False

        def show(self):
            self.calls.append("show")

        def raise_(self):
            self.calls.append("raise")

        def activateWindow(self):
            self.calls.append("activate")

    window = FakeWindow()
    macos_provider.MacOSSystemProvider().activate_window(window)
    assert window.calls == ["show", "raise", "activate"]


def test_nonactivating_panel_is_skipped_off_macos(app, monkeypatch):
    monkeypatch.setattr(overlay_module, "sys", SimpleNamespace(platform="linux"))
    assert overlay_module.macos_make_nonactivating_panel(QWidget()) is False


def test_overlay_skips_activation_only_when_app_is_inactive(app, monkeypatch):
    overlay = overlay_module.ScreenCaptureOverlay.__new__(
        overlay_module.ScreenCaptureOverlay
    )
    state = {"value": overlay_module.Qt.ApplicationState.ApplicationInactive}
    monkeypatch.setattr(overlay_module, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(
        overlay_module,
        "QGuiApplication",
        SimpleNamespace(applicationState=lambda: state["value"]),
    )

    assert overlay._show_without_activation() is True

    state["value"] = overlay_module.Qt.ApplicationState.ApplicationActive
    assert overlay._show_without_activation() is False

    monkeypatch.setattr(overlay_module, "sys", SimpleNamespace(platform="win32"))
    state["value"] = overlay_module.Qt.ApplicationState.ApplicationInactive
    assert overlay._show_without_activation() is False


def test_macos_close_keeps_app_running_in_menu_bar(app, monkeypatch):
    monkeypatch.setattr(app_lifecycle, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(app_lifecycle, "cleanup_runtime_log_session", lambda: None)
    monkeypatch.setattr(app_lifecycle, "_release_single_instance_lock", lambda: None)
    notifications = []
    view = QWidget()
    tray = SimpleNamespace(
        tray_icon=SimpleNamespace(),
    )
    system_provider = SimpleNamespace(
        show_notification=lambda tray, title, text, **kwargs: notifications.append(text)
    )
    controller = app_lifecycle.AppLifecycleController(
        view,
        SimpleNamespace(is_capturing=lambda: False),
        None,
        system_provider,
        tray,
        SimpleNamespace(show_window=lambda: None),
        (),
    )
    try:
        view.show()
        assert view.isVisible()
        controller.closeEvent(QCloseEvent())
        assert not view.isVisible()
        assert controller._force_exit is False
        assert notifications
    finally:
        controller.shutdown()
        view.deleteLater()


def test_nonactivating_panel_ignores_non_cocoa_platform(app, monkeypatch):
    # The offscreen plugin returns a handle that is not an NSView; messaging it
    # with objc_msgSend would crash the process.
    monkeypatch.setattr(overlay_module, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(
        overlay_module,
        "QGuiApplication",
        SimpleNamespace(platformName=lambda: "offscreen"),
    )
    assert overlay_module.macos_make_nonactivating_panel(QWidget()) is False


@pytest.mark.skipif(sys.platform != "darwin", reason="native NSPanel behaviour")
def test_nonactivating_panel_stays_on_screen_while_app_is_inactive(app):
    """A panel that keeps the app inactive must not hide on deactivation.

    NSPanel hides whenever its application is inactive. The capture panel is
    shown without activating the application, so with the default it is never
    drawn: Qt and AppKit both report it visible while the screen shows nothing.
    """
    import ctypes
    import ctypes.util

    objc = ctypes.CDLL(ctypes.util.find_library("objc"))
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    send = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(address)
    send_bool = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(
        address
    )

    if app.platformName() != "cocoa":
        pytest.skip("needs the cocoa platform plugin for a native NSPanel")
    widget = QWidget()
    widget.setWindowFlags(overlay_module._capture_window_flags())
    try:
        assert overlay_module.macos_make_nonactivating_panel(widget) is True
        window = send(int(widget.winId()), objc.sel_registerName(b"window"))
        hides = send_bool(window, objc.sel_registerName(b"hidesOnDeactivate"))
        mask = send(window, objc.sel_registerName(b"styleMask"))
        assert hides is False
        assert int(mask or 0) & overlay_module._NS_WINDOW_STYLE_MASK_NONACTIVATING_PANEL
    finally:
        widget.deleteLater()


@pytest.mark.parametrize(
    ("other_kind", "expected"),
    [
        (None, ["show"]),
        ("dialog", []),
        ("hidden_dialog", ["show"]),
        ("popup", ["show"]),
    ],
)
def test_dock_activation_ignores_activation_from_own_windows(
    app, monkeypatch, other_kind, expected
):
    """Showing the result window activates the app; that must not reopen the main window."""
    monkeypatch.setattr(app_lifecycle, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(app_lifecycle, "cleanup_runtime_log_session", lambda: None)
    monkeypatch.setattr(app_lifecycle, "_release_single_instance_lock", lambda: None)
    from PyQt6.QtWidgets import QDialog

    shown = []
    view = QWidget()
    other = None
    if other_kind in {"dialog", "hidden_dialog"}:
        other = QDialog()
        if other_kind == "dialog":
            other.show()
    elif other_kind == "popup":
        other = QWidget(None, Qt.WindowType.Popup)
        other.show()
    capture = SimpleNamespace(is_capturing=lambda: False)
    controller = build_lifecycle(view, capture, shown)
    try:
        app.processEvents()
        controller._reactivate_from_dock()
        assert shown == expected
    finally:
        controller.shutdown()
        if other is not None:
            other.close()
            other.deleteLater()
        view.deleteLater()
        app.processEvents()

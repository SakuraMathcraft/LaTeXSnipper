"""Check platform menu translations and window lifecycle policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from localization.manager import install_application_translators, translate
from platform_services.linux_provider import LinuxSystemProvider
from platform_services.macos_provider import MacOSSystemProvider
from platform_services.protocols import TrayMenuHandlers
from platform_services.windows_provider import WindowsSystemProvider
from ui.controllers import app_lifecycle


@pytest.fixture
def app():
    return QApplication.instance() or QApplication(["LaTeXSnipper-platform-tests"])


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

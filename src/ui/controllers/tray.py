"""TrayController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from platform_services.protocols import ISystemProvider
    from runtime.config_manager import ConfigManager
    from ui.controllers.capture import CaptureController
    from ui.controllers.status import StatusController
    from ui.controllers.windows import WindowController
    from ui.main_window import MainWindow
import sys

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QSystemTrayIcon

from localization.manager import translate as tr
from platform_services import TrayMenuHandlers


class TrayController(QObject):
    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        capture: CaptureController,
        status: StatusController,
        system_provider: ISystemProvider,
        windows: WindowController,
        quit_application: Callable[[], None],
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.capture = capture
        self.status = status
        self.system_provider = system_provider
        self.windows = windows
        self.quit_application = quit_application
        self.tray_icon = system_provider.create_tray(view.icon, view)
        self._tray_activation_connected = False

    def connect_tray_activation(self):
        tray = getattr(self, "tray_icon", None)
        if (
            sys.platform == "darwin"
            or not tray
            or getattr(self, "_tray_activation_connected", False)
        ):
            return

        def _on_tray_activated(reason):
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                self.windows.show_window()

        tray.activated.connect(_on_tray_activated)
        self._tray_activation_connected = True

    def update_tray_tooltip(self):
        hk = self.view.hotkey.display_hotkey()
        mode = self.display_mode()
        if mode == "index":
            idx = self.display_index()
            disp = (
                tr("屏幕 {index}").format(index=idx + 1)
                if idx is not None
                else tr("指定屏幕")
            )
        else:
            disp = tr("自动选择屏幕")
        if getattr(self, "tray_icon", None):
            self.system_provider.set_tray_tooltip(
                self.tray_icon,
                tr("LaTeXSnipper - 截图识别快捷键: {hotkey} | {display}").format(
                    hotkey=hk, display=disp
                ),
            )

    def display_mode(self) -> str:
        mode = (
            str(self.cfg.get("capture_display_mode", "auto") or "auto").strip().lower()
        )
        return mode if mode in ("auto", "index") else "auto"

    def display_index(self) -> int | None:
        try:
            idx = int(self.cfg.get("capture_display_index", 0))
            return idx if idx >= 0 else 0
        except Exception:
            return 0

    def _set_capture_display_mode(self, mode: str, index: int | None = None):
        m = (mode or "auto").strip().lower()
        if m not in ("auto", "index"):
            m = "auto"
        self.cfg.set("capture_display_mode", m)
        if index is not None:
            try:
                self.cfg.set("capture_display_index", max(0, int(index)))
            except Exception:
                pass
        self.update_tray_tooltip()
        self.update_tray_menu()
        if m == "auto":
            self.status.set_action_status(tr("识别屏幕：自动选择"))
        else:
            idx = self.display_index() or 0
            self.status.set_action_status(
                tr("识别屏幕：屏幕 {index}").format(index=idx + 1)
            )

    def _build_capture_display_submenu(self, tray_menu):
        submenu = tray_menu.addMenu(tr("识别屏幕"))
        mode = self.display_mode()
        idx = self.display_index() or 0
        act_auto = submenu.addAction(tr("自动选择"))
        act_auto.setCheckable(True)
        act_auto.setChecked(mode == "auto")
        act_auto.triggered.connect(
            lambda _=False: self._set_capture_display_mode("auto")
        )
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            g = screen.geometry()
            title = tr("屏幕 {index}: {name} ({width}x{height} @ {x},{y})").format(
                index=i + 1,
                name=screen.name(),
                width=g.width(),
                height=g.height(),
                x=g.x(),
                y=g.y(),
            )
            act = submenu.addAction(title)
            act.setCheckable(True)
            act.setChecked(mode == "index" and idx == i)
            act.triggered.connect(
                lambda _=False, screen_idx=i: self._set_capture_display_mode(
                    "index", screen_idx
                )
            )

    def update_tray_menu(self):
        hk = self.view.hotkey.display_hotkey()
        handlers = TrayMenuHandlers(
            on_open=self.windows.show_window,
            on_capture=self.capture.start_capture,
            on_exit=self.quit_application,
            on_preferences=self.windows.open_settings,
            build_capture_submenu=self._build_capture_display_submenu,
        )
        self.system_provider.update_tray_menu(self.tray_icon, hk, handlers)

    def shutdown(self):
        if self.tray_icon is not None:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()

"""Tray menu and capture display selection mixin."""

from __future__ import annotations

import sys

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QSystemTrayIcon

from localization.manager import translate as tr
from platform_services import TrayMenuHandlers
from runtime.hotkey_config import display_hotkey, normalize_hotkey_or_default


class TrayControllerMixin:
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
                self.show_window()

        tray.activated.connect(_on_tray_activated)
        self._tray_activation_connected = True

    def update_tray_tooltip(self):
        hk = display_hotkey(
            normalize_hotkey_or_default(self.cfg.get("hotkey", None), sys.platform),
            sys.platform,
        )
        mode = self._get_capture_display_mode()
        if mode == "index":
            idx = self._get_capture_display_index()
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
                    hotkey=hk,
                    display=disp,
                ),
            )

    def _get_capture_display_mode(self) -> str:
        mode = (
            str(self.cfg.get("capture_display_mode", "auto") or "auto").strip().lower()
        )
        return mode if mode in ("auto", "index") else "auto"

    def _get_capture_display_index(self) -> int | None:
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
            self.set_action_status(tr("识别屏幕：自动选择"))
        else:
            idx = self._get_capture_display_index() or 0
            self.set_action_status(tr("识别屏幕：屏幕 {index}").format(index=idx + 1))

    def _build_capture_display_submenu(self, tray_menu):
        submenu = tray_menu.addMenu(tr("识别屏幕"))
        mode = self._get_capture_display_mode()
        idx = self._get_capture_display_index() or 0

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
        hk = display_hotkey(
            normalize_hotkey_or_default(self.cfg.get("hotkey", None), sys.platform),
            sys.platform,
        )
        handlers = TrayMenuHandlers(
            on_open=self.show_window,
            on_capture=self.start_capture,
            on_exit=self.truly_exit,
            on_preferences=self.open_settings,
            build_capture_submenu=self._build_capture_display_submenu,
        )
        self.system_provider.update_tray_menu(self.tray_icon, hk, handlers)

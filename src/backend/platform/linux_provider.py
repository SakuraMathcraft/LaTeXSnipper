"""Linux platform providers for LaTeXSnipper.

Provides hotkey, screenshot, and system integration using Qt and pynput.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from backend.capture_overlay import ScreenCaptureOverlay
from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig
from backend.qhotkey import QHotkey


class LinuxHotkeyProvider(QObject):
    """Linux hotkey provider using pynput for global hotkeys."""

    def __init__(self, parent=None, global_enabled: bool = True):
        super().__init__(parent)
        self._global_enabled = bool(global_enabled)
        self._hotkey = QHotkey(parent=self) if self._global_enabled else None

    @property
    def activated(self):
        return self._hotkey.activated if self._hotkey else None

    def register(self, seq: str) -> None:
        if not self._hotkey:
            raise RuntimeError("global hotkey disabled")
        self._hotkey.setShortcut(QKeySequence(seq))
        self._hotkey.register()

    def is_registered(self) -> bool:
        if not self._hotkey:
            return False
        try:
            return bool(self._hotkey.is_registered())
        except Exception:
            return False

    def cleanup(self) -> None:
        try:
            if self._hotkey:
                self._hotkey.cleanup()
        except Exception:
            pass


class LinuxScreenshotProvider:
    """Linux screenshot provider reusing the Qt-based ScreenCaptureOverlay."""

    def request_permission(self) -> PermissionResult:
        # Linux does not require explicit screenshot permission on X11/Wayland
        return PermissionResult(PermissionState.ALLOWED, "linux-default-allowed")

    def create_overlay(self, cfg: ScreenshotConfig) -> ScreenCaptureOverlay:
        return ScreenCaptureOverlay(
            capture_display_mode=cfg.capture_display_mode,
            preferred_screen_index=cfg.preferred_screen_index,
        )


@dataclass
class TrayMenuHandlers:
    on_open: Callable[[], None]
    on_capture: Callable[[], None]
    on_exit: Callable[[], None]
    build_capture_submenu: Callable[[QMenu], None] | None = None


class LinuxSystemProvider:
    """Linux system integration provider using Qt's QSystemTrayIcon."""

    def create_tray(self, icon: QIcon, parent=None) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icon, parent)
        tray.setContextMenu(QMenu())
        tray.show()
        return tray

    def set_tray_tooltip(self, tray: QSystemTrayIcon, text: str) -> None:
        if tray:
            tray.setToolTip(text)

    def update_tray_menu(
        self, tray: QSystemTrayIcon, hotkey: str, handlers: TrayMenuHandlers
    ) -> None:
        if not tray:
            return
        tray_menu = QMenu()
        tray_menu.setObjectName("latexsnipperTrayMenu")
        tray_menu.setStyleSheet(
            "QMenu#latexsnipperTrayMenu{padding:4px;}"
            "QMenu#latexsnipperTrayMenu::item{padding:4px 18px 4px 8px;}"
            "QMenu#latexsnipperTrayMenu::item:selected{background-color:rgba(127,127,127,48);border-radius:4px;}"
            "QMenu#latexsnipperTrayMenu::item:pressed{background-color:rgba(127,127,127,64);border-radius:4px;}"
            "QMenu#latexsnipperTrayMenu::icon{width:0px;height:0px;margin:0px;padding:0px;}"
            "QMenu#latexsnipperTrayMenu::indicator{width:0px;height:0px;margin:0px;padding:0px;}"
        )
        tray_menu.addAction("打开主窗口", handlers.on_open)
        tray_menu.addAction(f"截图识别（{hotkey}）", handlers.on_capture)
        if callable(handlers.build_capture_submenu):
            handlers.build_capture_submenu(tray_menu)
        tray_menu.addAction("退出", handlers.on_exit)
        tray.setContextMenu(tray_menu)

    def show_notification(
        self,
        tray: QSystemTrayIcon,
        title: str,
        text: str,
        critical: bool = False,
        timeout_ms: int = 2500,
    ) -> None:
        if not tray:
            return
        icon = (
            QSystemTrayIcon.MessageIcon.Critical
            if critical
            else QSystemTrayIcon.MessageIcon.Information
        )
        tray.showMessage(title, text, icon, timeout_ms)

    def activate_window(self, window) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

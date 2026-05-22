"""macOS platform providers for LaTeXSnipper.

Provides hotkey, screenshot, and system integration using Qt and native macOS APIs.
"""

from __future__ import annotations

import ctypes

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from backend.capture_overlay import ScreenCaptureOverlay
from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig, TrayMenuHandlers
from backend.qhotkey import QHotkey


class MacOSHotkeyProvider(QObject):
    """macOS hotkey provider using a native global hotkey backend."""

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


class MacOSScreenshotProvider:
    """macOS screenshot provider using native screencapture CLI + Qt overlay."""

    def __init__(self):
        self._screen_capture_prompted = False

    def _preflight_screen_capture_access(self) -> bool | None:
        try:
            app_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            fn = app_services.CGPreflightScreenCaptureAccess
            fn.argtypes = []
            fn.restype = ctypes.c_bool
            return bool(fn())
        except Exception as exc:
            print(f"[WARN] macOS screen capture preflight unavailable: {exc}")
            return None

    def _request_screen_capture_access(self) -> bool | None:
        try:
            app_services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            fn = app_services.CGRequestScreenCaptureAccess
            fn.argtypes = []
            fn.restype = ctypes.c_bool
            return bool(fn())
        except Exception as exc:
            print(f"[WARN] macOS screen capture request unavailable: {exc}")
            return None

    def request_permission(self) -> PermissionResult:
        # macOS persists Screen Recording permission by bundle id. Preflight it
        # before Qt/screencapture touches the screen so the native prompt is not
        # triggered repeatedly by fallback capture attempts.
        allowed = self._preflight_screen_capture_access()
        if allowed is True:
            return PermissionResult(PermissionState.ALLOWED, "macos-screen-recording-allowed")
        if allowed is None:
            return PermissionResult(PermissionState.UNKNOWN, "macos-screen-recording-unknown")

        if not self._screen_capture_prompted:
            self._screen_capture_prompted = True
            requested = self._request_screen_capture_access()
            if requested is True or self._preflight_screen_capture_access() is True:
                return PermissionResult(PermissionState.ALLOWED, "macos-screen-recording-allowed")

        return PermissionResult(
            PermissionState.UNKNOWN,
            "请在系统设置 > 隐私与安全性 > 录屏中允许 LaTeXSnipper。授权后如仍无法截图，请重启应用。",
        )

    def create_overlay(self, cfg: ScreenshotConfig) -> ScreenCaptureOverlay:
        return ScreenCaptureOverlay(
            capture_display_mode=cfg.capture_display_mode,
            preferred_screen_index=cfg.preferred_screen_index,
            screenshot_tool=cfg.screenshot_tool,
        )


class MacOSSystemProvider:
    """macOS system integration provider using Qt's QSystemTrayIcon."""

    def create_tray(self, icon: QIcon, parent=None) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icon, parent)
        tray.setContextMenu(QMenu())
        tray.show()
        return tray

    def set_tray_tooltip(self, tray: QSystemTrayIcon, text: str) -> None:
        tray.setToolTip(text)

    def update_tray_menu(self, tray: QSystemTrayIcon, hotkey: str, handlers: TrayMenuHandlers) -> None:
        tray_menu = tray.contextMenu()
        if tray_menu is None:
            return
        tray_menu.clear()
        tray_menu.addAction(f"截图识别（{hotkey}）", handlers.on_capture)
        if callable(handlers.build_capture_submenu):
            handlers.build_capture_submenu(tray_menu)
        tray_menu.addSeparator()
        tray_menu.addAction("打开主窗口", handlers.on_open)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", handlers.on_exit)

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
        if hasattr(window, "isMinimized") and window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()

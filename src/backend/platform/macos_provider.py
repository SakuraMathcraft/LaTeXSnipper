"""macOS platform providers for LaTeXSnipper.

Provides hotkey, screenshot, and system integration using Qt and native macOS APIs.
"""

from __future__ import annotations

import ctypes
import ctypes.util

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from backend.capture_overlay import ScreenCaptureOverlay
from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig, TrayMenuHandlers
from backend.qhotkey import QHotkey


def _load_core_graphics():
    path = ctypes.util.find_library("CoreGraphics")
    if not path:
        return None
    try:
        return ctypes.CDLL(path)
    except Exception:
        return None


def _preflight_screen_capture_access() -> bool | None:
    core_graphics = _load_core_graphics()
    if core_graphics is None:
        return None
    try:
        fn = core_graphics.CGPreflightScreenCaptureAccess
    except AttributeError:
        return None
    fn.restype = ctypes.c_bool
    fn.argtypes = []
    try:
        return bool(fn())
    except Exception:
        return None


def _request_screen_capture_access() -> bool | None:
    core_graphics = _load_core_graphics()
    if core_graphics is None:
        return None
    try:
        fn = core_graphics.CGRequestScreenCaptureAccess
    except AttributeError:
        return None
    fn.restype = ctypes.c_bool
    fn.argtypes = []
    try:
        return bool(fn())
    except Exception:
        return None


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

    _DENIED_MESSAGE = (
        "LaTeXSnipper 需要屏幕录制权限才能截图识别。\n\n"
        "请在 macOS 系统设置 > 隐私与安全性 > 屏幕录制"
        "（或“屏幕与系统音频录制”）中允许 LaTeXSnipper，"
        "然后重新启动应用。"
    )

    def __init__(self):
        self._permission_request_attempted = False

    def request_permission(self) -> PermissionResult:
        # Preflight does not trigger the system prompt. The explicit request
        # below is only reached from a user-initiated screenshot action.
        allowed = _preflight_screen_capture_access()
        if allowed is True:
            return PermissionResult(PermissionState.ALLOWED, "macos-screen-capture-allowed")
        if allowed is None:
            return PermissionResult(PermissionState.ALLOWED, "macos-screen-capture-api-unavailable")

        if self._permission_request_attempted:
            return PermissionResult(PermissionState.DENIED, self._DENIED_MESSAGE)

        self._permission_request_attempted = True
        requested = _request_screen_capture_access()
        if requested is True:
            return PermissionResult(PermissionState.ALLOWED, "macos-screen-capture-request-granted")
        return PermissionResult(PermissionState.DENIED, self._DENIED_MESSAGE)

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
        window.show()
        try:
            window.showNormal()
        except Exception:
            pass
        window.raise_()
        window.activateWindow()

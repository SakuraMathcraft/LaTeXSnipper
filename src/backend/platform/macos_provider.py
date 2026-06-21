"""macOS platform providers for LaTeXSnipper.

Provides hotkey, screenshot, and system integration using Qt and native macOS APIs.
"""

from __future__ import annotations

import ctypes
import subprocess

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from backend.capture_overlay import ScreenCaptureOverlay
from backend.platform.protocols import (
    ApplicationMenuHandlers,
    PermissionResult,
    PermissionState,
    ScreenshotConfig,
    TrayMenuHandlers,
)
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
        self._settings_opened = False

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
            PermissionState.DENIED,
            "LaTeXSnipper needs Screen Recording permission to capture the screen.\n\n"
            "Open System Settings -> Privacy & Security -> Screen Recording, "
            "enable LaTeXSnipper, then restart the app if macOS asks you to.",
        )

    def open_permission_settings(self) -> None:
        if self._settings_opened:
            return
        self._settings_opened = True
        try:
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])
        except Exception as exc:
            print(f"[WARN] macOS privacy settings open failed: {exc}")

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
        tray_menu.addAction(f"Start Capture / Snip ({hotkey})", handlers.on_capture)
        if callable(handlers.build_capture_submenu):
            handlers.build_capture_submenu(tray_menu)
        tray_menu.addSeparator()
        tray_menu.addAction("Show Main Window", handlers.on_open)
        if callable(handlers.on_preferences):
            tray_menu.addAction("Preferences...", handlers.on_preferences)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit", handlers.on_exit)

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

    def install_application_menu(self, window, handlers: ApplicationMenuHandlers) -> None:
        if getattr(window, "_macos_application_menu_installed", False):
            return
        menu_bar = window.menuBar()
        if menu_bar is None:
            return

        app_menu = menu_bar.addMenu("LaTeXSnipper")

        about_action = QAction("About LaTeXSnipper", app_menu)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(handlers.on_about)
        app_menu.addAction(about_action)

        prefs_action = QAction("Preferences...", app_menu)
        prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs_action.setShortcut(QKeySequence("Meta+,"))
        prefs_action.triggered.connect(handlers.on_preferences)
        app_menu.addAction(prefs_action)

        app_menu.addSeparator()

        hide_action = QAction("Hide LaTeXSnipper", app_menu)
        hide_action.setShortcut(QKeySequence("Meta+H"))
        hide_action.triggered.connect(self._hide_application)
        app_menu.addAction(hide_action)

        hide_others_action = QAction("Hide Others", app_menu)
        hide_others_action.setShortcut(QKeySequence("Alt+Meta+H"))
        hide_others_action.triggered.connect(self._hide_other_applications)
        app_menu.addAction(hide_others_action)

        app_menu.addSeparator()

        quit_action = QAction("Quit LaTeXSnipper", app_menu)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Quit))
        quit_action.triggered.connect(handlers.on_quit)
        app_menu.addAction(quit_action)

        file_menu = menu_bar.addMenu("File")
        capture_action = QAction("Start Capture / Snip", file_menu)
        capture_action.setShortcut(QKeySequence("Meta+Alt+S"))
        capture_action.triggered.connect(handlers.on_capture)
        file_menu.addAction(capture_action)

        show_action = QAction("Show Main Window", file_menu)
        show_action.triggered.connect(handlers.on_show_window)
        file_menu.addAction(show_action)

        close_action = QAction("Close Window", file_menu)
        close_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Close))
        close_action.triggered.connect(handlers.on_close_window)
        file_menu.addAction(close_action)

        edit_menu = menu_bar.addMenu("Edit")
        self._add_standard_edit_action(edit_menu, "Copy", QKeySequence.StandardKey.Copy, "copy")
        self._add_standard_edit_action(edit_menu, "Paste", QKeySequence.StandardKey.Paste, "paste")
        self._add_standard_edit_action(edit_menu, "Select All", QKeySequence.StandardKey.SelectAll, "selectAll")

        setattr(window, "_macos_application_menu_installed", True)

    def _add_standard_edit_action(self, menu: QMenu, text: str, key, method_name: str) -> None:
        action = QAction(text, menu)
        action.setShortcut(QKeySequence(key))
        action.triggered.connect(lambda _=False, name=method_name: self._trigger_focused_widget_method(name))
        menu.addAction(action)

    def _trigger_focused_widget_method(self, method_name: str) -> None:
        app = QApplication.instance()
        widget = app.focusWidget() if app is not None else None
        method = getattr(widget, method_name, None)
        if callable(method):
            method()

    def _hide_application(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        for widget in app.topLevelWidgets():
            try:
                if widget.isVisible():
                    widget.hide()
            except Exception:
                pass

    def _hide_other_applications(self) -> None:
        script = (
            'tell application "System Events" to set visible of every process '
            'whose visible is true and name is not "LaTeXSnipper" to false'
        )
        try:
            subprocess.Popen(["osascript", "-e", script])
        except Exception as exc:
            print(f"[WARN] macOS hide others failed: {exc}")

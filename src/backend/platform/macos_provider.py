"""macOS platform providers for LaTeXSnipper.

Provides hotkey, screenshot, and system integration using Qt and native macOS APIs.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

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
        self._screen_capture_restart_required = False
        self._settings_opened = False
        self._last_permission_state = PermissionState.UNKNOWN

    @staticmethod
    def _screen_capture_permission_target() -> tuple[str, bool]:
        """Describe the process identity macOS can associate with capture access."""
        executable = Path(sys.executable or "python3").expanduser()
        bundle = next(
            (candidate for candidate in (executable, *executable.parents) if candidate.suffix.lower() == ".app"),
            None,
        )
        if bundle is not None and bool(getattr(sys, "frozen", False)):
            temporary_copy = str(bundle).startswith("/Volumes/") or "/AppTranslocation/" in str(bundle)
            return f"LaTeXSnipper.app ({bundle})", temporary_copy

        if bool(getattr(sys, "frozen", False)):
            return f"LaTeXSnipper 打包可执行文件 ({executable})", False

        return (
            "当前开发启动进程 "
            f"(Python: {executable}；以系统设置中实际显示的 Python、Terminal、iTerm 或 VS Code 为准)",
            False,
        )

    def _screen_capture_denial_message(self) -> str:
        target, temporary_copy = self._screen_capture_permission_target()
        temporary_guidance = (
            "检测到当前副本位于 DMG 或 App Translocation 临时位置。请先将 LaTeXSnipper.app 移到 /Applications，"
            "再从该位置重新打开并授权。\n\n"
            if temporary_copy
            else "如果是从 DMG 或 Downloads 直接打开，请先将 LaTeXSnipper.app 移到 /Applications，"
            "并确保授权的是当前运行的同一副本。\n\n"
        )
        return (
            "LaTeXSnipper 无法获得当前运行副本的屏幕录制权限。\n\n"
            f"当前授权对象：{target}\n\n"
            "请打开 System Settings -> Privacy & Security -> Screen & System Audio Recording "
            "(旧版 macOS 显示为 Screen Recording)，授权上述对象。\n\n"
            f"{temporary_guidance}"
            "授权后请使用 Command+Q 完全退出 LaTeXSnipper，再从同一位置重新打开。"
        )

    def _permission_result(self, state: PermissionState, message: str) -> PermissionResult:
        self._last_permission_state = state
        return PermissionResult(state, message)

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
        # Preflight before Qt/screencapture touches the screen. The actual TCC
        # target is the active app bundle in packaged mode and the launch process
        # in source mode, not merely the product name shown to the user.
        if self._screen_capture_restart_required:
            print("[INFO] macOS 屏幕录制权限状态已变化，需要重启后再截图")
            return self._permission_result(
                PermissionState.DENIED,
                self._screen_capture_denial_message(),
            )

        target, temporary_copy = self._screen_capture_permission_target()
        allowed = self._preflight_screen_capture_access()
        print(f"[DEBUG] macOS 屏幕录制权限预检: result={allowed!r} target={target} temporary_copy={temporary_copy}")
        if allowed is True:
            return self._permission_result(PermissionState.ALLOWED, "macos-screen-recording-allowed")
        if allowed is None:
            return self._permission_result(PermissionState.UNKNOWN, "macos-screen-recording-unknown")

        if not self._screen_capture_prompted:
            self._screen_capture_prompted = True
            self._screen_capture_restart_required = True
            print("[INFO] 通过 CoreGraphics 请求 macOS 屏幕录制权限")
            requested = self._request_screen_capture_access()
            print(f"[INFO] macOS 屏幕录制权限请求结果: {requested!r}，需要重启应用后再截图")

        return self._permission_result(
            PermissionState.DENIED,
            self._screen_capture_denial_message(),
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
        overlay = ScreenCaptureOverlay(
            capture_display_mode=cfg.capture_display_mode,
            preferred_screen_index=cfg.preferred_screen_index,
            screenshot_tool=cfg.screenshot_tool,
        )
        overlay.macos_permission_preflight_state = self._last_permission_state.value
        return overlay


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
        self._add_paste_action(edit_menu, handlers.on_paste)
        self._add_standard_edit_action(edit_menu, "Select All", QKeySequence.StandardKey.SelectAll, "selectAll")

        setattr(window, "_macos_application_menu_installed", True)

    def _add_standard_edit_action(self, menu: QMenu, text: str, key, method_name: str) -> None:
        action = QAction(text, menu)
        action.setShortcut(QKeySequence(key))
        action.triggered.connect(lambda _=False, name=method_name: self._trigger_focused_widget_method(name))
        menu.addAction(action)

    def _add_paste_action(self, menu: QMenu, image_paste_handler) -> None:
        action = QAction("Paste", menu)
        action.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
        action.triggered.connect(lambda _=False: self._trigger_paste(image_paste_handler))
        menu.addAction(action)

    def _trigger_paste(self, image_paste_handler) -> None:
        if callable(image_paste_handler):
            try:
                if image_paste_handler():
                    return
            except Exception as exc:
                print(f"[WARN] macOS image paste handler failed: {exc}")
        self._trigger_focused_widget_method("paste")

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

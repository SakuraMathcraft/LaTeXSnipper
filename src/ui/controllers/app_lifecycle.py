"""AppLifecycleController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from platform_services.protocols import ISystemProvider
    from ui.controllers.capture import CaptureController
    from ui.controllers.file_drop import FileInputController
    from ui.controllers.tray import TrayController
    from ui.controllers.windows import WindowController
    from ui.main_window import MainWindow
import logging
import os
import sys

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from qfluentwidgets import InfoBar, InfoBarPosition

from localization.manager import translate as tr
from platform_services import ApplicationMenuHandlers
from runtime.runtime_logging import cleanup_runtime_log_session
from runtime.single_instance import (
    release_single_instance_lock as _release_single_instance_lock,
)
from ui.controllers.runtime_log import apply_runtime_log_window_preference

logger = logging.getLogger(f"latexsnipper.{__name__}")


class _MacApplicationQuitFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event):
        if sys.platform == "darwin" and event.type() == QEvent.Type.Quit:
            window = self._window
            try:
                window._force_exit = True
                window.shutdown()
            except Exception:
                pass
        elif (
            sys.platform == "darwin" and event.type() == QEvent.Type.ApplicationActivate
        ):
            window = self._window
            try:
                QTimer.singleShot(0, window._reactivate_from_dock)
            except Exception:
                pass
        return False


class AppLifecycleController(QObject):
    def __init__(
        self,
        view: MainWindow,
        capture: CaptureController,
        file_input: FileInputController,
        system_provider: ISystemProvider,
        tray: TrayController,
        windows: WindowController,
        shutdown_actions: tuple[Callable[[], None], ...],
    ):
        super().__init__(view)
        self.view = view
        self.capture = capture
        self.file_input = file_input
        self.system_provider = system_provider
        self.tray = tray
        self.windows = windows
        self.shutdown_actions = shutdown_actions
        self._force_exit = False
        self._shutdown_done = False
        self._mac_quit_filter = None
        self._dock_close_notice_shown = False
        self._tray_msg_shown = False

    def install_platform_lifecycle_hooks(self):
        if sys.platform != "darwin":
            return
        app = QCoreApplication.instance()
        if app is None or getattr(self, "_mac_quit_filter", None) is not None:
            return
        self._mac_quit_filter = _MacApplicationQuitFilter(self.view)
        app.installEventFilter(self._mac_quit_filter)
        self._install_macos_application_menu()

    def _install_macos_application_menu(self):
        if sys.platform != "darwin":
            return
        provider = getattr(self, "system_provider", None)
        installer = getattr(provider, "install_application_menu", None)
        if not callable(installer):
            return
        handlers = ApplicationMenuHandlers(
            on_about=self._show_about_dialog,
            on_preferences=self.windows.open_settings,
            on_capture=self.capture.start_capture,
            on_show_window=self.windows.show_window,
            on_close_window=self._close_active_window,
            on_quit=self.truly_exit,
            on_paste=self._handle_latex_editor_image_paste,
        )
        installer(self.view, handlers)

    def _handle_latex_editor_image_paste(self) -> bool:
        """Route Command+V images through OCR only when the LaTeX editor owns focus."""
        editor = getattr(self.view, "latex_editor", None)
        if editor is None:
            return False
        try:
            viewport = editor.viewport()
            if not editor.hasFocus() and (viewport is None or not viewport.hasFocus()):
                return False
        except Exception:
            return False
        try:
            return bool(self.file_input._handle_clipboard_image_paste())
        except Exception as exc:
            logger.warning("macOS 图片粘贴处理失败: %s", exc)
            return False

    def _show_about_dialog(self):
        InfoBar.info(
            title=tr("关于 LaTeXSnipper"),
            content=tr("截图、识别、手写、编辑与导出数学内容。"),
            parent=self.view,
            duration=5000,
            position=InfoBarPosition.TOP,
        )

    def _close_active_window(self):
        app = QApplication.instance()
        active = app.activeWindow() if app is not None else None
        if active is not None and active is not self.view:
            try:
                active.close()
                return
            except Exception:
                pass
        self.view.close()

    def _reactivate_from_dock(self):
        if sys.platform != "darwin" or getattr(self, "_force_exit", False):
            return
        try:
            if not self.view.isVisible() or self.view.isMinimized():
                self.windows.show_window()
        except Exception:
            pass

    def apply_runtime_log_window_preference(self, enabled: bool):
        """Apply the runtime-log window preference."""
        try:
            os.environ["LATEXSNIPPER_SHOW_RUNTIME_LOG"] = "1" if enabled else "0"
            apply_runtime_log_window_preference(force=False)
        except Exception as e:
            logger.warning("应用运行日志窗口设置失败: %s", e)

    def closeEvent(self, event):
        if self._force_exit:
            self.shutdown()
            event.accept()
            return
        if sys.platform == "linux":
            tray_available = False
            try:
                tray_available = bool(
                    getattr(self.tray, "tray_icon", None)
                    and QSystemTrayIcon.isSystemTrayAvailable()
                    and self.tray.tray_icon.isVisible()
                )
            except Exception:
                tray_available = bool(getattr(self.tray, "tray_icon", None))
            if tray_available:
                self.view.hide()
                if not getattr(self, "_tray_msg_shown", False):
                    self.system_provider.show_notification(
                        self.tray.tray_icon, "LaTeXSnipper", tr("已最小化到系统托盘")
                    )
                    self._tray_msg_shown = True
                event.ignore()
                return
            reply = QMessageBox.question(
                self.view,
                tr("确认退出"),
                tr("关闭窗口将完全退出 LaTeXSnipper，是否确认？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._force_exit = True
                if self.tray.tray_icon:
                    self.tray.tray_icon.hide()
                self.view.close()
                QTimer.singleShot(0, QCoreApplication.quit)
            else:
                event.ignore()
            return
        if sys.platform == "darwin":
            self.view.hide()
            if self.tray.tray_icon and (
                not getattr(self, "_dock_close_notice_shown", False)
            ):
                try:
                    self.system_provider.show_notification(
                        self.tray.tray_icon,
                        "LaTeXSnipper",
                        tr("主窗口已关闭，可通过 Dock 或菜单栏重新打开"),
                    )
                    self._dock_close_notice_shown = True
                except Exception:
                    pass
            event.accept()
            return
        self.view.hide()
        if self.tray.tray_icon:
            if not getattr(self, "_tray_msg_shown", False):
                self.system_provider.show_notification(
                    self.tray.tray_icon, "LaTeXSnipper", tr("已最小化到系统托盘")
                )
                self._tray_msg_shown = True
        event.ignore()

    def truly_exit(self):
        self._force_exit = True
        if self.tray.tray_icon:
            self.tray.tray_icon.hide()
        try:
            self.view.close()
        except Exception:
            pass
        QTimer.singleShot(0, lambda: (self.shutdown(), QCoreApplication.quit()))

    def prepare_restart(self):
        self._force_exit = True
        self.shutdown()

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        for action in self.shutdown_actions:
            try:
                action()
            except Exception:
                logger.exception("退出清理失败: %s", action.__qualname__)
        if self._mac_quit_filter is not None:
            QCoreApplication.instance().removeEventFilter(self._mac_quit_filter)
        logger.info("LaTeXSnipper 已退出")
        cleanup_runtime_log_session()
        _release_single_instance_lock()

"""Application lifecycle controller mixin for the main window."""

from __future__ import annotations

import os
import sys

from localization.manager import translate as tr
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from qfluentwidgets import InfoBar, InfoBarPosition

from platform_services import ApplicationMenuHandlers
from runtime.runtime_logging import cleanup_runtime_log_session
from ui.runtime_log_controller import apply_runtime_log_window_preference
from runtime.single_instance import (
    release_single_instance_lock as _release_single_instance_lock,
)


class _MacApplicationQuitFilter(QObject):
    def __init__(self, window):
        super().__init__(window)
        self._window = window

    def eventFilter(self, obj, event):
        if sys.platform == "darwin" and event.type() == QEvent.Type.Quit:
            window = self._window
            try:
                window._force_exit = True
                window._graceful_shutdown()
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


class AppLifecycleMixin:
    def install_platform_lifecycle_hooks(self):
        if sys.platform != "darwin":
            return
        app = QCoreApplication.instance()
        if app is None or getattr(self, "_mac_quit_filter", None) is not None:
            return
        self._mac_quit_filter = _MacApplicationQuitFilter(self)
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
            on_preferences=self.open_settings,
            on_capture=self.start_capture,
            on_show_window=self.show_window,
            on_close_window=self._close_active_window,
            on_quit=self.truly_exit,
            on_paste=self._handle_latex_editor_image_paste,
        )
        installer(self, handlers)

    def _handle_latex_editor_image_paste(self) -> bool:
        """Route Command+V images through OCR only when the LaTeX editor owns focus."""
        editor = getattr(self, "latex_editor", None)
        if editor is None:
            return False
        try:
            viewport = editor.viewport()
            if not editor.hasFocus() and (viewport is None or not viewport.hasFocus()):
                return False
        except Exception:
            return False
        try:
            return bool(self._handle_clipboard_image_paste())
        except Exception as exc:
            print(f"[WARN] macOS 图片粘贴处理失败: {exc}")
            return False

    def _show_about_dialog(self):
        InfoBar.info(
            title=tr("关于 LaTeXSnipper"),
            content=tr("截图、识别、手写、编辑与导出数学内容。"),
            parent=self,
            duration=5000,
            position=InfoBarPosition.TOP,
        )

    def _close_active_window(self):
        app = QApplication.instance()
        active = app.activeWindow() if app is not None else None
        if active is not None and active is not self:
            try:
                active.close()
                return
            except Exception:
                pass
        self.close()

    def _reactivate_from_dock(self):
        if sys.platform != "darwin" or getattr(self, "_force_exit", False):
            return
        try:
            if not self.isVisible() or self.isMinimized():
                self.show_window()
        except Exception:
            pass

    def apply_runtime_log_window_preference(self, enabled: bool):
        """Apply the runtime-log window preference."""
        try:
            os.environ["LATEXSNIPPER_SHOW_RUNTIME_LOG"] = "1" if enabled else "0"
            apply_runtime_log_window_preference(force=False, tee=True)
        except Exception as e:
            print(f"[WARN] 应用运行日志窗口设置失败: {e}")

    def prepare_restart(self):
        """Called by settings restart flow: close heavy resources and release app lock early."""
        self._force_exit = True
        try:
            self._graceful_shutdown()
        except Exception:
            pass
        try:
            cleanup_runtime_log_session()
        except Exception:
            pass
        try:
            _release_single_instance_lock()
        except Exception:
            pass
        try:
            if getattr(self, "hotkey_provider", None):
                self.hotkey_provider.cleanup()
        except Exception:
            pass

    def _graceful_shutdown(self):
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        self._model_warmup_cancelled = True

        try:
            self.save_history()
        except Exception as e:
            print(f"[WARN] 保存历史失败: {e}")

        try:
            if hasattr(self, "favorites_window") and self.favorites_window:
                self.favorites_window.save_favorites()
        except Exception as e:
            print(f"[WARN] 保存收藏夹失败: {e}")

        try:
            self.cfg.save()
        except Exception as e:
            print(f"[WARN] 保存配置失败: {e}")

        try:
            if getattr(self, "hotkey_provider", None):
                self.hotkey_provider.cleanup()
        except Exception:
            pass
        try:
            if getattr(self, "tray_icon", None):
                self.tray_icon.hide()
                self.tray_icon.deleteLater()
        except Exception:
            pass
        try:
            timer = getattr(self, "_auto_theme_refresh_timer", None)
            if timer is not None:
                timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, "overlay", None):
                self.overlay.close()
                self.overlay = None
        except Exception:
            pass
        try:
            automation_api = getattr(self, "automation_api", None)
            if automation_api is not None:
                automation_api.shutdown()
        except Exception:
            pass
        try:
            coordinator = getattr(self, "recognition_coordinator", None)
            if coordinator is not None:
                coordinator.stop(wait=False)
        except Exception:
            pass
        try:
            model = getattr(self, "model", None)
            stop_model = getattr(model, "_stop_mathcraft_worker", None)
            if callable(stop_model):
                stop_model()
        except Exception:
            pass

        if self.predict_thread:
            try:
                if self.predict_thread.isRunning():
                    self.predict_thread.quit()
                    self.predict_thread.wait(3000)
            except Exception:
                pass
        if self.predict_worker:
            try:
                self.predict_worker.deleteLater()
            except Exception:
                pass
        self.predict_thread = None
        self.predict_worker = None
        self._predict_busy = False

        if self.pdf_predict_thread:
            try:
                if self.pdf_predict_thread.isRunning():
                    self.pdf_predict_thread.quit()
                    self.pdf_predict_thread.wait(3000)
            except Exception:
                pass
        if self.pdf_predict_worker:
            try:
                self.pdf_predict_worker.deleteLater()
            except Exception:
                pass
        self.pdf_predict_thread = None
        self.pdf_predict_worker = None
        if self.pdf_progress:
            try:
                self.pdf_progress.close()
            except Exception:
                pass
            self.pdf_progress = None
        if self._pdf_result_window:
            try:
                self._pdf_result_window.close()
            except Exception:
                pass
        if self._preview_render_thread:
            try:
                if self._preview_render_thread.isRunning():
                    self._preview_render_thread.quit()
                    self._preview_render_thread.wait(3000)
            except Exception:
                pass
        if self._preview_render_worker:
            try:
                self._preview_render_worker.deleteLater()
            except Exception:
                pass
        self._preview_render_thread = None
        self._preview_render_worker = None
        print("[INFO] LaTeXSnipper 已退出")
        try:
            cleanup_runtime_log_session()
        except Exception:
            pass
        try:
            _release_single_instance_lock()
        except Exception:
            pass

    def closeEvent(self, event):
        if self._force_exit:
            self._graceful_shutdown()
            event.accept()
            return

        if sys.platform == "linux":
            tray_available = False
            try:
                tray_available = bool(
                    getattr(self, "tray_icon", None)
                    and QSystemTrayIcon.isSystemTrayAvailable()
                    and self.tray_icon.isVisible()
                )
            except Exception:
                tray_available = bool(getattr(self, "tray_icon", None))
            if tray_available:
                self.hide()
                if not getattr(self, "_tray_msg_shown", False):
                    self.system_provider.show_notification(
                        self.tray_icon, "LaTeXSnipper", tr("已最小化到系统托盘")
                    )
                    self._tray_msg_shown = True
                event.ignore()
                return
            reply = QMessageBox.question(
                self,
                tr("确认退出"),
                tr("关闭窗口将完全退出 LaTeXSnipper，是否确认？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._force_exit = True
                if self.tray_icon:
                    self.tray_icon.hide()
                self.close()
                QTimer.singleShot(0, QCoreApplication.quit)
            else:
                event.ignore()
            return

        if sys.platform == "darwin":
            self.hide()
            if self.tray_icon and not getattr(self, "_dock_close_notice_shown", False):
                try:
                    self.system_provider.show_notification(
                        self.tray_icon,
                        "LaTeXSnipper",
                        tr("主窗口已关闭，可通过 Dock 或菜单栏重新打开"),
                    )
                    self._dock_close_notice_shown = True
                except Exception:
                    pass
            event.accept()
            return

        self.hide()
        if self.tray_icon:
            if not getattr(self, "_tray_msg_shown", False):
                self.system_provider.show_notification(
                    self.tray_icon, "LaTeXSnipper", tr("已最小化到系统托盘")
                )
                self._tray_msg_shown = True
        event.ignore()

    def truly_exit(self):
        self._force_exit = True
        if self.tray_icon:
            self.tray_icon.hide()

        try:
            self.close()
        except Exception:
            pass
        QTimer.singleShot(
            0, lambda: (self._graceful_shutdown(), QCoreApplication.quit())
        )

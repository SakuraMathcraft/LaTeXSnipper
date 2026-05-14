"""Application lifecycle controller mixin for the main window."""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QMessageBox

from runtime.runtime_logging import cleanup_runtime_log_session, open_debug_console
from runtime.single_instance import release_single_instance_lock as _release_single_instance_lock


class AppLifecycleMixin:
    def apply_startup_console_preference(self, enabled: bool):
        """Apply the startup log-window preference."""
        try:
            os.environ["LATEXSNIPPER_SHOW_CONSOLE"] = "1" if enabled else "0"
            open_debug_console(force=False, tee=True)
        except Exception as e:
            print(f"[WARN] apply_startup_console_preference failed: {e}")

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


        try:
            self.save_history()
            print("[关闭] 历史记录已保存")
        except Exception as e:
            print(f"[关闭] 保存历史失败: {e}")


        try:
            if hasattr(self, 'favorites_window') and self.favorites_window:
                self.favorites_window.save_favorites()
                print("[关闭] 收藏夹已保存")
        except Exception as e:
            print(f"[关闭] 保存收藏夹失败: {e}")


        try:
            self.cfg.save()
            print("[关闭] 配置已保存")
        except Exception as e:
            print(f"[关闭] 保存配置失败: {e}")


        try:
            m = getattr(self, "model", None)
            if m:
                fn = getattr(m, "_stop_mathcraft_worker", None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
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
            reply = QMessageBox.question(
                self,
                "确认退出",
                "关闭窗口将完全退出 LaTeXSnipper，是否确认？\n\n"
                "（提示：你可以通过系统托盘菜单的「退出」来关闭程序）",
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

        self.hide()
        if self.tray_icon:

            if not getattr(self, '_tray_msg_shown', False):
                self.system_provider.show_notification(self.tray_icon, "LaTeXSnipper", "已最小化到系统托盘")
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
        QTimer.singleShot(0, lambda: (self._graceful_shutdown(), QCoreApplication.quit()))

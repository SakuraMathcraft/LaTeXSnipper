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

    def _stop_timer_attr(self, attr_name: str) -> None:
        timer = getattr(self, attr_name, None)
        if timer is None:
            return
        try:
            timer.stop()
        except Exception:
            pass

    def _close_capture_overlay_for_shutdown(self) -> None:
        self._capture_start_pending = False
        self._capture_waiting_for_hidden_result_window = False
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return
        try:
            overlay.removeEventFilter(self)
        except Exception:
            pass
        try:
            overlay.close()
        except Exception:
            pass
        self.overlay = None

    def _stop_worker_thread(self, thread_attr: str, worker_attr: str, timeout_ms: int = 3000) -> None:
        thread = getattr(self, thread_attr, None)
        worker = getattr(self, worker_attr, None)

        if worker is not None:
            cancel = getattr(worker, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass

        stopped = True
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
            try:
                if thread.isRunning():
                    thread.quit()
                    stopped = bool(thread.wait(timeout_ms))
            except Exception:
                stopped = False

        if worker is not None and stopped:
            try:
                worker.deleteLater()
            except Exception:
                pass
            setattr(self, worker_attr, None)
        elif worker is not None:
            print(f"[关闭] {worker_attr} 仍在运行，跳过 deleteLater")

        if stopped:
            setattr(self, thread_attr, None)

    def _graceful_shutdown(self):
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True

        self._close_capture_overlay_for_shutdown()

        try:
            if getattr(self, "hotkey_provider", None):
                self.hotkey_provider.cleanup()
                print("[关闭] 全局快捷键已清理")
        except Exception as e:
            print(f"[关闭] 清理全局快捷键失败: {e}")

        self._stop_timer_attr("_auto_theme_refresh_timer")
        self._stop_timer_attr("_render_timer")

        try:
            m = getattr(self, "model", None)
            if m:
                fn = getattr(m, "_stop_mathcraft_worker", None)
                if callable(fn):
                    fn()
        except Exception:
            pass

        self._stop_worker_thread("predict_thread", "predict_worker")
        self._predict_busy = False
        self._stop_worker_thread("pdf_predict_thread", "pdf_predict_worker")
        self._stop_worker_thread("_preview_render_thread", "_preview_render_worker")

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

        try:
            if self.tray_icon:
                self.tray_icon.hide()
        except Exception as e:
            print(f"[关闭] 隐藏托盘图标失败: {e}")

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
            cleanup_runtime_log_session()
        except Exception:
            pass
        try:
            _release_single_instance_lock()
        except Exception:
            pass

    def request_quit(self):
        self._force_exit = True
        try:
            self._graceful_shutdown()
        finally:
            QTimer.singleShot(0, QCoreApplication.quit)

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
                self.request_quit()
                event.accept()
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
        self.request_quit()

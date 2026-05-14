"""Prediction result dialog controller mixin for the main window."""

from __future__ import annotations

import ctypes
import datetime
import os

import pyperclip
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition

from bootstrap.deps_bootstrap import custom_warning_dialog
from preview.content_preview import build_mixed_content_html
from preview.math_preview import dialog_theme_tokens, is_dark_ui
from runtime.webengine_runtime import ensure_webengine_loaded
from ui.predict_result_dialog import show_predict_result_dialog
from ui.window_helpers import exec_close_only_message_box as _exec_close_only_message_box

try:
    from PyQt6 import sip
except Exception:
    try:
        import sip  # pyright: ignore[reportMissingImports]
    except Exception:
        sip = None

class PredictResultControllerMixin:
    def _clear_predict_result_dialog_ref(self, dialog_obj=None):
        """Clear the result dialog reference only when the callback still targets this window."""
        current = getattr(self, "_predict_result_dialog", None)
        if dialog_obj is None or current is dialog_obj:
            self._predict_result_dialog = None
        hidden = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        if dialog_obj is None or hidden is dialog_obj:
            self._hidden_unpinned_predict_result_dialog_for_capture = None
        restoring = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        if dialog_obj is None or restoring is dialog_obj:
            self._restore_predict_result_dialog_after_capture = None

    def _is_predict_result_dialog_alive(self, dlg) -> bool:
        if dlg is None:
            return False
        try:
            if sip is not None and sip.isdeleted(dlg):
                return False
        except Exception:
            pass
        return True

    def _move_predict_result_dialog_to_screen(self, dlg: QDialog, screen_index: int | None) -> None:
        if screen_index is None or bool(getattr(dlg, "_predict_result_pinned", False)):
            return
        try:
            from PyQt6.QtGui import QGuiApplication

            screens = QGuiApplication.screens()
            idx = int(screen_index)
            if idx < 0 or idx >= len(screens):
                return
            geo = screens[idx].availableGeometry()
            size = dlg.size()
            main_screen = None
            try:
                handle = self.windowHandle()
                if handle is not None:
                    main_screen = handle.screen()
            except Exception:
                main_screen = None
            if main_screen is None:
                try:
                    main_screen = QGuiApplication.screenAt(self.frameGeometry().center())
                except Exception:
                    main_screen = None
            same_screen_as_main = bool(main_screen is screens[idx])

            if self.isVisible() and not self.isMinimized() and same_screen_as_main:
                width = min(int(size.width()), int(geo.width()))
                height = min(int(size.height()), int(geo.height()))
                x = int(geo.x() + max(0, (geo.width() - width) // 2))
                y = int(geo.y() + max(0, (geo.height() - height) // 2))
            else:
                margin = 24
                x = int(geo.x() + margin)
                y = int(geo.y() + margin)
            max_x = geo.right() - int(size.width()) + 1
            max_y = geo.bottom() - int(size.height()) + 1
            x = max(geo.left(), min(x, max_x))
            y = max(geo.top(), min(y, max_y))
            dlg.move(x, y)
        except Exception:
            pass

    def _predict_result_pinned_size(self) -> tuple[int, int]:
        """Return the compact size for a pinned recognition result window."""
        return (320, 380)

    def _predict_result_mode_title(self, current_mode: str) -> str:
        mode_titles = {
            "mathcraft": "确认或修改 LaTeX：",
            "mathcraft_text": "识别的文字内容：",
            "mathcraft_mixed": "识别结果（文字+公式）：",
        }
        return mode_titles.get(current_mode, "确认或修改内容：")

    def _set_predict_result_pin_button_style(self, button, pinned: bool):
        try:
            t = dialog_theme_tokens()
            icon = FluentIcon.UNPIN if pinned else FluentIcon.PIN
            button.setIcon(icon.icon())
            button.setIconSize(QSize(18, 18))
            button.setToolTip("固定为小窗口并保持置顶，再点一次恢复可调整大小")
            if pinned:
                dark = is_dark_ui()
                bg = "#2f6ea8" if dark else "#3daee9"
                hover = "#3e82c3" if dark else "#5dbff2"
                pressed = "#245a8d" if dark else "#319fd9"
                border = "#4d8dca" if dark else "#2b94cb"
                button.setStyleSheet(
                    f"""
                    QToolButton {{
                        background: {bg};
                        color: #ffffff;
                        border: 1px solid {border};
                        border-radius: 4px;
                        padding: 0;
                    }}
                    QToolButton:hover {{
                        background: {hover};
                        border: 1px solid {border};
                    }}
                    QToolButton:pressed {{
                        background: {pressed};
                        border: 1px solid {border};
                    }}
                    """
                )
            else:
                button.setStyleSheet(
                    f"""
                    QToolButton {{
                        background: transparent;
                        color: {t["muted"]};
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 0;
                        min-width: 30px;
                        min-height: 30px;
                    }}
                    QToolButton:hover {{
                        background: {t["panel_bg"]};
                        border: 1px solid {t["accent"]};
                    }}
                    QToolButton:pressed {{
                        background: {t["panel_bg"]};
                    }}
                    """
                )
        except Exception:
            pass

    def _set_predict_result_native_caption_buttons(self, dlg: QDialog, pinned: bool) -> bool:
        if os.name != "nt":
            return False
        try:
            hwnd = int(dlg.winId())
            if not hwnd:
                return False
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -16)
            if not style:
                return False
            ws_minimizebox = 0x00020000
            ws_maximizebox = 0x00010000
            if pinned:
                style &= ~ws_minimizebox
                style &= ~ws_maximizebox
            else:
                style &= ~ws_minimizebox
                style |= ws_maximizebox
            user32.SetWindowLongW(hwnd, -16, style)
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOMOVE | NOSIZE | NOZORDER | NOACTIVATE | FRAMECHANGED
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
            return True
        except Exception:
            return False

    def _set_predict_result_native_topmost(self, dlg: QDialog, topmost: bool) -> bool:
        if os.name != "nt":
            return False
        try:
            hwnd = int(dlg.winId())
            if not hwnd:
                return False
            user32 = ctypes.windll.user32
            insert_after = -1 if topmost else -2  # HWND_TOPMOST / HWND_NOTOPMOST
            flags = 0x0010 | 0x0001 | 0x0002 | 0x0040  # NOACTIVATE | NOSIZE | NOMOVE | SHOWWINDOW
            ok = user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags)
            return bool(ok)
        except Exception:
            return False

    def _set_predict_result_pinned(self, dlg: QDialog, pin_btn, pinned: bool):
        dlg._predict_result_pinned = bool(pinned)
        try:
            if pinned and not dlg.isMaximized():
                dlg._pin_restore_geometry = dlg.geometry()
        except Exception:
            pass

        try:
            dlg.setMinimumSize(0, 0)
            dlg.setMaximumSize(16777215, 16777215)
        except Exception:
            pass

        if pinned:
            width, height = self._predict_result_pinned_size()
            dlg.setFixedSize(width, height)
        else:
            restore_geometry = getattr(dlg, "_pin_restore_geometry", None)
            if restore_geometry is not None:
                try:
                    dlg.resize(restore_geometry.size())
                    dlg.move(restore_geometry.topLeft())
                except Exception:
                    pass

        if not self._set_predict_result_native_topmost(dlg, pinned):
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
            dlg.show()
        self._set_predict_result_native_caption_buttons(dlg, pinned)

        self._set_predict_result_pin_button_style(pin_btn, pinned)
        try:
            pin_btn.setChecked(pinned)
        except Exception:
            pass
        dlg.raise_()
        dlg.activateWindow()

    def _try_refresh_predict_result_dialog(self, dlg: QDialog, code: str, current_mode: str) -> bool:
        try:
            if not bool(getattr(dlg, "_predict_result_pinned", False)):
                return False
            if getattr(dlg, "_predict_result_mode", None) != current_mode:
                return False
            editor = getattr(dlg, "_predict_result_editor", None)
            info_label = getattr(dlg, "_predict_result_info_label", None)
            if editor is None or info_label is None:
                return False
            info_label.setText(self._predict_result_mode_title(current_mode))
            editor.setPlainText(code)
            dlg.raise_()
            dlg.activateWindow()
            return True
        except Exception:
            return False

    def _hide_unpinned_predict_result_dialog_for_capture(self, dlg: QDialog) -> None:
        """Hide an unpinned result dialog before the clean desktop snapshot is taken."""
        try:
            if os.name == "nt":
                hwnd = int(dlg.winId())
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            dlg.hide()
            dlg.setVisible(False)
        except Exception:
            try:
                dlg.hide()
            except Exception:
                pass

    def _flush_desktop_after_capture_window_hide(self) -> None:
        """Let Qt and DWM publish hidden result windows before ScreenCaptureOverlay grabs pixels."""
        try:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass
        if os.name == "nt":
            try:
                ctypes.windll.dwmapi.DwmFlush()
            except Exception:
                pass
        try:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        except Exception:
            pass

    def _prepare_predict_result_dialog_for_capture(self):
        dlg = getattr(self, "_predict_result_dialog", None)
        self._restore_predict_result_dialog_after_capture = None
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            if bool(getattr(dlg, "_predict_result_pinned", False)) and dlg.isVisible():
                self._restore_predict_result_dialog_after_capture = dlg
            elif dlg.isVisible():
                self._hidden_unpinned_predict_result_dialog_for_capture = dlg
                self._hide_unpinned_predict_result_dialog_for_capture(dlg)
        except Exception:
            self._restore_predict_result_dialog_after_capture = None
            self._hidden_unpinned_predict_result_dialog_for_capture = None

    def _restore_predict_result_dialog_visibility(self):
        dlg = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        self._restore_predict_result_dialog_after_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            dlg.show()
            if bool(getattr(dlg, "_predict_result_pinned", False)):
                self._set_predict_result_native_topmost(dlg, True)
                self._set_predict_result_native_caption_buttons(dlg, True)
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _restore_hidden_unpinned_predict_result_dialog(self):
        dlg = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            if bool(getattr(dlg, "_predict_result_pinned", False)):
                return
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _discard_hidden_unpinned_predict_result_dialog(self, dialog_obj=None):
        hidden = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        if dialog_obj is None or hidden is dialog_obj:
            self._hidden_unpinned_predict_result_dialog_for_capture = None

    def on_predict_ok(self, latex: str):
        self._recognition_cancel_requested = False
        used = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "predict_worker", None), "config", None)
                )
                if not used:
                    used = getattr(self, "_last_external_model_name", None)
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            used = None
        if not used:
            used = getattr(self, "current_model", "mathcraft")
        self.set_model_status("完成")
        self.set_action_status("识别完成", auto_clear_ms=3000)
        try:
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] 识别完成 model={used} time={elapsed:.2f}s")
            else:
                print(f"[INFO] 识别完成 model={used}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):

            show_toast = bool(self.cfg.get("show_capture_success_toast", False))
            if show_toast:
                try:
                    now_ts = datetime.datetime.now().timestamp()
                    cooldown_ok = (now_ts - float(getattr(self, "_last_capture_toast_ts", 0.0) or 0.0)) >= 12.0
                    bg_mode = (not self.isVisible()) or self.isMinimized() or (not self.isActiveWindow())
                    if cooldown_ok and bg_mode:
                        hk = self.cfg.get("hotkey", "Ctrl+F")
                        self.system_provider.show_notification(
                            self.tray_icon,
                            "识别完成",
                            f"公式已识别。使用快捷键 {hk} 可再次截图。",
                            critical=False,
                            timeout_ms=2500,
                        )
                        self._last_capture_toast_ts = now_ts
                except Exception:
                    pass
        self.show_confirm_dialog(latex)
        self._discard_hidden_unpinned_predict_result_dialog()

    def show_confirm_dialog(self, latex_code: str):
        """Show the recognition result confirmation dialog."""
        result_screen_index = self._next_predict_result_screen_index
        self._next_predict_result_screen_index = None
        code = (latex_code or "").strip()
        if not code:
            _exec_close_only_message_box(self, "提示", "结果为空")
            return


        current_mode = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                current_mode = "external_model"
            else:
                current_mode = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            current_mode = None
        if not current_mode:
            current_mode = getattr(self, "current_model", "mathcraft")


        old_dialog = getattr(self, "_predict_result_dialog", None)
        if old_dialog is not None and self._try_refresh_predict_result_dialog(old_dialog, code, current_mode):
            return
        if old_dialog is not None:
            try:
                old_dialog.close()
            except Exception:
                pass
            self._clear_predict_result_dialog_ref(old_dialog)

        self._predict_result_dialog = show_predict_result_dialog(
            parent=self,
            code=code,
            current_mode=current_mode,
            result_screen_index=result_screen_index,
            mode_title=self._predict_result_mode_title,
            ensure_webengine_loaded=ensure_webengine_loaded,
            build_mixed_html=self._build_mixed_html,
            show_export_menu_for_source=self._show_export_menu_for_source,
            accept_latex=self.accept_latex,
            set_pin_button_style=self._set_predict_result_pin_button_style,
            set_pinned=self._set_predict_result_pinned,
            move_to_screen=self._move_predict_result_dialog_to_screen,
            clear_dialog_ref=self._clear_predict_result_dialog_ref,
        )

    def _build_mixed_html(self, content: str) -> str:
        return build_mixed_content_html(content)

    def on_predict_fail(self, msg: str, external_model: bool | None = None):
        self._next_predict_result_screen_index = None
        self._restore_hidden_unpinned_predict_result_dialog()
        if self._is_user_cancelled_recognition_error(msg):
            try:
                print(f"[INFO] 识别已中断: {msg}")
            except Exception:
                pass
            self._show_recognition_cancelled_infobar()
            return
        self.set_model_status("失败")
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "predict_worker", None), "config", None)
                )
                if not used:
                    used = getattr(self, "_last_external_model_name", None)
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                print(f"[INFO] 识别失败 model={used} err={msg}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            hk = self.cfg.get("hotkey", "Ctrl+F")
            try:
                self.system_provider.show_notification(
                    self.tray_icon,
                    "识别失败",
                    f"{msg}\n可使用快捷键 {hk} 重试。",
                    critical=True,
                    timeout_ms=4000,
                )
            except Exception:
                pass
        content = self._recognition_failure_content(
            msg,
            worker_attr="predict_worker",
            external_model=external_model,
        )
        self.set_action_status(content, auto_clear_ms=4500)
        try:
            InfoBar.error(
                title="识别失败",
                content=content,
                parent=self,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("错误", content, self)

    def accept_latex(self, dialog, te: QTextEdit):
        t = te.toPlainText().strip()
        if not t:
            if bool(getattr(dialog, "_predict_result_pinned", False)):
                self.set_action_status("识别结果为空", parent=dialog)
                return
            dialog.reject()
            return
        try:
            try:
                pyperclip.copy(t)
            except Exception:
                QApplication.clipboard().setText(t)
        except Exception as e:
            custom_warning_dialog("错误", f"复制失败: {e}",self)
        try:
            content_type = None
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
            if not content_type:
                content_type = getattr(self, "current_model", "mathcraft")
            self.add_history_record(t, content_type=content_type)
        except Exception as e:
            custom_warning_dialog("错误", f"写入历史失败: {e}", self)
        if bool(getattr(dialog, "_predict_result_pinned", False)):
            self.set_action_status("已确认并复制到剪贴板", parent=dialog)
            try:
                dialog.raise_()
                dialog.activateWindow()
            except Exception:
                pass
            return
        dialog.accept()

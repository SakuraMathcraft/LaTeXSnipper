"""RecognitionResultController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QSystemTrayIcon

    from platform_services.protocols import ISystemProvider
    from runtime.config_manager import ConfigManager
    from ui.controllers.editor_actions import EditorActionsController
    from ui.controllers.history import HistoryController
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.status import StatusController
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
import ctypes
import datetime
import logging
import os
import sys
import time

import pyperclip
from PyQt6 import sip
from PyQt6.QtCore import QObject, QSize, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QTextEdit
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition

from exporting.formula_export import export_format_label, is_export_format_available
from localization.manager import translate as tr
from preview.content_preview import build_mixed_content_html
from recognition.error_messages import (
    CANCELED_WORKER_MESSAGE,
    recognition_failure_user_message,
)
from runtime.content_types import normalize_content_type
from runtime.hotkey_config import display_hotkey, normalize_hotkey_or_default
from runtime.webengine_runtime import ensure_webengine_loaded
from ui.notifications import show_user_notice
from ui.predict_result_dialog import show_predict_result_dialog
from ui.theme_tokens import dialog_theme_tokens, is_dark_ui
from ui.window_helpers import show_normal_window

logger = logging.getLogger(f"latexsnipper.{__name__}")
RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS = 10.0


class RecognitionResultController(QObject):
    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        editor: EditorActionsController,
        history: HistoryController,
        models: ModelRuntimeController,
        status: StatusController,
        system_provider: ISystemProvider,
        tasks: RecognitionTaskController,
        tray_icon: Callable[[], QSystemTrayIcon | None],
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.editor = editor
        self.history = history
        self.models = models
        self.status = status
        self.system_provider = system_provider
        self.tasks = tasks
        self.tray_icon = tray_icon
        self._predict_result_dialog = None
        self._next_predict_result_screen_index = None
        self._last_recognition_failure_toast_ts = 0.0
        self._last_recognition_cancel_notice_at = 0.0

    def _clear_predict_result_dialog_ref(self, dialog_obj=None):
        """Clear the result dialog reference only when the callback still targets this window."""
        current = getattr(self, "_predict_result_dialog", None)
        if dialog_obj is None or current is dialog_obj:
            self._predict_result_dialog = None

    def _is_predict_result_dialog_alive(self, dlg) -> bool:
        if dlg is None:
            return False
        try:
            if sip.isdeleted(dlg):
                return False
        except Exception:
            pass
        return True

    def _move_predict_result_dialog_to_screen(
        self, dlg: QDialog, screen_index: int | None
    ) -> None:
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
                handle = self.view.windowHandle()
                if handle is not None:
                    main_screen = handle.screen()
            except Exception:
                main_screen = None
            if main_screen is None:
                try:
                    main_screen = QGuiApplication.screenAt(
                        self.view.frameGeometry().center()
                    )
                except Exception:
                    main_screen = None
            same_screen_as_main = bool(main_screen is screens[idx])
            if (
                self.view.isVisible()
                and (not self.view.isMinimized())
                and same_screen_as_main
            ):
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
            "mathcraft": tr("确认或修改公式："),
            "mathcraft_text": tr("确认或修改文本："),
            "mathcraft_mixed": tr("确认或修改内容："),
        }
        return mode_titles.get(current_mode, tr("确认或修改内容："))

    def _set_predict_result_pin_button_style(self, button, pinned: bool):
        try:
            t = dialog_theme_tokens()
            icon = FluentIcon.UNPIN if pinned else FluentIcon.PIN
            button.setIcon(icon.icon())
            button.setIconSize(QSize(18, 18))
            button.setToolTip(tr("固定为小窗口并保持置顶，再点一次恢复可调整大小"))
            if pinned:
                dark = is_dark_ui()
                bg = "#2f6ea8" if dark else "#3daee9"
                hover = "#3e82c3" if dark else "#5dbff2"
                pressed = "#245a8d" if dark else "#319fd9"
                border = "#4d8dca" if dark else "#2b94cb"
                button.setStyleSheet(
                    f"\n                    QToolButton {{\n                        background: {bg};\n                        color: #ffffff;\n                        border: 1px solid {border};\n                        border-radius: 4px;\n                        padding: 0;\n                    }}\n                    QToolButton:hover {{\n                        background: {hover};\n                        border: 1px solid {border};\n                    }}\n                    QToolButton:pressed {{\n                        background: {pressed};\n                        border: 1px solid {border};\n                    }}\n                    "
                )
            else:
                button.setStyleSheet(
                    f"\n                    QToolButton {{\n                        background: transparent;\n                        color: {t['muted']};\n                        border: 1px solid transparent;\n                        border-radius: 4px;\n                        padding: 0;\n                        min-width: 30px;\n                        min-height: 30px;\n                    }}\n                    QToolButton:hover {{\n                        background: {t['panel_bg']};\n                        border: 1px solid {t['accent']};\n                    }}\n                    QToolButton:pressed {{\n                        background: {t['panel_bg']};\n                    }}\n                    "
                )
        except Exception:
            pass

    def _set_predict_result_native_caption_buttons(
        self, dlg: QDialog, pinned: bool
    ) -> bool:
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
            ws_minimizebox = 131072
            ws_maximizebox = 65536
            if pinned:
                style &= ~ws_minimizebox
                style &= ~ws_maximizebox
            else:
                style &= ~ws_minimizebox
                style |= ws_maximizebox
            user32.SetWindowLongW(hwnd, -16, style)
            flags = 1 | 2 | 4 | 16 | 32
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
            insert_after = -1 if topmost else -2
            flags = 16 | 1 | 2 | 64
            ok = user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags)
            return bool(ok)
        except Exception:
            return False

    def _set_predict_result_transient_owner(self, dlg: QDialog, pinned: bool) -> None:
        """Detach a pinned result from the main window's minimize lifecycle."""
        try:
            dlg.winId()
            handle = dlg.windowHandle()
            if handle is None:
                return
            owner_handle = None if pinned else self.view.windowHandle()
            handle.setTransientParent(owner_handle)
        except Exception:
            pass

    def _set_predict_result_pinned(self, dlg: QDialog, pin_btn, pinned: bool):
        dlg._predict_result_pinned = bool(pinned)
        try:
            if pinned and (not dlg.isMaximized()):
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
        self._set_predict_result_transient_owner(dlg, pinned)
        show_normal_window(dlg)
        self._set_predict_result_native_caption_buttons(dlg, pinned)
        self._set_predict_result_pin_button_style(pin_btn, pinned)
        try:
            pin_btn.setChecked(pinned)
        except Exception:
            pass

    def _try_refresh_predict_result_dialog(
        self, dlg: QDialog, code: str, current_mode: str
    ) -> bool:
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
            show_normal_window(dlg)
            return True
        except Exception:
            return False

    def show_result(
        self, content: str, content_type: str, model_name: str, elapsed: float | None
    ):
        self.tasks.clear_cancellation()
        coordinator = getattr(self, "coordinator", None)
        if coordinator is not None:
            normalized_type = normalize_content_type(content_type)
            mode = (
                "text"
                if normalized_type == "text"
                else "mixed"
                if normalized_type == "markdown"
                else "formula"
            )
            internal_models = {"mathcraft", "mathcraft_text", "mathcraft_mixed"}
            backend = (
                "mathcraft"
                if str(model_name).strip().lower() in internal_models
                else "external"
            )
            coordinator.publish_next_result(content, backend=backend, mode=mode)
        self.status.set_model_status(tr("完成"))
        self.status.set_action_status(tr("识别完成"), auto_clear_ms=3000)
        if elapsed is not None:
            logger.info("识别完成 model=%s time=%ss", model_name, f"{elapsed:.2f}")
        else:
            logger.info("识别完成 model=%s", model_name)
        self.show_confirm_dialog(content, normalize_content_type(content_type))

    def show_confirm_dialog(self, recognized_content: str, content_type: str):
        """Show the recognition result confirmation dialog."""
        result_screen_index = self._next_predict_result_screen_index
        self._next_predict_result_screen_index = None
        code = (recognized_content or "").strip()
        if not code:
            self.status.show_action_status(tr("识别结果为空"), level="warning")
            return
        current_mode = normalize_content_type(content_type)
        old_dialog = getattr(self, "_predict_result_dialog", None)
        if old_dialog is not None and self._try_refresh_predict_result_dialog(
            old_dialog, code, current_mode
        ):
            return
        if old_dialog is not None:
            try:
                old_dialog.close()
            except Exception:
                pass
            self._clear_predict_result_dialog_ref(old_dialog)
        default_export_format = str(
            self.cfg.get("last_export_format", "") or ""
        ).strip()
        if not is_export_format_available(default_export_format):
            default_export_format = ""
        default_export_label = (
            export_format_label(default_export_format) if default_export_format else ""
        )
        self._predict_result_dialog = show_predict_result_dialog(
            parent=self.view,
            code=code,
            current_mode=current_mode,
            result_screen_index=result_screen_index,
            mode_title=self._predict_result_mode_title,
            ensure_webengine_loaded=ensure_webengine_loaded,
            build_mixed_html=self._build_mixed_html,
            show_export_menu_for_source=self.editor.show_source_export_menu,
            accept_result=self.accept_recognition_result,
            set_pin_button_style=self._set_predict_result_pin_button_style,
            set_pinned=self._set_predict_result_pinned,
            move_to_screen=self._move_predict_result_dialog_to_screen,
            clear_dialog_ref=self._clear_predict_result_dialog_ref,
            default_export_format=default_export_format,
            default_export_label=default_export_label,
            quick_export=lambda format_type, text, dialog: self.editor.export(
                format_type, text, info_parent=dialog
            ),
        )

    def _build_mixed_html(self, content: str) -> str:
        return build_mixed_content_html(content)

    def _should_show_recognition_failure_tray_notification(
        self, now_ts: float | None = None
    ) -> bool:
        try:
            current = float(
                now_ts if now_ts is not None else datetime.datetime.now().timestamp()
            )
            last = float(
                getattr(self, "_last_recognition_failure_toast_ts", 0.0) or 0.0
            )
            if current - last < RECOGNITION_FAILURE_TRAY_COOLDOWN_SECONDS:
                return False
            self._last_recognition_failure_toast_ts = current
            return True
        except Exception:
            return True

    def _show_recognition_failure_notice(self, content: str) -> None:
        visible = False
        try:
            visible = bool(self.view.isVisible() and (not self.view.isMinimized()))
        except Exception:
            pass
        if not visible and self.tray_icon():
            if self._should_show_recognition_failure_tray_notification():
                hotkey = display_hotkey(
                    normalize_hotkey_or_default(
                        self.cfg.get("hotkey", None), sys.platform
                    ),
                    sys.platform,
                )
                try:
                    self.system_provider.show_notification(
                        self.tray_icon(),
                        tr("识别失败"),
                        tr("{content}\n可使用快捷键 {hotkey} 重试。").format(
                            content=content, hotkey=hotkey
                        ),
                        critical=True,
                        timeout_ms=4000,
                    )
                    return
                except Exception:
                    pass
            else:
                return
        if not visible:
            try:
                self.system_provider.activate_window(self.view)
            except Exception:
                pass
        try:
            InfoBar.error(
                title=tr("识别失败"),
                content=content,
                parent=self.view,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
        except Exception as exc:
            logger.warning("无法显示识别失败提示: %s", exc)

    def show_failure(
        self, msg: str, model_name: str, elapsed: float | None, external_model: bool
    ):
        self._next_predict_result_screen_index = None
        canceled = self._is_user_cancelled_recognition_error(msg)
        content = self.failure_content(msg, external_model=external_model)
        coordinator = getattr(self, "coordinator", None)
        if coordinator is not None:
            empty_codes = {
                tr("未识别到公式内容"): "empty_formula",
                tr("未识别到文本内容"): "empty_text",
                tr("未检测到可识别内容"): "empty_content",
            }
            code = (
                "canceled"
                if canceled
                else empty_codes.get(content, "recognition_failed")
            )
            coordinator.fail_next_result(content, code=code)
        if canceled:
            try:
                logger.debug("识别已中断: %s", msg)
            except Exception:
                pass
            self.show_cancelled()
            return
        self.status.set_model_status(tr("失败"))
        if elapsed is not None:
            logger.error(
                "识别失败 model=%s time=%ss err=%s", model_name, f"{elapsed:.2f}", msg
            )
        else:
            logger.error("识别失败 model=%s err=%s", model_name, msg)
        self._show_recognition_failure_notice(content)

    def accept_recognition_result(self, dialog, te: QTextEdit):
        t = te.toPlainText().strip()
        if not t:
            if bool(getattr(dialog, "_predict_result_pinned", False)):
                self.status.show_action_status(
                    tr("识别结果为空"), level="warning", parent=dialog
                )
                return
            dialog.reject()
            return
        try:
            try:
                pyperclip.copy(t)
            except Exception:
                QApplication.clipboard().setText(t)
        except Exception as e:
            self.status.show_action_status(
                tr("复制失败：{error}").format(error=e), level="error", parent=dialog
            )
            return
        try:
            content_type = normalize_content_type(dialog._predict_result_mode)
            self.history.add_history_record(t, content_type=content_type)
        except Exception as e:
            self.status.show_action_status(
                tr("写入历史失败：{error}").format(error=e),
                level="error",
                parent=dialog,
            )
            return
        if bool(getattr(dialog, "_predict_result_pinned", False)):
            self.status.set_action_status(tr("已确认并复制到剪贴板"), parent=dialog)
            try:
                dialog.raise_()
                dialog.activateWindow()
            except Exception:
                pass
            return
        dialog.accept()

    def show_busy(self, content: str | None = None) -> None:
        try:
            InfoBar.info(
                title=tr("提示"),
                content=content or tr("正在识别，请稍候"),
                parent=self.view,
                duration=2200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            show_user_notice(tr("提示"), content, self.view)

    def _is_user_cancelled_recognition_error(self, msg: str) -> bool:
        text = str(msg or "").strip().lower()
        if bool(getattr(self.tasks, "cancel_requested", False)):
            return True
        return (
            "cancel" in text
            or "cancelled" in text
            or "canceled" in text
            or (CANCELED_WORKER_MESSAGE in text)
            or (tr("已取消").lower() in text)
            or (tr("已中断").lower() in text)
        )

    def show_cancelled(self, *, reset_cancel_flag: bool = True) -> None:
        if reset_cancel_flag:
            self.tasks.clear_cancellation()
        self.status.set_model_status(tr("已中断"))
        now = time.monotonic()
        if (
            now - float(getattr(self, "_last_recognition_cancel_notice_at", 0.0) or 0.0)
            < 2.5
        ):
            return
        self._last_recognition_cancel_notice_at = now
        try:
            InfoBar.info(
                title=tr("识别已中断"),
                content=tr("已停止当前识别任务，可重新截图或切换识别类型后再试。"),
                parent=self.view,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def failure_content(self, msg: str, *, external_model: bool) -> str:
        return recognition_failure_user_message(
            msg, "external_model" if external_model else "mathcraft"
        )

    def refresh_export_format(self, key):
        dialog = self._predict_result_dialog
        if dialog is not None:
            from exporting.formula_export import export_format_label

            dialog._refresh_quick_export_button(key, export_format_label(key))

    def shutdown(self):
        if self._predict_result_dialog is not None:
            self._predict_result_dialog.close()

    def set_screen(self, index):
        self._next_predict_result_screen_index = index

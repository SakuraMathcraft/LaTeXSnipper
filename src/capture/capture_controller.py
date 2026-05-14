"""Screen capture controller mixin for the main window."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QTimer, Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from backend.platform import ScreenshotConfig
from bootstrap.deps_bootstrap import custom_warning_dialog


class CaptureControllerMixin:
    def start_capture(self):
        if self._capture_start_pending or self.overlay is not None:
            try:
                if self.overlay is not None:
                    self.system_provider.activate_window(self.overlay)
            except Exception:
                pass
            return
        self._last_capture_screen_index = None
        self._next_predict_result_screen_index = None
        self._prepare_predict_result_dialog_for_capture()
        pinned_dialog = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        if not self.isVisible() and pinned_dialog is None:
            self.showMinimized()
        if not self.model:
            self._restore_hidden_unpinned_predict_result_dialog()
            self._restore_predict_result_dialog_visibility()
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        perm = self.screenshot_provider.request_permission()
        if getattr(perm, "state", None) == "denied":
            self._restore_hidden_unpinned_predict_result_dialog()
            self._restore_predict_result_dialog_visibility()
            custom_warning_dialog("权限不足", getattr(perm, "message", "截图权限被拒绝"), self)
            return
        cfg = ScreenshotConfig(
            capture_display_mode=self._get_capture_display_mode(),
            preferred_screen_index=self._get_capture_display_index(),
        )
        hidden_unpinned_dialog = self._hidden_unpinned_predict_result_dialog_for_capture is not None
        self._capture_start_pending = True
        self._capture_waiting_for_hidden_result_window = hidden_unpinned_dialog
        if hidden_unpinned_dialog:
            self._flush_desktop_after_capture_window_hide()
            QTimer.singleShot(220, lambda cfg=cfg: self._begin_capture_overlay(cfg))
        else:
            self._begin_capture_overlay(cfg)

    def _begin_capture_overlay(self, cfg: ScreenshotConfig):
        if not self._capture_start_pending:
            return
        waiting_for_hidden_result = self._capture_waiting_for_hidden_result_window
        self._capture_start_pending = False
        self._capture_waiting_for_hidden_result_window = False
        if self.overlay is not None:
            return
        try:
            if waiting_for_hidden_result:
                self._flush_desktop_after_capture_window_hide()
            self.overlay = self.screenshot_provider.create_overlay(cfg)
            self.overlay.installEventFilter(self)
            self.overlay.selection_done.connect(self.on_capture_done)
            self.system_provider.activate_window(self.overlay)
        except Exception as e:
            self.overlay = None
            QTimer.singleShot(0, self._restore_predict_result_dialog_visibility)
            QTimer.singleShot(0, self._restore_hidden_unpinned_predict_result_dialog)
            custom_warning_dialog("错误", f"截图遮罩启动失败: {e}", self)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self._drag_contains_local_file(event):
                event.acceptProposedAction()
                return True
        if event.type() == QEvent.Type.Drop:
            if self._local_drop_paths(event):
                self.dropEvent(event)
                return True
        if obj is getattr(self, "overlay", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                try:
                    cancel = getattr(obj, "cancel_capture", None)
                    if callable(cancel):
                        cancel()
                    else:
                        obj.close()
                except Exception:
                    pass
                self._capture_start_pending = False
                self._capture_waiting_for_hidden_result_window = False
                self.overlay = None
                QTimer.singleShot(0, self._restore_predict_result_dialog_visibility)
                QTimer.singleShot(0, self._restore_hidden_unpinned_predict_result_dialog)
                self.set_action_status("已取消截图")
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        self._capture_start_pending = False
        self._capture_waiting_for_hidden_result_window = False
        capture_failure_message = ""
        if self.overlay:
            capture_failure_message = str(getattr(self.overlay, "last_capture_failure_message", "") or "").strip()
            screen_index = getattr(self.overlay, "last_capture_screen_index", None)
            self._last_capture_screen_index = int(screen_index) if screen_index is not None else None
            self._next_predict_result_screen_index = self._last_capture_screen_index
            self.overlay.close()
            self.overlay = None
        QTimer.singleShot(0, self._restore_predict_result_dialog_visibility)
        if pixmap is None:
            QTimer.singleShot(0, self._restore_hidden_unpinned_predict_result_dialog)
            if capture_failure_message:
                QTimer.singleShot(0, lambda msg=capture_failure_message: self._show_capture_failure_info(msg))
            return
        if self.is_recognition_busy(source="main"):
            self._restore_hidden_unpinned_predict_result_dialog()
            self._show_recognition_busy_info()
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", f"图片处理失败: {e}", self)
            return
        self._start_predict_with_pil(img)

    def _show_capture_failure_info(self, message: str):
        text = str(message or "").strip()
        if not text:
            return
        try:
            self.system_provider.activate_window(self)
        except Exception:
            try:
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        InfoBar.warning(
            title="截图屏幕不匹配",
            content=text,
            parent=self,
            duration=6200,
            position=InfoBarPosition.TOP,
        )

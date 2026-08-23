"""Screen capture controller mixin for the main window."""

from __future__ import annotations

import ctypes
import os

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import InfoBar, InfoBarPosition

from backend.platform import ScreenshotConfig
from bootstrap.deps_ui import custom_warning_dialog


class CaptureControllerMixin:
    def start_capture(self, preserve_pinned_result: bool = False):
        if self._capture_start_pending or self.overlay is not None:
            try:
                if self.overlay is not None:
                    self.system_provider.activate_window(self.overlay)
            except Exception:
                pass
            return
        self._last_capture_screen_index = None
        self._next_predict_result_screen_index = None
        if not self.model:
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        perm = self.screenshot_provider.request_permission()
        if getattr(perm, "state", None) == "denied":
            custom_warning_dialog("权限不足", getattr(perm, "message", "截图权限被拒绝"), self)
            opener = getattr(self.screenshot_provider, "open_permission_settings", None)
            if callable(opener):
                opener()
            return
        cfg = ScreenshotConfig(
            capture_display_mode=self._get_capture_display_mode(),
            preferred_screen_index=self._get_capture_display_index(),
        )
        windows_changed = self._prepare_windows_for_capture(
            preserve_pinned_result=bool(preserve_pinned_result)
        )
        self._capture_start_pending = True
        self._capture_waiting_for_window_update = windows_changed
        if windows_changed:
            self._flush_desktop_after_capture_window_update()
            QTimer.singleShot(220, lambda cfg=cfg: self._begin_capture_overlay(cfg))
        else:
            self._begin_capture_overlay(cfg)

    def _begin_capture_overlay(self, cfg: ScreenshotConfig):
        if not self._capture_start_pending:
            return
        waiting_for_window_update = self._capture_waiting_for_window_update
        self._capture_start_pending = False
        self._capture_waiting_for_window_update = False
        if self.overlay is not None:
            return
        try:
            if waiting_for_window_update:
                self._flush_desktop_after_capture_window_update()
            self.overlay = self.screenshot_provider.create_overlay(cfg)
            self.overlay.installEventFilter(self)
            self.overlay.selection_done.connect(self.on_capture_done)
            self.system_provider.activate_window(self.overlay)
        except Exception as e:
            self.overlay = None
            custom_warning_dialog("错误", f"截图遮罩启动失败: {e}", self)

    def _prepare_windows_for_capture(self, *, preserve_pinned_result: bool = False) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        changed = False
        widgets = list(app.topLevelWidgets())
        for widget in widgets:
            try:
                if widget is None or widget is self:
                    continue
                if preserve_pinned_result and bool(
                    getattr(widget, "_predict_result_pinned", False)
                ):
                    continue
                if widget.isVisible():
                    widget.hide()
                    changed = True
                if widget.isMinimized():
                    widget.setWindowState(
                        widget.windowState() & ~Qt.WindowState.WindowMinimized
                    )
                    changed = True
            except Exception:
                continue
        try:
            if self.isVisible() and not self.isMinimized():
                self.showMinimized()
                changed = True
        except Exception:
            pass
        return changed

    def _flush_desktop_after_capture_window_update(self) -> None:
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

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self._handle_clipboard_image_paste(event):
            event.accept()
            return True
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
                self._capture_waiting_for_window_update = False
                self.overlay = None
                self.show_action_status("已取消截图", level="info")
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        self._capture_start_pending = False
        self._capture_waiting_for_window_update = False
        capture_failure_message = ""
        if self.overlay:
            capture_failure_message = str(getattr(self.overlay, "last_capture_failure_message", "") or "").strip()
            screen_index = getattr(self.overlay, "last_capture_screen_index", None)
            self._last_capture_screen_index = int(screen_index) if screen_index is not None else None
            self._next_predict_result_screen_index = self._last_capture_screen_index
            self.overlay.close()
            self.overlay = None
        if pixmap is None:
            if capture_failure_message:
                QTimer.singleShot(0, lambda msg=capture_failure_message: self._show_capture_failure_info(msg))
            return
        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
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
            title="截图失败",
            content=text,
            parent=self,
            duration=6200,
            position=InfoBarPosition.TOP,
        )

"""Screen capture controller mixin for the main window."""

from __future__ import annotations

from localization.manager import translate as tr

from PyQt6.QtCore import QEvent, QTimer, Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from platform_services import ScreenshotConfig
from ui.notifications import show_user_notice


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
            show_user_notice(tr("错误"), tr("模型未初始化"), self)
            return
        perm = self.screenshot_provider.request_permission()
        if getattr(perm, "state", None) == "denied":
            message = getattr(perm, "message", tr("截图权限被拒绝"))
            notified = False
            if getattr(self, "tray_icon", None):
                try:
                    self.system_provider.show_notification(
                        self.tray_icon,
                        tr("截图权限不足"),
                        message,
                        critical=True,
                        timeout_ms=5000,
                    )
                    notified = True
                except Exception:
                    pass
            if not notified:
                show_user_notice(tr("权限不足"), message, self)
            opener = getattr(self.screenshot_provider, "open_permission_settings", None)
            if callable(opener):
                opener()
            return
        cfg = ScreenshotConfig(
            capture_display_mode=self._get_capture_display_mode(),
            preferred_screen_index=self._get_capture_display_index(),
        )
        windows_changed = self.capture_window_manager.prepare(
            preserve_pinned_result=bool(preserve_pinned_result)
        )
        self._capture_start_pending = True
        self._capture_waiting_for_window_update = windows_changed
        if windows_changed:
            self.capture_window_manager.flush_desktop()
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
                self.capture_window_manager.flush_desktop()
            self.overlay = self.screenshot_provider.create_overlay(cfg)
            self.overlay.installEventFilter(self)
            self.overlay.selection_done.connect(self.on_capture_done)
            self.system_provider.activate_window(self.overlay)
        except Exception as e:
            self.overlay = None
            self._show_capture_notice(
                tr("截图启动失败"), str(e), level="error", duration=6200
            )

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self._handle_clipboard_image_paste(
            event
        ):
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
        if (
            obj is getattr(self, "overlay", None)
            and event.type() == QEvent.Type.KeyPress
        ):
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
                QTimer.singleShot(
                    0,
                    lambda: self._show_capture_notice(
                        tr("已取消截图"),
                        tr("未创建识别任务。"),
                        level="info",
                        duration=2400,
                    ),
                )
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        self._capture_start_pending = False
        self._capture_waiting_for_window_update = False
        capture_failure_message = ""
        if self.overlay:
            capture_failure_message = str(
                getattr(self.overlay, "last_capture_failure_message", "") or ""
            ).strip()
            screen_index = getattr(self.overlay, "last_capture_screen_index", None)
            self._last_capture_screen_index = (
                int(screen_index) if screen_index is not None else None
            )
            self._next_predict_result_screen_index = self._last_capture_screen_index
            self.overlay.close()
            self.overlay = None
        if pixmap is None:
            if capture_failure_message:
                QTimer.singleShot(
                    0,
                    lambda msg=capture_failure_message: self._show_capture_failure_info(
                        msg
                    ),
                )
            return
        if self.is_recognition_busy(source="main"):
            self._show_capture_notice(
                tr("正在识别"),
                tr("当前已有识别任务，请稍候。"),
                level="info",
                duration=2600,
            )
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
            self._show_capture_notice(
                tr("图片处理失败"), str(e), level="error", duration=5000
            )
            return
        self._start_predict_with_pil(img)

    def _show_capture_notice(
        self,
        title: str,
        message: str,
        *,
        level: str = "warning",
        duration: int = 6200,
    ) -> None:
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
        notifier = {
            "error": InfoBar.error,
            "info": InfoBar.info,
            "success": InfoBar.success,
        }.get(level, InfoBar.warning)
        notifier(
            title=title,
            content=text,
            parent=self,
            duration=duration,
            position=InfoBarPosition.TOP,
        )

    def _show_capture_failure_info(self, message: str):
        self._show_capture_notice(
            title=tr("截图失败"),
            message=message,
        )

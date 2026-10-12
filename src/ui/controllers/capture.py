"""CaptureController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QSystemTrayIcon

    from platform_services.protocols import IScreenshotProvider, ISystemProvider
    from ui.controllers.file_drop import FileInputController
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.recognition import ImageRecognitionController
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from qfluentwidgets import InfoBar, InfoBarPosition

from localization.manager import translate as tr
from platform_services import ScreenshotConfig
from recognition.image_input import image_from_qpixmap
from ui.notifications import show_user_notice


class CaptureController(QObject):
    def __init__(
        self,
        view: MainWindow,
        file_input: FileInputController,
        models: ModelRuntimeController,
        recognition: ImageRecognitionController,
        screenshot_provider: IScreenshotProvider,
        system_provider: ISystemProvider,
        tasks: RecognitionTaskController,
        display_mode: Callable[[], str],
        display_index: Callable[[], int | None],
        tray_icon: Callable[[], QSystemTrayIcon | None],
        can_capture: Callable[[], bool],
    ):
        super().__init__(view)
        self.view = view
        self.file_input = file_input
        self.models = models
        self.recognition = recognition
        self.screenshot_provider = screenshot_provider
        self.system_provider = system_provider
        self.tasks = tasks
        self.display_mode = display_mode
        self.display_index = display_index
        self.tray_icon = tray_icon
        from capture.window_manager import CaptureWindowManager

        self.capture_window_manager = CaptureWindowManager(view)
        self.overlay = None
        self._capture_start_pending = False
        self._capture_waiting_for_window_update = False
        self._last_capture_screen_index = None
        self.can_capture = can_capture

    def start_capture(self, preserve_pinned_result: bool = False):
        if self.tasks.is_busy():
            self._show_capture_notice(
                tr("正在识别"),
                tr("当前已有识别任务，请稍候。"),
                level="info",
                duration=2600,
            )
            return
        if not self.can_capture():
            return
        if self._capture_start_pending or self.overlay is not None:
            try:
                if self.overlay is not None:
                    self.system_provider.activate_window(self.overlay)
            except Exception:
                pass
            return
        self._last_capture_screen_index = None
        if not self.models.model:
            show_user_notice(tr("错误"), tr("模型未初始化"), self.view)
            return
        perm = self.screenshot_provider.request_permission()
        if getattr(perm, "state", None) == "denied":
            message = getattr(perm, "message", tr("截图权限被拒绝"))
            notified = False
            if self.tray_icon():
                try:
                    self.system_provider.show_notification(
                        self.tray_icon(),
                        tr("截图权限不足"),
                        message,
                        critical=True,
                        timeout_ms=5000,
                    )
                    notified = True
                except Exception:
                    pass
            if not notified:
                show_user_notice(tr("权限不足"), message, self.view)
            opener = getattr(self.screenshot_provider, "open_permission_settings", None)
            if callable(opener):
                opener()
            return
        cfg = ScreenshotConfig(
            capture_display_mode=self.display_mode(),
            preferred_screen_index=self.display_index(),
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
        if self.file_input.eventFilter(obj, event):
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
        return False

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
        if self.tasks.is_busy(source="main"):
            self._show_capture_notice(
                tr("正在识别"),
                tr("当前已有识别任务，请稍候。"),
                level="info",
                duration=2600,
            )
            return
        try:
            img = image_from_qpixmap(pixmap)
        except Exception as e:
            self._show_capture_notice(
                tr("图片处理失败"), str(e), level="error", duration=5000
            )
            return
        self.recognition.recognize_image(
            img, screen_index=self._last_capture_screen_index
        )

    def _show_capture_notice(
        self, title: str, message: str, *, level: str = "warning", duration: int = 6200
    ) -> None:
        text = str(message or "").strip()
        if not text:
            return
        try:
            self.system_provider.activate_window(self.view)
        except Exception:
            try:
                self.view.show()
                self.view.raise_()
                self.view.activateWindow()
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
            parent=self.view,
            duration=duration,
            position=InfoBarPosition.TOP,
        )

    def _show_capture_failure_info(self, message: str):
        self._show_capture_notice(title=tr("截图失败"), message=message)

    def shutdown(self):
        self._capture_start_pending = False
        self._capture_waiting_for_window_update = False
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None

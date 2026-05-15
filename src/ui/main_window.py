from __future__ import annotations

from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QBuffer, QIODevice, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMainWindow
from qfluentwidgets import PrimaryPushButton

from capture.capture_controller import CaptureControllerMixin
from preview.preview_controller import PreviewControllerMixin
from recognition.pdf_controller import PdfRecognitionControllerMixin
from recognition.recognition_controller import RecognitionControllerMixin
from ui.app_lifecycle_controller import AppLifecycleMixin
from ui.editor_actions_controller import EditorActionsControllerMixin
from ui.file_drop import FileDropMixin
from ui.history_controller import HistoryControllerMixin
from ui.hotkey_controller import HotkeyControllerMixin
from ui.main_window_setup import MainWindowSetupMixin
from ui.menu_helpers import action_btn_style as _action_btn_style
from ui.model_runtime_controller import ModelRuntimeControllerMixin
from ui.predict_result_controller import PredictResultControllerMixin
from ui.status_controller import StatusControllerMixin
from ui.theme_controller import ThemeControllerMixin
from ui.tray_controller import TrayControllerMixin
from ui.window_openers import WindowOpenersMixin


class MainWindow(
    MainWindowSetupMixin,
    ThemeControllerMixin,
    PreviewControllerMixin,
    FileDropMixin,
    TrayControllerMixin,
    ModelRuntimeControllerMixin,
    StatusControllerMixin,
    EditorActionsControllerMixin,
    HistoryControllerMixin,
    RecognitionControllerMixin,
    PdfRecognitionControllerMixin,
    PredictResultControllerMixin,
    CaptureControllerMixin,
    HotkeyControllerMixin,
    WindowOpenersMixin,
    AppLifecycleMixin,
    QMainWindow,
):
    """Main application window based on QMainWindow."""

    _model_warmup_result_signal = pyqtSignal()
    _preview_latex_render_request = pyqtSignal(str, str)

    def _center_on_startup_screen_once(self) -> None:
        if getattr(self, "_startup_centered_once", False):
            return
        self._startup_centered_once = True
        try:
            from PyQt6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
            if screen is None:
                return
            geo = screen.availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(geo.center())
            top_left = frame.topLeft()
            max_x = geo.right() - frame.width() + 1
            max_y = geo.bottom() - frame.height() + 1
            x = max(geo.left(), min(top_left.x(), max_x))
            y = max(geo.top(), min(top_left.y(), max_y))
            self.move(x, y)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_startup_screen_once()

    def start_post_show_tasks(self):
        """Start deferred tasks after the main window is visible."""
        if getattr(self, "_post_show_tasks_started", False):
            return
        self._post_show_tasks_started = True

        seq = getattr(self, "_pending_hotkey_seq", None)
        if seq:
            QTimer.singleShot(0, lambda seq=seq: self.register_hotkey(seq))

        try:
            if self.model:
                QTimer.singleShot(0, self._warmup_desired_model)
        except Exception:
            pass

    def _apply_primary_buttons(self) -> None:
        """Apply primary button styling."""
        try:
            btns = self.findChildren(PrimaryPushButton)
        except Exception:
            return
        for button in btns or []:
            try:
                button.setStyleSheet(_action_btn_style())
            except Exception:
                pass

    def _safe_call(self, name, fn):
        print(f"[SlotEnter] {name}")
        try:
            fn()
            print(f"[SlotExit] {name}")
        except Exception as e:
            print(f"[SlotError] {name}: {e}")

    def _defer(self, fn):
        QTimer.singleShot(0, fn)

    def _qpixmap_to_pil(self, pixmap):
        buf = QBuffer()
        if not buf.open(QIODevice.OpenModeFlag.ReadWrite):
            raise RuntimeError("QBuffer 打开失败")
        if not pixmap.save(buf, "PNG"):
            raise RuntimeError("QPixmap 保存失败")
        data = bytes(buf.data())
        buf.close()
        return Image.open(BytesIO(data)).convert("RGB")

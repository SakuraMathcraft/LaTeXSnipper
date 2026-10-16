"""Compose the desktop UI and independently owned controllers."""

from __future__ import annotations
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow
from qfluentwidgets import PrimaryPushButton
from localization.manager import translate as tr
from platform_services import PlatformCapabilityRegistry
from recognition.jobs import RecognitionJobCoordinator
from runtime.app_paths import resource_path
from runtime.config_manager import ConfigManager
from runtime.hotkey_config import normalize_hotkey_or_default
from ui.controllers.app_lifecycle import AppLifecycleController
from ui.controllers.automation_api import AutomationApiController
from ui.controllers.capture import CaptureController
from ui.controllers.editor_actions import EditorActionsController
from ui.controllers.file_drop import FileInputController
from ui.controllers.history import HistoryController
from ui.controllers.hotkey import HotkeyController
from ui.controllers.model_runtime import ModelRuntimeController
from ui.controllers.onboarding import OnboardingController
from ui.controllers.pdf import PdfRecognitionController
from ui.controllers.predict_result import RecognitionResultController
from ui.controllers.preview import PreviewController
from ui.controllers.recognition import ImageRecognitionController
from ui.controllers.status import StatusController
from ui.controllers.tasks import RecognitionTaskController
from ui.controllers.theme import ThemeController
from ui.controllers.tray import TrayController
from ui.controllers.windows import WindowController
from ui.main_window_layout import (
    DEFAULT_MAIN_WINDOW_SIZE,
    adjust_main_window_size,
    build_main_window_layout,
)
from ui.menu_helpers import action_btn_style
from ui.settings_context import SettingsContext


class MainWindow(QMainWindow):
    def __init__(self, startup_progress=None):
        super().__init__()
        self.lifecycle = None
        self.theme = None
        self._startup_centered_once = False
        self._post_show_tasks_started = False
        self.cfg = ConfigManager()
        self.setWindowTitle(tr("LaTeXSnipper"))
        self.resize(*DEFAULT_MAIN_WINDOW_SIZE)
        self.setMinimumSize(*DEFAULT_MAIN_WINDOW_SIZE)
        self.icon = QIcon(resource_path("assets/icon.ico"))
        self.setWindowIcon(self.icon)
        if startup_progress is not None:
            startup_progress(tr("初始化识别与预览..."))
        build_main_window_layout(self, self.cfg)
        self.platform_registry = PlatformCapabilityRegistry(parent=self)
        providers = self.platform_registry.create()
        notification_parent = lambda: self.windows.notification_parent()
        self.tasks = RecognitionTaskController(
            self, lambda: self.windows.handwriting_busy()
        )
        self.models = ModelRuntimeController(
            self,
            self.cfg,
            self.tasks,
            notice=lambda *a, **k: self.status.show_action_status(*a, **k),
            notification_parent=notification_parent,
        )
        self.status = StatusController(self, self.cfg, self.models, notification_parent)
        self.preview = PreviewController(
            self, self.status, label_for=lambda text: self.history.label_for(text)
        )
        self.editor = EditorActionsController(self, self.cfg, self.status)
        self.coordinator = RecognitionJobCoordinator(
            self.models.model, external_config_provider=self.models.external_config
        )
        self.windows = WindowController(
            self,
            self.cfg,
            self.models,
            self.preview,
            self.status,
            providers.system,
            self.editor,
            lambda: SettingsContext(
                self.cfg,
                self.models,
                self.status,
                self.theme,
                self.lifecycle,
                self.automation_api,
            ),
            self.tasks,
            self.coordinator,
        )
        self.theme = ThemeController(self, self.cfg, self.preview, self.windows)
        self.history = HistoryController(
            self,
            self.cfg,
            self.editor,
            self.preview,
            self.status,
            self.theme,
            self.windows,
        )
        self.windows.initialize_favorites(self.history)
        self.results = RecognitionResultController(
            self,
            self.cfg,
            self.editor,
            self.history,
            self.models,
            self.status,
            providers.system,
            self.tasks,
            tray_icon=lambda: self.tray.tray_icon,
        )
        self.recognition = ImageRecognitionController(
            self, self.coordinator, self.models, self.results, self.status, self.tasks
        )
        self.pdf = PdfRecognitionController(
            self, self.coordinator, self.models, self.results, self.status, self.tasks
        )
        self.file_input = FileInputController(self, self.pdf, self.recognition)
        self.capture = CaptureController(
            self,
            self.file_input,
            self.models,
            self.recognition,
            providers.screenshot,
            providers.system,
            self.tasks,
            display_mode=lambda: self.tray.display_mode(),
            display_index=lambda: self.tray.display_index(),
            tray_icon=lambda: self.tray.tray_icon,
            can_capture=lambda: not self.onboarding.active,
        )
        self.hotkey = HotkeyController(
            self, self.cfg, self.capture, providers.hotkey, self.status
        )
        self.tray = TrayController(
            self,
            self.cfg,
            self.capture,
            self.status,
            providers.system,
            self.windows,
            quit_application=lambda: self.lifecycle.truly_exit(),
        )
        self.automation_api = AutomationApiController(self.cfg, self.coordinator, self)
        self.lifecycle = AppLifecycleController(
            self,
            self.capture,
            self.file_input,
            providers.system,
            self.tray,
            self.windows,
            shutdown_actions=(
                self.models.cancel_warmup,
                self.automation_api.shutdown,
                lambda: self.coordinator.stop(wait=False),
                self.models.stop_worker,
                self.tasks.shutdown,
                self.models.shutdown,
                self.preview.shutdown,
                self.capture.shutdown,
                self.pdf.shutdown,
                self.windows.shutdown,
                self.results.shutdown,
                self.history.save_history,
                self.theme.shutdown,
                self.hotkey.shutdown,
                self.tray.shutdown,
                self.cfg.save,
            ),
        )
        self._connect_controllers(providers)
        self.onboarding = OnboardingController(
            self, self.cfg, self.models, self.status, self.hotkey
        )
        self._connect_actions()
        self.history.load_history()
        self.history.update_history_ui()
        self.status.sync_model_status()
        self.theme.apply_mode(self.theme._theme_mode, refresh_preview=False)
        self.theme.apply_styles(force=True)
        for button in self.findChildren(PrimaryPushButton):
            button.setStyleSheet(action_btn_style())
        adjust_main_window_size(self)
        self.tray.connect_tray_activation()
        self.tray.update_tray_menu()
        self.tray.update_tray_tooltip()
        self.lifecycle.install_platform_lifecycle_hooks()
        from PyQt6.QtWidgets import QApplication

        QApplication.instance().aboutToQuit.connect(self.lifecycle.shutdown)

    def _connect_controllers(self, providers):
        self.models.status_changed.connect(self.status.set_model_status)
        self.models.selection_changed.connect(self.windows.refresh_model_selection)
        self.models.settings_requested.connect(self.windows.open_settings)
        self.models.cancel_requested.connect(self._cancel_recognition_for_mode_change)
        self.models.model.status_signal.connect(self.status.show_status_message)
        self.editor.export_format_changed.connect(self.results.refresh_export_format)
        self.hotkey.changed.connect(self.tray.update_tray_menu)
        self.hotkey.changed.connect(self.tray.update_tray_tooltip)
        self.tasks.changed.connect(self.pdf.task_state_changed)
        if providers.hotkey.activated is not None:
            providers.hotkey.activated.connect(self.hotkey.on_hotkey_triggered)

    def _cancel_recognition_for_mode_change(self):
        if self.tasks.cancel():
            self.results.show_cancelled(reset_cancel_flag=False)

    def _connect_actions(self):
        actions = (
            (self.capture_button, self.capture.start_capture),
            (self.onboarding_button, self.onboarding.start),
            (self.history_order_button, self.history.toggle_history_order),
            (self.clear_history_button, self.history.clear_history),
            (self.change_key_button, self.hotkey.set_shortcut),
            (self.show_fav_button, self.windows.open_favorites),
            (self.settings_button, self.windows.open_settings),
            (self.upload_image_btn, self.recognition.select_image),
            (self.upload_pdf_btn, self.pdf.select_pdf),
            (self.copy_editor_btn, self.editor.copy_content),
            (self.export_btn, self.editor.show_export_menu),
            (self.handwriting_btn, self.windows.open_handwriting_window),
            (self.clear_preview_btn, self.preview.clear),
        )
        for button, action in actions:
            button.clicked.connect(lambda _checked=False, action=action: action())
        for widget in (self, *self.drop_targets):
            self.file_input._enable_file_drop_target(widget)

    def start_post_show_tasks(self):
        if self._post_show_tasks_started:
            return
        self._post_show_tasks_started = True
        seq = normalize_hotkey_or_default(self.cfg.get("hotkey"), sys.platform)
        QTimer.singleShot(0, self.onboarding.start_automatically)
        QTimer.singleShot(0, lambda: self.hotkey.register_hotkey(seq))
        QTimer.singleShot(0, self.models.warmup_selected)
        QTimer.singleShot(
            0, self.automation_api.apply_automation_api_startup_preference
        )

    def showEvent(self, event):
        super().showEvent(event)
        if not self._startup_centered_once:
            self._startup_centered_once = True
            screen = self.screen()
            if screen is not None:
                frame = self.frameGeometry()
                frame.moveCenter(screen.availableGeometry().center())
                self.move(frame.topLeft())

    def event(self, event):
        if getattr(self, "theme", None) is not None:
            self.theme.handle_event(event)
        return super().event(event)

    def closeEvent(self, event):
        if self.lifecycle is not None:
            self.lifecycle.closeEvent(event)
        else:
            super().closeEvent(event)

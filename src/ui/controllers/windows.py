"""WindowController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from platform_services.protocols import ISystemProvider
    from recognition.jobs import RecognitionJobCoordinator
    from runtime.config_manager import ConfigManager
    from ui.controllers.editor_actions import EditorActionsController
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.preview import PreviewController
    from ui.controllers.status import StatusController
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
    from ui.settings_context import SettingsContext
import logging

from PyQt6.QtCore import QObject

from handwriting import HandwritingWindow
from localization.manager import translate as tr
from recognition.model_policy import (
    is_internal_document_model,
    resolve_document_recognition_model,
)
from runtime.content_types import FORMULA_CONTENT_TYPE, content_type_for_external_output
from ui.settings_window import SettingsWindow
from ui.window_helpers import show_normal_window

logger = logging.getLogger(f"latexsnipper.{__name__}")


class WindowController(QObject):
    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        models: ModelRuntimeController,
        preview: PreviewController,
        status: StatusController,
        system_provider: ISystemProvider,
        editor: EditorActionsController,
        settings_context: Callable[[], SettingsContext],
        tasks: RecognitionTaskController,
        coordinator: RecognitionJobCoordinator,
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.models = models
        self.preview = preview
        self.status = status
        self.system_provider = system_provider
        self.editor = editor
        self.settings_context = settings_context
        self.tasks = tasks
        self.coordinator = coordinator
        self.settings_window = None
        self.handwriting_window = None
        self.workbench_window = None
        self.favorites_window = None

    def open_settings(self):
        if self.settings_window and self.settings_window.isVisible():
            try:
                if hasattr(self.settings_window, "apply_theme_styles"):
                    self.settings_window.apply_theme_styles(force=True)
            except Exception:
                pass
            show_normal_window(self.settings_window)
            return
        if not self.settings_window:
            self.settings_window = SettingsWindow(
                self.view, context=self.settings_context()
            )
            self.settings_window.model_changed.connect(self.models.select_model)
            self.settings_window.destroyed.connect(
                lambda: setattr(self, "settings_window", None)
            )
        show_normal_window(self.settings_window)
        try:
            if hasattr(self.settings_window, "apply_theme_styles"):
                self.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass

    def open_favorites(self):
        fav = self.favorites_window
        show_normal_window(fav)

    def _on_workbench_insert(self, latex: str):
        text = (latex or "").strip()
        if text == "__LOAD_FROM_MAIN__":
            text = self.view.latex_editor.toPlainText().strip()
            if not text:
                if getattr(self, "workbench_window", None):
                    self.workbench_window.show_info(
                        tr("当前无内容"), tr("主编辑器为空，没有可载入的公式")
                    )
                return
            self.workbench_window.set_latex(text)
            self.workbench_window.show_success(
                tr("已载入"), tr("主编辑器内容已载入数学工作台")
            )
            return
        if not text:
            if getattr(self, "workbench_window", None):
                self.workbench_window.show_info(
                    tr("当前无内容"), tr("数学工作台为空，没有可写回的内容")
                )
            return
        self.view.latex_editor.setPlainText(text)
        self.preview.render_latex_in_preview(text, FORMULA_CONTENT_TYPE)
        self.status.set_action_status(tr("工作台内容已回填到主编辑器"))
        if getattr(self, "workbench_window", None):
            self.workbench_window.show_success(
                tr("已写回"), tr("数学工作台内容已写回主编辑器")
            )

    def _on_handwriting_insert(self, latex: str, output_mode: str):
        text = (latex or "").strip()
        if not text:
            return
        self.preview.set_source(text, content_type_for_external_output(output_mode))
        self.status.set_action_status(tr("手写识别结果已写入主编辑器"))
        try:
            if self.view.isMinimized():
                self.view.showNormal()
            else:
                self.view.show()
            self.view.raise_()
            self.view.activateWindow()
        except Exception:
            pass

    def open_handwriting_window(self):
        preferred = self.models.preferred_model()
        handwriting_model = resolve_document_recognition_model(preferred)
        self.status.sync_model_status()
        if not self.models.model and handwriting_model != "external_model":
            self.status.show_action_status(tr("模型未初始化"), level="error")
            return
        if handwriting_model == "external_model" and (
            not self.models.external_configured()
        ):
            self.models.show_external_configuration()
            return
        if getattr(self, "handwriting_window", None):
            show_normal_window(self.handwriting_window)
            self._warmup_handwriting_model_async(handwriting_model)
            return
        self.handwriting_window = HandwritingWindow(
            self.models.model,
            models=self.models,
            coordinator=self.coordinator,
            tasks=self.tasks,
            owner=self.view,
            parent=None,
        )
        self.handwriting_window.latexInserted.connect(self._on_handwriting_insert)
        self.handwriting_window.destroyed.connect(
            lambda: setattr(self, "handwriting_window", None)
        )
        show_normal_window(self.handwriting_window)
        self._warmup_handwriting_model_async(handwriting_model)

    def _warmup_handwriting_model_async(self, model):
        if is_internal_document_model(model):
            self.models.ensure_warmup(preferred_model=model, update_preference=False)

    def open_workbench(self):
        if not getattr(self, "workbench_window", None):
            from editor.workbench_window import WorkbenchWindow

            self.workbench_window = WorkbenchWindow(
                self.view, on_insert_latex=self._on_workbench_insert
            )
            self.workbench_window.destroyed.connect(
                lambda: setattr(self, "workbench_window", None)
            )
            self.workbench_window.apply_theme_styles(force=True)
        current = self.view.latex_editor.toPlainText().strip()
        if current:
            self.workbench_window.set_latex(current)
        show_normal_window(self.workbench_window)

    def show_window(self):
        self.system_provider.activate_window(self.view)
        self.status.set_action_status(tr("主窗口已显示"))

    def notification_parent(self):
        window = self.settings_window
        return window if window is not None and window.isVisible() else self.view

    def refresh_model_selection(self):
        if self.settings_window is not None:
            self.settings_window.update_model_selection()

    def handwriting_busy(self):
        window = self.handwriting_window
        return bool(
            window is not None and window.isVisible() and window.is_recognizing_busy()
        )

    def shutdown(self):
        self.favorites_window.save_favorites()
        for window in (
            self.handwriting_window,
            self.workbench_window,
            self.favorites_window,
        ):
            if window is not None:
                window.close()

    def initialize_favorites(self, history):
        from ui.favorites_window import FavoritesWindow
        from ui.window_helpers import select_existing_directory_with_icon

        self.favorites_window = FavoritesWindow(
            self.cfg,
            history=history,
            preview=self.preview,
            status=self.status,
            export_formula=self.editor.export,
            parent=self.view,
            select_export_directory=select_existing_directory_with_icon,
        )

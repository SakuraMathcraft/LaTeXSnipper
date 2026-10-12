"""ImageRecognitionController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recognition.jobs import RecognitionJobCoordinator
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.predict_result import RecognitionResultController
    from ui.controllers.status import StatusController
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QObject

from localization.manager import translate as tr
from recognition.error_messages import translate_image_input_error
from recognition.external_workers import ExternalModelWorker
from recognition.image_input import ImageInputError, image_from_path
from recognition.workers import PredictionWorker
from runtime.content_types import (
    content_type_for_external_output,
    content_type_for_mathcraft,
)
from ui.controllers.file_drop import file_kind, image_extensions, image_patterns
from ui.notifications import show_user_notice
from ui.window_helpers import select_open_file_with_icon as _select_open_file_with_icon


class ImageRecognitionController(QObject):
    def __init__(
        self,
        view: MainWindow,
        coordinator: RecognitionJobCoordinator,
        models: ModelRuntimeController,
        results: RecognitionResultController,
        status: StatusController,
        tasks: RecognitionTaskController,
    ):
        super().__init__(view)
        self.view = view
        self.coordinator = coordinator
        self.models = models
        self.results = results
        self.status = status
        self.tasks = tasks

    def recognize_image(
        self,
        img: Image.Image,
        external_prompt_template: str | None = None,
        *,
        screen_index=None,
    ):
        if self.tasks.is_busy(source="main"):
            self.results.show_busy()
            return
        self.results.set_screen(screen_index)
        if (
            self.models.current_model == "external_model"
            or self.models.preferred_model() == "external_model"
        ):
            self._start_external_predict_with_pil(
                img, external_prompt_template=external_prompt_template
            )
            return
        if not self.models.model:
            show_user_notice(tr("错误"), tr("模型未初始化"), self.view)
            return
        if self.tasks.thread and self.tasks.thread.isRunning():
            show_user_notice(tr("错误"), tr("前一识别线程尚未结束"), self.view)
            return
        preferred = self.models.preferred_model()
        if preferred != self.models.current_model:
            self.models.select_current(preferred)
        if self.models.model and (not self.models.model.is_model_ready(preferred)):
            token = self.tasks.prepare()
            self.status.set_model_status(tr("预热中"))
            self.status.show_action_status(
                tr("模型预热中，完成后将自动开始识别"), level="info", auto_clear_ms=2200
            )
            self.models.ensure_warmup(
                preferred_model=preferred,
                on_ready=lambda: self._warmup_ready(
                    token, img, external_prompt_template, screen_index
                ),
                on_fail=lambda message: self._warmup_failed(token, message, preferred),
            )
            return
        active_model = self.models.current_model
        self.status.set_model_status(tr("识别中..."))
        worker = PredictionWorker(self.coordinator, img, active_model)
        self.tasks.start(
            worker, self._on_internal_predict_ok, self._on_internal_predict_fail
        )

    def _start_external_predict_with_pil(
        self, img: Image.Image, external_prompt_template: str | None = None
    ):
        if self.tasks.thread and self.tasks.thread.isRunning():
            show_user_notice(tr("错误"), tr("前一识别线程尚未结束"), self.view)
            return
        config = self.models.external_config()
        one_shot_template = str(external_prompt_template or "").strip()
        if one_shot_template:
            config.prompt_template = one_shot_template
        if not self.models.external_configured():
            self.models.show_external_configuration()
            return
        self.models.select_current("external_model")
        self.status.set_model_status(tr("外部模型识别中..."))
        worker = ExternalModelWorker(self.coordinator, config, img)
        self.tasks.start(
            worker, self._on_external_predict_ok, self._on_external_predict_fail
        )

    def select_image(self):
        """Upload an image and recognize formulas or text."""
        patterns = image_patterns()
        filter_ = tr("图片文件 ({patterns})").format(patterns=" ".join(patterns))
        file_path, _ = _select_open_file_with_icon(
            self.view,
            tr("选择图片"),
            "",
            tr("{images};;所有文件 (*.*)").format(images=filter_),
        )
        if not file_path:
            return
        self.recognize_file(Path(file_path))

    def recognize_file(self, file_path: str | Path):
        """Recognize a local image file selected by dialog or dropped onto the window."""
        path = Path(file_path)
        if not path.is_file():
            show_user_notice(
                tr("错误"), tr("图片文件不存在: {path}").format(path=path), self.view
            )
            return
        if file_kind(path) != "image":
            formats = ", ".join(image_extensions())
            show_user_notice(
                tr("提示"),
                tr("请拖入或选择图片文件。支持格式：{formats}。").format(
                    formats=formats
                ),
                self.view,
            )
            return
        if self.tasks.is_busy(source="main"):
            self.results.show_busy()
            return
        if not self.models.model and self.models.preferred_model() != "external_model":
            show_user_notice(tr("错误"), tr("模型未初始化"), self.view)
            return
        try:
            img = image_from_path(path)
        except ImageInputError as exc:
            show_user_notice(
                tr("错误"),
                tr("图片加载失败：{error}").format(
                    error=translate_image_input_error(exc.user_message)
                ),
                self.view,
            )
            return
        self.recognize_image(img)

    def _on_external_predict_ok(self, result):
        output_mode = self.tasks.worker.config.resolved_output_mode()
        text = result.best_text(output_mode)
        model_name = self.models.external_display_name(result=result)
        self.results.show_result(
            text,
            content_type_for_external_output(output_mode),
            model_name,
            self.tasks.worker.elapsed,
        )

    def _on_internal_predict_ok(self, text: str) -> None:
        model_name = self.tasks.worker.model_name
        self.results.show_result(
            text,
            content_type_for_mathcraft(model_name),
            model_name,
            self.tasks.worker.elapsed,
        )

    def _on_external_predict_fail(self, msg: str):
        model_name = self.models.external_display_name(config=self.tasks.worker.config)
        self.results.show_failure(
            msg, model_name, self.tasks.worker.elapsed, external_model=True
        )

    def _on_internal_predict_fail(self, msg: str) -> None:
        self.results.show_failure(
            msg,
            self.tasks.worker.model_name,
            self.tasks.worker.elapsed,
            external_model=False,
        )

    def _warmup_ready(self, token, image, template, screen_index):
        if self.tasks.finish_preparation(token):
            self.recognize_image(image, template, screen_index=screen_index)

    def _warmup_failed(self, token, message, model):
        if self.tasks.finish_preparation(token):
            self.results.show_failure(
                tr("模型预热失败: {message}").format(message=message),
                model,
                None,
                external_model=False,
            )

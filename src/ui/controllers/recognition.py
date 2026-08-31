"""Image recognition controller mixin for the main window."""

from __future__ import annotations

from localization.manager import translate as tr

import time
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QThread
from qfluentwidgets import InfoBar, InfoBarPosition

from recognition.external_workers import ExternalModelWorker
from recognition.error_messages import (
    CANCELED_WORKER_MESSAGE,
    recognition_failure_user_message,
    translate_image_input_error,
)
from ui.notifications import show_user_notice
from runtime.content_types import (
    content_type_for_external_output,
    content_type_for_mathcraft,
)
from recognition.image_input import ImageInputError, image_from_path
from ui.window_helpers import select_open_file_with_icon as _select_open_file_with_icon
from recognition.workers import PredictionWorker


class RecognitionControllerMixin:
    def _get_infobar_parent(self):
        try:
            if self.settings_window and self.settings_window.isVisible():
                return self.settings_window
        except Exception:
            pass
        return self

    def _report_startup_progress(self, message: str):
        cb = getattr(self, "_startup_progress", None)
        if not callable(cb):
            return
        try:
            cb(str(message or ""))
        except Exception:
            pass

    def _show_recognition_busy_info(self, content: str | None = None) -> None:
        try:
            InfoBar.info(
                title=tr("提示"),
                content=content or tr("正在识别，请稍候"),
                parent=self,
                duration=2200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            show_user_notice(tr("提示"), content, self)

    def is_recognition_busy(self, source: str = "main") -> bool:
        main_busy = bool(
            getattr(self, "_predict_busy", False)
            or (self.predict_thread and self.predict_thread.isRunning())
            or (self.pdf_predict_thread and self.pdf_predict_thread.isRunning())
        )
        if main_busy:
            return True
        if source != "handwriting":
            try:
                hw = getattr(self, "handwriting_window", None)
                if hw and hasattr(hw, "is_recognizing_busy") and hw.isVisible():
                    return bool(hw.is_recognizing_busy())
            except Exception:
                pass
        return False

    def _cancel_active_recognition_for_mode_switch(self) -> None:
        cancelled = False
        self._recognition_cancel_requested = True
        worker = getattr(self, "predict_worker", None)
        if worker and hasattr(worker, "cancel"):
            try:
                worker.cancel()
                cancelled = True
            except Exception:
                pass
        pdf_worker = getattr(self, "pdf_predict_worker", None)
        if pdf_worker and hasattr(pdf_worker, "cancel"):
            try:
                pdf_worker.cancel()
                cancelled = True
            except Exception:
                pass
        for thread_name in ("predict_thread", "pdf_predict_thread"):
            thread = getattr(self, thread_name, None)
            if thread:
                try:
                    thread.requestInterruption()
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass
        if cancelled:
            self._predict_busy = False
            self.set_model_status(tr("识别已中断"))
            self._show_recognition_cancelled_infobar(reset_cancel_flag=False)

    def _is_user_cancelled_recognition_error(self, msg: str) -> bool:
        text = str(msg or "").strip().lower()
        if bool(getattr(self, "_recognition_cancel_requested", False)):
            return True
        return (
            "cancel" in text
            or "cancelled" in text
            or "canceled" in text
            or CANCELED_WORKER_MESSAGE in text
            or tr("已取消").lower() in text
            or tr("已中断").lower() in text
        )

    def _show_recognition_cancelled_infobar(
        self, *, reset_cancel_flag: bool = True
    ) -> None:
        if reset_cancel_flag:
            self._recognition_cancel_requested = False
        self.set_model_status(tr("已中断"))
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
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def _start_predict_with_pil(
        self, img: Image.Image, external_prompt_template: str | None = None
    ):
        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return
        if (
            self.current_model == "external_model"
            or self._get_preferred_model_for_predict() == "external_model"
        ):
            self._start_external_predict_with_pil(
                img, external_prompt_template=external_prompt_template
            )
            return
        if not self.model:
            show_user_notice(tr("错误"), tr("模型未初始化"), self)
            return
        if self.predict_thread and self.predict_thread.isRunning():
            show_user_notice(tr("错误"), tr("前一识别线程尚未结束"), self)
            return
        preferred = self._get_preferred_model_for_predict()
        if preferred != self.current_model:
            self.current_model = preferred
        if self.model and not self.model.is_model_ready(preferred):
            self.set_model_status(tr("预热中"))
            self.show_action_status(
                tr("模型预热中，完成后将自动开始识别"), level="info", auto_clear_ms=2200
            )
            self._ensure_model_warmup_async(
                preferred_model=preferred,
                on_ready=lambda img=img, template=external_prompt_template: (
                    self._start_predict_with_pil(img, template)
                ),
                on_fail=lambda msg, model=preferred: self.on_predict_fail(
                    tr("模型预热失败: {message}").format(message=msg),
                    model,
                    None,
                    external_model=False,
                ),
            )
            return
        active_model = self.current_model
        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status(tr("识别中..."))

        self.predict_thread = QThread()
        self.predict_worker = PredictionWorker(
            self.model,
            img,
            active_model,
            coordinator=getattr(self, "recognition_coordinator", None),
        )
        self.predict_worker.moveToThread(self.predict_thread)

        def _cleanup():
            self._predict_busy = False
            if self.predict_worker:
                self.predict_worker.deleteLater()
                self.predict_worker = None
            if self.predict_thread:
                self.predict_thread.deleteLater()
                self.predict_thread = None

        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self._on_internal_predict_ok)
        self.predict_worker.failed.connect(self._on_internal_predict_fail)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(_cleanup)
        self.predict_thread.start()

    def _start_external_predict_with_pil(
        self, img: Image.Image, external_prompt_template: str | None = None
    ):
        if self.predict_thread and self.predict_thread.isRunning():
            show_user_notice(tr("错误"), tr("前一识别线程尚未结束"), self)
            return
        config = self._get_external_model_config()
        one_shot_template = str(external_prompt_template or "").strip()
        if one_shot_template:
            config.prompt_template = one_shot_template
        if not self._is_external_model_configured():
            self._open_external_model_settings_with_notice()
            return
        self.current_model = "external_model"
        self.cfg.set("default_model", "external_model")
        self.cfg.set("desired_model", "external_model")
        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status(tr("外部模型识别中..."))
        self.predict_thread = QThread()
        self.predict_worker = ExternalModelWorker(
            config,
            img,
            coordinator=getattr(self, "recognition_coordinator", None),
        )
        self.predict_worker.moveToThread(self.predict_thread)

        def _cleanup():
            self._predict_busy = False
            if self.predict_worker:
                self.predict_worker.deleteLater()
                self.predict_worker = None
            if self.predict_thread:
                self.predict_thread.deleteLater()
                self.predict_thread = None

        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self._on_external_predict_ok)
        self.predict_worker.failed.connect(self._on_external_predict_fail)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(_cleanup)
        self.predict_thread.start()

    def _upload_image_recognition(self):
        """Upload an image and recognize formulas or text."""
        patterns = self._get_supported_image_patterns()
        filter_ = tr("图片文件 ({patterns})").format(patterns=" ".join(patterns))
        file_path, _ = _select_open_file_with_icon(
            self,
            tr("选择图片"),
            "",
            tr("{images};;所有文件 (*.*)").format(images=filter_),
        )
        if not file_path:
            return
        self._recognize_image_file(Path(file_path))

    def _recognize_image_file(self, file_path: str | Path):
        """Recognize a local image file selected by dialog or dropped onto the window."""
        self._next_predict_result_screen_index = None
        path = Path(file_path)
        if not path.is_file():
            show_user_notice(
                tr("错误"), tr("图片文件不存在: {path}").format(path=path), self
            )
            return
        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return
        if (
            not self.model
            and self._get_preferred_model_for_predict() != "external_model"
        ):
            show_user_notice(tr("错误"), tr("模型未初始化"), self)
            return
        try:
            img = image_from_path(path)
        except ImageInputError as exc:
            show_user_notice(
                tr("错误"),
                tr("图片加载失败：{error}").format(
                    error=translate_image_input_error(exc.user_message)
                ),
                self,
            )
            return
        self._start_predict_with_pil(img)

    def _on_external_predict_ok(self, result):
        output_mode = self.predict_worker.config.resolved_output_mode()
        text = result.best_text(output_mode)
        model_name = self._get_external_model_display_name(result=result)
        self.on_predict_ok(
            text,
            content_type_for_external_output(output_mode),
            model_name,
            self.predict_worker.elapsed,
        )

    def _on_internal_predict_ok(self, text: str) -> None:
        model_name = self.predict_worker.model_name
        self.on_predict_ok(
            text,
            content_type_for_mathcraft(model_name),
            model_name,
            self.predict_worker.elapsed,
        )

    def _on_external_predict_fail(self, msg: str):
        model_name = self._get_external_model_display_name(
            config=self.predict_worker.config
        )
        self.on_predict_fail(
            msg, model_name, self.predict_worker.elapsed, external_model=True
        )

    def _on_internal_predict_fail(self, msg: str) -> None:
        self.on_predict_fail(
            msg,
            self.predict_worker.model_name,
            self.predict_worker.elapsed,
            external_model=False,
        )

    def _is_external_recognition_worker(self, worker) -> bool:
        return bool(
            getattr(worker, "config", None)
        ) and worker.__class__.__name__.startswith("ExternalModel")

    def _recognition_failure_content(
        self,
        msg: str,
        *,
        worker_attr: str | None = None,
        external_model: bool | None = None,
    ) -> str:
        is_external = bool(external_model)
        if external_model is None:
            worker = getattr(self, worker_attr or "", None)
            is_external = (
                self._is_external_recognition_worker(worker)
                or getattr(self, "current_model", "") == "external_model"
            )
        backend = "external_model" if is_external else "mathcraft"
        return recognition_failure_user_message(msg, backend)

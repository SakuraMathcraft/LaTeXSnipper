import time
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from recognition.error_messages import (
    CANCELED_WORKER_MESSAGE,
    recognition_error_code_message,
)
from backend.external_model.client import ExternalModelClient
from backend.external_model.schemas import ExternalModelConfig


class ExternalModelWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, config: ExternalModelConfig, image, coordinator: Any | None = None):
        super().__init__()
        self.config = config
        self.image = image
        self.elapsed = None
        self.coordinator = coordinator
        self._job_id: str | None = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self.coordinator is not None and self._job_id:
            try:
                self.coordinator.cancel(self._job_id, principal_id="desktop-ui")
            except Exception:
                pass

    def run(self):
        t0 = time.perf_counter()
        try:
            if self._cancelled:
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            if self.coordinator is None:
                result = ExternalModelClient(self.config).predict(self.image)
            else:
                from recognition.jobs import JobSource, RecognitionItemInput

                job = self.coordinator.submit(
                    [RecognitionItemInput(image=self.image)],
                    principal_id="desktop-ui",
                    source=JobSource.UI,
                    mode={
                        "ocr_formula_v1": "formula",
                        "ocr_text_v1": "text",
                    }.get(self.config.prompt_template, "mixed"),
                    timeout_seconds=self.config.normalized_timeout(),
                    backend="external",
                    external_config=self.config,
                )
                self._job_id = job["id"]
                if self._cancelled:
                    self.coordinator.cancel(self._job_id, principal_id="desktop-ui")
                snapshot = self.coordinator.wait(job["id"], principal_id="desktop-ui", timeout=None)
                item = snapshot["items"][0]
                if item["state"] != "completed":
                    error = item.get("error") or {}
                    raise RuntimeError(
                        recognition_error_code_message(
                            error.get("code"), "external_model"
                        )
                    )
                from backend.external_model.schemas import ExternalModelResult

                text = str(item["text"])
                output_mode = self.config.resolved_output_mode()
                result = ExternalModelResult(
                    text=text,
                    latex=text if output_mode == "latex" else "",
                    markdown=text if output_mode == "markdown" else "",
                    provider=self.config.normalized_provider(),
                    model_name=self.config.normalized_model_name(),
                )
            self.elapsed = time.perf_counter() - t0
            self.finished.emit(result)
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            self.failed.emit(str(e))


class ExternalModelConnectionWorker(QObject):
    finished = pyqtSignal(bool, str)
    failed = pyqtSignal(object)

    def __init__(self, config: ExternalModelConfig):
        super().__init__()
        self.config = config
        self.elapsed = None

    def run(self):
        t0 = time.perf_counter()
        try:
            ok, message = ExternalModelClient(self.config).test_connection()
            self.elapsed = time.perf_counter() - t0
            self.finished.emit(bool(ok), str(message or ""))
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            self.failed.emit(e)

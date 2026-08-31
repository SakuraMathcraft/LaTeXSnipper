"""Recognition worker objects used by the main window."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from localization.manager import translate as tr
from recognition.error_messages import (
    CANCELED_WORKER_MESSAGE,
    EMPTY_CONTENT_MESSAGE,
    EMPTY_FORMULA_MESSAGE,
    EMPTY_RESULT_MESSAGE,
    EMPTY_TEXT_MESSAGE,
    recognition_error_code_message,
)
from recognition.image_input import validated_rgb_image
from recognition.image_preprocess import optimize_mathcraft_input_image
from recognition.jobs import JobSource, RecognitionItemInput, RecognitionJobCoordinator


def _empty_recognition_message(result: dict[str, Any] | None = None) -> str:
    mode = str((result or {}).get("mode") or "").strip().lower()
    if mode == "text":
        return EMPTY_TEXT_MESSAGE
    if mode == "mixed":
        return EMPTY_CONTENT_MESSAGE
    return EMPTY_FORMULA_MESSAGE


class PredictionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_wrapper: Any, image: Image.Image, model_name: str, coordinator: RecognitionJobCoordinator | None = None):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name
        self.coordinator = coordinator
        self._job_id: str | None = None
        self.elapsed = None
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
            if self._cancel_requested():
                self.elapsed = time.perf_counter() - t0
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            if self.coordinator is not None:
                mode = {"mathcraft": "formula", "mathcraft_text": "text", "mathcraft_mixed": "mixed"}.get(
                    self.model_name, "formula"
                )
                job = self.coordinator.submit(
                    [RecognitionItemInput(image=self.image)],
                    principal_id="desktop-ui",
                    source=JobSource.UI,
                    mode=mode,
                    timeout_seconds=300,
                )
                self._job_id = job["id"]
                job = self.coordinator.wait(job["id"], principal_id="desktop-ui", timeout=None)
                self.elapsed = time.perf_counter() - t0
                if job["state"] == "canceled":
                    self.failed.emit(CANCELED_WORKER_MESSAGE)
                    return
                item = job["items"][0]
                if item["state"] != "completed":
                    error = item.get("error") or {}
                    self.failed.emit(
                        recognition_error_code_message(error.get("code"), "mathcraft")
                    )
                    return
                self.finished.emit(str(item["text"]).strip())
                return
            if hasattr(self.model_wrapper, "predict_result"):
                result_obj = self.model_wrapper.predict_result(
                    optimize_mathcraft_input_image(self.image), model_name=self.model_name
                )
                result = str(result_obj.get("text", "") or "").strip()
                if result_obj.get("empty_reason") or not result:
                    self.elapsed = time.perf_counter() - t0
                    self.failed.emit(_empty_recognition_message(result_obj))
                    return
            else:
                result = self.model_wrapper.predict(
                    optimize_mathcraft_input_image(self.image), model_name=self.model_name
                )
            self.elapsed = time.perf_counter() - t0
            if self._cancel_requested():
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            if not result or not result.strip():
                self.failed.emit(EMPTY_RESULT_MESSAGE)
            else:
                self.finished.emit(result.strip())
        except Exception as exc:
            self.elapsed = time.perf_counter() - t0
            if self._cancel_requested():
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            self.failed.emit(str(exc))

    def _cancel_requested(self) -> bool:
        return self._cancelled or QThread.currentThread().isInterruptionRequested()


class PdfPredictWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(
        self,
        model_wrapper: Any,
        pdf_path: str,
        page_indices: list[int],
        model_name: str,
        output_format: str,
        dpi: int = 200,
        coordinator: RecognitionJobCoordinator | None = None,
    ):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.pdf_path = pdf_path
        self.page_indices = [int(index) for index in page_indices if int(index) >= 0]
        self.model_name = model_name
        self.output_format = output_format
        self.dpi = dpi
        self.coordinator = coordinator
        self._cancelled = False
        self._job_id: str | None = None
        self.elapsed = None

    def cancel(self):
        self._cancelled = True
        if self.coordinator is not None and self._job_id:
            try:
                self.coordinator.cancel(self._job_id, principal_id="desktop-pdf")
            except Exception:
                pass

    def run(self):
        t0 = time.perf_counter()

        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

        try:
            import fitz  # PyMuPDF
        except Exception as exc:
            _set_elapsed()
            self.failed.emit(tr("缺少 PyMuPDF 依赖: {error}").format(error=exc))
            return

        try:
            doc = fitz.open(self.pdf_path)
        except Exception as exc:
            _set_elapsed()
            self.failed.emit(tr("PDF 打开失败: {error}").format(error=exc))
            return

        page_count = doc.page_count or 1
        page_indices = [index for index in self.page_indices if 0 <= index < page_count]
        if not page_indices:
            page_indices = [0]
        total = len(page_indices)
        try:
            doc.close()
        except Exception:
            pass

        render_queue = queue.Queue(maxsize=1)
        render_thread = threading.Thread(
            target=lambda: self._render_pages(fitz, page_indices, render_queue),
            name="MathCraftPdfRenderPrefetch",
            daemon=True,
        )
        render_thread.start()

        page_results = []
        try:
            while True:
                if self._cancel_requested():
                    _set_elapsed()
                    self.failed.emit(CANCELED_WORKER_MESSAGE)
                    return
                try:
                    item = render_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                progress_index, page_index, img, image_size = item
                result = self._predict_page(img)
                if self._cancel_requested():
                    _set_elapsed()
                    self.failed.emit(CANCELED_WORKER_MESSAGE)
                    return
                if isinstance(result, dict):
                    result["page_index"] = page_index + 1
                    result.setdefault("image_size", image_size)
                    page_results.append(result)
                self.progress.emit(progress_index + 1, total)
        except Exception as exc:
            _set_elapsed()
            if self._cancel_requested():
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            self.failed.emit(str(exc))
            return

        from recognition.postprocessing.mathcraft_document import compose_mathcraft_markdown_pages

        clean_results = [
            page
            for page in page_results
            if isinstance(page, dict) and (str(page.get("text") or "").strip() or page.get("blocks"))
        ]
        content = compose_mathcraft_markdown_pages(clean_results)
        if not content.strip():
            _set_elapsed()
            self.failed.emit(EMPTY_RESULT_MESSAGE)
            return
        _set_elapsed()
        self.finished.emit(content.strip())

    def _cancel_requested(self) -> bool:
        return self._cancelled or QThread.currentThread().isInterruptionRequested()

    def _put_render_item(self, render_queue: queue.Queue, item) -> bool:
        while not self._cancelled:
            try:
                render_queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def _render_pages(self, fitz, page_indices: list[int], render_queue: queue.Queue) -> None:
        render_doc = None
        try:
            render_doc = fitz.open(self.pdf_path)
            for progress_index, page_index in enumerate(page_indices):
                if self._cancelled:
                    break
                page = render_doc.load_page(page_index)
                pix = page.get_pixmap(dpi=self.dpi, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                if not self._put_render_item(render_queue, (progress_index, page_index, img, [pix.width, pix.height])):
                    return
            self._put_render_item(render_queue, None)
        except Exception as exc:
            self._put_render_item(render_queue, exc)
        finally:
            try:
                if render_doc is not None:
                    render_doc.close()
            except Exception:
                pass

    def _predict_page(self, img: Image.Image) -> dict:
        if self.coordinator is not None:
            mode = {"mathcraft": "formula", "mathcraft_text": "text", "mathcraft_mixed": "mixed"}.get(
                self.model_name, "mixed"
            )
            job = self.coordinator.submit(
                [RecognitionItemInput(image=validated_rgb_image(img))],
                principal_id="desktop-pdf",
                source=JobSource.PDF,
                mode=mode,
                timeout_seconds=600,
                input_type="pdf_page",
            )
            self._job_id = job["id"]
            snapshot = self.coordinator.wait(job["id"], principal_id="desktop-pdf", timeout=None)
            self._job_id = None
            item = snapshot["items"][0]
            if item["state"] != "completed":
                error = item.get("error") or {}
                raise RuntimeError(
                    recognition_error_code_message(error.get("code"), "mathcraft")
                )
            return {"text": item["text"], "mode": mode}
        if hasattr(self.model_wrapper, "predict_result"):
            return self.model_wrapper.predict_result(img, model_name=self.model_name)
        return {"text": self.model_wrapper.predict(img, model_name=self.model_name)}

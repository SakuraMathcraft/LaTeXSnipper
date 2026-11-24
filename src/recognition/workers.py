"""Recognition worker objects used by the main window."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict
from typing import cast

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal

from localization.manager import translate as tr
from mathcraft_ocr.protocol import PdfTextLine
from recognition.error_messages import (
    CANCELED_WORKER_MESSAGE,
    EMPTY_RESULT_MESSAGE,
    recognition_error_code_message,
)
from recognition.image_input import validated_rgb_image
from recognition.jobs import JobSource, RecognitionItemInput, RecognitionJobCoordinator
from recognition.pdf_text import visible_pdf_text
from recognition.postprocessing.mathcraft_document import MathCraftMarkdownDocument

logger = logging.getLogger("latexsnipper.recognition.workers")


class PredictionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        coordinator: RecognitionJobCoordinator,
        image: Image.Image,
        model_name: str | None,
    ):
        super().__init__()
        self.image = image
        self.model_name = model_name
        self.coordinator = coordinator
        self._job_id: str | None = None
        self.elapsed = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._job_id:
            try:
                self.coordinator.cancel(
                    cast(str, self._job_id), principal_id="desktop-ui"
                )
            except Exception:
                pass

    def run(self):
        t0 = time.perf_counter()
        try:
            if self._cancel_requested():
                self.elapsed = time.perf_counter() - t0
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            mode = {
                "mathcraft": "formula",
                "mathcraft_text": "text",
                "mathcraft_mixed": "mixed",
            }.get(self.model_name or "", "formula")
            job = self.coordinator.submit(
                [RecognitionItemInput(image=self.image)],
                principal_id="desktop-ui",
                source=JobSource.UI,
                mode=mode,
                timeout_seconds=300,
            )
            self._job_id = job["id"]
            if self._cancelled:
                self.coordinator.cancel(
                    cast(str, self._job_id), principal_id="desktop-ui"
                )
            job = self.coordinator.wait(
                job["id"], principal_id="desktop-ui", timeout=None
            )
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
        except Exception as exc:
            self.elapsed = time.perf_counter() - t0
            if self._cancel_requested():
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            self.failed.emit(str(exc))

    def _cancel_requested(self) -> bool:
        return self._cancelled


class PdfPredictWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(
        self,
        coordinator: RecognitionJobCoordinator,
        pdf_path: str,
        page_indices: list[int],
        model_name: str,
        output_format: str,
        dpi: int = 200,
    ):
        super().__init__()
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
        if self._job_id:
            try:
                self.coordinator.cancel(
                    cast(str, self._job_id), principal_id="desktop-pdf"
                )
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

        document = MathCraftMarkdownDocument()
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
                progress_index, page_index, img, pdf_text_lines = item
                result = self._predict_page(img, pdf_text_lines)
                if self._cancel_requested():
                    _set_elapsed()
                    self.failed.emit(CANCELED_WORKER_MESSAGE)
                    return
                result["page_index"] = page_index + 1
                result.setdefault("image_size", img.size)
                document.append(result)
                self.progress.emit(progress_index + 1, total)
        except Exception as exc:
            _set_elapsed()
            if self._cancel_requested():
                self.failed.emit(CANCELED_WORKER_MESSAGE)
                return
            self.failed.emit(str(exc))
            return

        content = document.render()
        if not content.strip():
            _set_elapsed()
            self.failed.emit(EMPTY_RESULT_MESSAGE)
            return
        _set_elapsed()
        self.finished.emit(content.strip())

    def _cancel_requested(self) -> bool:
        return self._cancelled

    def _put_render_item(self, render_queue: queue.Queue, item) -> bool:
        while not self._cancelled:
            try:
                render_queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def _render_pages(
        self, fitz, page_indices: list[int], render_queue: queue.Queue
    ) -> None:
        render_doc = None
        try:
            render_doc = fitz.open(self.pdf_path)
            outlines: dict[int, list[tuple[int, str]]] = defaultdict(list)
            use_native_text = self.model_name == "mathcraft_mixed"
            if use_native_text:
                try:
                    for level, title, page_number in render_doc.get_toc():
                        outlines[page_number - 1].append((level, title))
                except (RuntimeError, ValueError) as exc:
                    logger.debug("Could not read PDF outline: %s", exc)
            text_flags = fitz.TEXTFLAGS_RAWDICT & ~(
                fitz.TEXT_PRESERVE_IMAGES
                | fitz.TEXT_CID_FOR_UNKNOWN_UNICODE
                | fitz.TEXT_PRESERVE_LIGATURES
            )
            for progress_index, page_index in enumerate(page_indices):
                if self._cancelled:
                    break
                page = render_doc.load_page(page_index)
                pdf_text_lines = None
                if use_native_text:
                    try:
                        pdf_text_lines = visible_pdf_text(
                            page, text_flags=text_flags, outline=outlines[page_index]
                        )
                    except (RuntimeError, ValueError) as exc:
                        logger.debug(
                            "Could not read text on PDF page %d: %s",
                            page_index + 1,
                            exc,
                        )
                pix = page.get_pixmap(dpi=self.dpi, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if not self._put_render_item(
                    render_queue,
                    (progress_index, page_index, img, pdf_text_lines),
                ):
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

    def _predict_page(
        self, img: Image.Image, pdf_text_lines: list[PdfTextLine] | None
    ) -> dict:
        mode = {
            "mathcraft": "formula",
            "mathcraft_text": "text",
            "mathcraft_mixed": "mixed",
        }.get(self.model_name, "mixed")
        job = self.coordinator.submit(
            [
                RecognitionItemInput(
                    image=validated_rgb_image(img), pdf_text_lines=pdf_text_lines
                )
            ],
            principal_id="desktop-pdf",
            source=JobSource.PDF,
            mode=mode,
            timeout_seconds=600,
            input_type="pdf_page",
        )
        self._job_id = job["id"]
        if self._cancelled:
            self.coordinator.cancel(cast(str, self._job_id), principal_id="desktop-pdf")
        snapshot = self.coordinator.wait(
            job["id"], principal_id="desktop-pdf", timeout=None
        )
        self._job_id = None
        item = snapshot["items"][0]
        if item["state"] != "completed":
            error = item.get("error") or {}
            raise RuntimeError(
                recognition_error_code_message(error.get("code"), "mathcraft")
            )
        return {"text": item["text"], "mode": mode, **(item.get("document") or {})}

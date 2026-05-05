"""Recognition worker objects used by the main window."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class PredictionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_wrapper: Any, image: Image.Image, model_name: str):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name
        self.elapsed = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        t0 = time.perf_counter()
        try:
            if self._cancel_requested():
                self.elapsed = time.perf_counter() - t0
                self.failed.emit("已取消")
                return
            result = self.model_wrapper.predict(self.image, model_name=self.model_name)
            self.elapsed = time.perf_counter() - t0
            if self._cancel_requested():
                self.failed.emit("已取消")
                return
            if not result or not result.strip():
                self.failed.emit("识别结果为空")
            else:
                self.finished.emit(result.strip())
        except Exception as exc:
            self.elapsed = time.perf_counter() - t0
            if self._cancel_requested():
                self.failed.emit("已取消")
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
        max_pages: int,
        model_name: str,
        output_format: str,
        dpi: int = 200,
    ):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.pdf_path = pdf_path
        self.max_pages = max_pages
        self.model_name = model_name
        self.output_format = output_format
        self.dpi = dpi
        self._cancelled = False
        self.elapsed = None

    def cancel(self):
        self._cancelled = True

    def run(self):
        t0 = time.perf_counter()

        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

        try:
            import fitz  # PyMuPDF
        except Exception as exc:
            _set_elapsed()
            self.failed.emit(f"缺少 PyMuPDF 依赖: {exc}")
            return

        try:
            doc = fitz.open(self.pdf_path)
        except Exception as exc:
            _set_elapsed()
            self.failed.emit(f"PDF 打开失败: {exc}")
            return

        total = min(max(self.max_pages, 1), doc.page_count or 1)
        try:
            doc.close()
        except Exception:
            pass

        render_queue = queue.Queue(maxsize=1)
        render_thread = threading.Thread(
            target=lambda: self._render_pages(fitz, total, render_queue),
            name="MathCraftPdfRenderPrefetch",
            daemon=True,
        )
        render_thread.start()

        page_results = []
        try:
            while True:
                if self._cancel_requested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                try:
                    item = render_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                page_index, img, image_size = item
                result = self._predict_page(img)
                if self._cancel_requested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                if isinstance(result, dict):
                    result["page_index"] = page_index + 1
                    result.setdefault("image_size", image_size)
                    page_results.append(result)
                self.progress.emit(page_index + 1, total)
        except Exception as exc:
            _set_elapsed()
            if self._cancel_requested():
                self.failed.emit("已取消")
                return
            self.failed.emit(str(exc))
            return

        from core.mathcraft_document_engine import compose_mathcraft_markdown_pages

        clean_results = [
            page
            for page in page_results
            if isinstance(page, dict) and (str(page.get("text") or "").strip() or page.get("blocks"))
        ]
        content = compose_mathcraft_markdown_pages(clean_results)
        if not content.strip():
            _set_elapsed()
            self.failed.emit("识别结果为空")
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

    def _render_pages(self, fitz, total: int, render_queue: queue.Queue) -> None:
        render_doc = None
        try:
            render_doc = fitz.open(self.pdf_path)
            for page_index in range(total):
                if self._cancelled:
                    break
                page = render_doc.load_page(page_index)
                pix = page.get_pixmap(dpi=self.dpi, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                if not self._put_render_item(render_queue, (page_index, img, [pix.width, pix.height])):
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
        if hasattr(self.model_wrapper, "predict_result"):
            return self.model_wrapper.predict_result(img, model_name=self.model_name)
        return {"text": self.model_wrapper.predict(img, model_name=self.model_name)}

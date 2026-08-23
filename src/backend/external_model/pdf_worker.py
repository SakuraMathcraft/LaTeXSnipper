import time
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from backend.recognition_errors import recognition_error_code_user_message
from .asset_store import PdfAssetStore
from .document_pipeline import ExternalDocumentPipeline
from .mineru_client import MineruClient
from .schemas import ExternalModelConfig


class ExternalModelPdfWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(
        self,
        config: ExternalModelConfig,
        pdf_path: str,
        page_indices: list[int],
        output_format: str,
        dpi: int | None = 200,
        document_mode: str = "document",
        coordinator: Any | None = None,
    ):
        super().__init__()
        self.config = config
        self.pdf_path = pdf_path
        self.page_indices = [int(index) for index in page_indices if int(index) >= 0]
        self.output_format = output_format
        self.dpi = int(dpi) if dpi is not None else None
        self.document_mode = str(document_mode or "document").strip().lower() or "document"
        self._cancelled = False
        self.elapsed = None
        self.structured_result = None
        self.coordinator = coordinator

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self.coordinator is not None:
            try:
                self.coordinator.run_external_operation(self._run_uncoordinated)
            except Exception:
                self.failed.emit(recognition_error_code_user_message("upstream_error", "external_model"))
            return
        self._run_uncoordinated()

    def _run_uncoordinated(self):
        t0 = time.perf_counter()
        asset_store = None

        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

        if self._cancelled:
            _set_elapsed()
            self.failed.emit("已取消")
            return

        if self.config.normalized_provider() == "mineru":
            try:
                page_indices = self.page_indices or [0]
                page_start = min(page_indices)
                page_end = max(page_indices)
                total = page_end - page_start + 1
                asset_store = PdfAssetStore(task_id="latest", overwrite_existing=True)
                pipeline = ExternalDocumentPipeline(self.config, self.output_format, "parse", asset_store=asset_store)
                self.progress.emit(0, total)
                result = MineruClient(self.config).parse_pdf(self.pdf_path, page_start, page_end)
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    asset_store.cleanup()
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                page_result = pipeline.process_result(result, page_start + 1)
                content = pipeline.compose_document([page_result] if page_result else [])
                self.structured_result = pipeline.build_structured_result()
                if not content.strip():
                    asset_store.cleanup()
                    _set_elapsed()
                    self.failed.emit("识别结果为空")
                    return
                self.progress.emit(total, total)
                _set_elapsed()
                self.finished.emit(content.strip())
                return
            except Exception as e:
                if asset_store is not None:
                    asset_store.cleanup()
                _set_elapsed()
                self.failed.emit(str(e))
                return

        if self.dpi is None:
            _set_elapsed()
            self.failed.emit("PDF 渲染 DPI 未设置")
            return

        try:
            import fitz  # PyMuPDF
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"缺少 PyMuPDF 依赖: {e}")
            return

        try:
            from PIL import Image

            from recognition.image_input import validated_rgb_image
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"缺少 Pillow 依赖: {e}")
            return

        try:
            doc = fitz.open(self.pdf_path)
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"PDF 打开失败: {e}")
            return

        asset_store = (
            PdfAssetStore(task_id="latest", overwrite_existing=True)
            if self.document_mode == "parse"
            else None
        )
        pipeline = ExternalDocumentPipeline(self.config, self.output_format, self.document_mode, asset_store=asset_store)
        page_count = doc.page_count or 1
        page_indices = [index for index in self.page_indices if 0 <= index < page_count]
        if not page_indices:
            page_indices = [0]
        total = len(page_indices)
        results = []
        try:
            for progress_index, page_index in enumerate(page_indices):
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    if asset_store is not None:
                        asset_store.cleanup()
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                page = doc.load_page(page_index)
                render_dpi = max(self.dpi, 72)
                pix = page.get_pixmap(dpi=render_dpi, alpha=False)
                image = validated_rgb_image(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
                page_result = pipeline.process_page(image, page_index + 1, self.config.prompt_template)
                if page_result:
                    results.append(page_result)
                self.progress.emit(progress_index + 1, total)
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    if asset_store is not None:
                        asset_store.cleanup()
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
        except Exception as e:
            if asset_store is not None:
                asset_store.cleanup()
            _set_elapsed()
            self.failed.emit(str(e))
            return
        finally:
            try:
                doc.close()
            except Exception:
                pass

        content = pipeline.compose_document(results)
        self.structured_result = pipeline.build_structured_result()
        if not content.strip():
            if asset_store is not None:
                asset_store.cleanup()
            _set_elapsed()
            self.failed.emit("识别结果为空")
            return
        _set_elapsed()
        self.finished.emit(content.strip())

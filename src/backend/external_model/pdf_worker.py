import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

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
        max_pages: int,
        output_format: str,
        dpi: int = 200,
        document_mode: str = "document",
    ):
        super().__init__()
        self.config = config
        self.pdf_path = pdf_path
        self.max_pages = max_pages
        self.output_format = output_format
        self.dpi = dpi
        self.document_mode = str(document_mode or "document").strip().lower() or "document"
        self._cancelled = False
        self.elapsed = None
        self.structured_result = None

    def cancel(self):
        self._cancelled = True

    def run(self):
        t0 = time.perf_counter()
        asset_store = None

        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

        if self.config.normalized_provider() == "mineru":
            try:
                total = max(int(self.max_pages or 1), 1)
                asset_store = PdfAssetStore(task_id="latest", overwrite_existing=True)
                pipeline = ExternalDocumentPipeline(self.config, self.output_format, "parse", asset_store=asset_store)
                self.progress.emit(0, total)
                result = MineruClient(self.config).parse_pdf(self.pdf_path, total)
                page_result = pipeline.process_result(result, 1, "ocr_document_parse_v1")
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

        try:
            import fitz  # PyMuPDF
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"缺少 PyMuPDF 依赖: {e}")
            return

        try:
            from PIL import Image
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
        total = min(max(int(self.max_pages or 1), 1), doc.page_count or 1)
        results = []
        try:
            for i in range(total):
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    if asset_store is not None:
                        asset_store.cleanup()
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=int(max(self.dpi, 72)), alpha=False)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                page_result = pipeline.process_page(image, i + 1, self.config.prompt_template)
                if page_result:
                    results.append(page_result)
                self.progress.emit(i + 1, total)
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

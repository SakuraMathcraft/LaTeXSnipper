import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .document_pipeline import ExternalDocumentPipeline
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

        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

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

        pipeline = ExternalDocumentPipeline(self.config, self.output_format, self.document_mode)
        total = min(max(int(self.max_pages or 1), 1), doc.page_count or 1)
        results = []
        try:
            for i in range(total):
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
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
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
        except Exception as e:
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
            _set_elapsed()
            self.failed.emit("识别结果为空")
            return
        _set_elapsed()
        self.finished.emit(content.strip())

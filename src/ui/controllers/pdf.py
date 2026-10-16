"""PdfRecognitionController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recognition.jobs import RecognitionJobCoordinator
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.predict_result import RecognitionResultController
    from ui.controllers.status import StatusController
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWidgets import QDialog, QInputDialog, QProgressDialog
from qfluentwidgets import ProgressBar

from localization.manager import translate as tr
from recognition.external_pdf_worker import ExternalModelPdfWorker
from recognition.model_policy import EXTERNAL_MODEL, resolve_document_recognition_model
from recognition.workers import PdfPredictWorker
from ui.controllers.file_drop import file_kind
from ui.notifications import show_user_notice
from ui.pdf_options_dialog import prompt_pdf_output_options
from ui.pdf_result_window import PdfResultWindow
from ui.theme_tokens import is_dark_ui
from ui.window_helpers import apply_app_window_icon as _apply_app_window_icon
from ui.window_helpers import select_open_file_with_icon as _select_open_file_with_icon
from ui.window_helpers import select_save_file_with_icon as _select_save_file_with_icon

logger = logging.getLogger(f"latexsnipper.{__name__}")


def parse_pdf_page_range(text: str, total_pages: int) -> tuple[int, int]:
    """Parse a 1-based PDF page or contiguous page range into inclusive bounds."""
    total = max(int(total_pages or 1), 1)
    raw = str(text or "").strip().replace("－", "-").replace("—", "-").replace("–", "-")
    if not raw:
        raise ValueError(tr("请输入页码或页码范围。"))
    parts = [part.strip() for part in raw.split("-")]
    if len(parts) > 2 or any((not part for part in parts)):
        raise ValueError(tr("页码范围格式应为 3 或 3-7。"))
    try:
        start = int(parts[0])
        end = int(parts[1]) if len(parts) == 2 else start
    except ValueError as exc:
        raise ValueError(tr("页码范围只能包含数字和连字符。")) from exc
    if start < 1 or end < 1:
        raise ValueError(tr("页码必须从 1 开始。"))
    if start > end:
        raise ValueError(tr("起始页不能大于结束页。"))
    if end > total:
        raise ValueError(tr("页码不能超过 PDF 总页数 {total}。").format(total=total))
    return (start, end)


class PdfRecognitionController(QObject):
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
        self.pdf_progress = None
        self._pdf_output_format = None
        self._pdf_doc_style = None
        self._pdf_dpi = None
        self._pdf_structured_result = None
        self._pdf_result_window = None
        self._pdf_progress_text = ""

    def _prompt_pdf_output_options(self, recognition_model: str):
        external_cfg = (
            self.models.external_config()
            if recognition_model == EXTERNAL_MODEL
            else None
        )
        return prompt_pdf_output_options(self.view, recognition_model, external_cfg)

    def select_pdf(self):
        """Upload a PDF and recognize it as Markdown or LaTeX document output."""
        file_path, _ = _select_open_file_with_icon(
            self.view, tr("选择 PDF 文件"), "", tr("PDF 文件 (*.pdf);;所有文件 (*.*)")
        )
        if not file_path:
            return
        self.recognize_file(Path(file_path))

    def recognize_file(self, file_path: str | Path):
        """Recognize a local PDF file selected by dialog or dropped onto the window."""
        path = Path(file_path)
        if not path.is_file():
            show_user_notice(
                tr("错误"), tr("PDF 文件不存在: {path}").format(path=path), self.view
            )
            return
        if file_kind(path) != "pdf":
            show_user_notice(tr("提示"), tr("请拖入或选择 PDF 文件。"), self.view)
            return
        recognition_model = resolve_document_recognition_model(
            self.models.preferred_model()
        )
        if not self.models.model and recognition_model != EXTERNAL_MODEL:
            show_user_notice(tr("错误"), tr("模型未初始化"), self.view)
            return
        if recognition_model == EXTERNAL_MODEL and (
            not self.models.external_configured()
        ):
            show_user_notice(
                tr("提示"), tr("外部模型未配置，请先完成必要配置。"), self.view
            )
            return
        try:
            import fitz
        except Exception as e:
            show_user_notice(
                tr("错误"),
                tr("PDF 处理资源不可用: {error}\n请打开应用诊断并修复应用资源。").format(
                    error=e
                ),
                self.view,
            )
            return
        try:
            doc = fitz.open(str(path))
            total_pages = doc.page_count
            doc.close()
        except Exception as e:
            show_user_notice(
                tr("错误"), tr("PDF 打开失败: {error}").format(error=e), self.view
            )
            return
        default_pages = min(total_pages, 5) if total_pages > 0 else 1
        page_dlg = QInputDialog(self.view)
        page_dlg.setWindowTitle(tr("选择页码"))
        page_dlg.setLabelText(
            tr("PDF 共 {total} 页，输入识别页码或范围：").format(total=total_pages)
        )
        page_dlg.setInputMode(QInputDialog.InputMode.TextInput)
        page_dlg.setTextValue(f"1-{default_pages}" if default_pages > 1 else "1")
        page_dlg.setWindowFlags(
            (
                page_dlg.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        page_dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        page_dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        page_dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        page_dlg.setFixedSize(page_dlg.sizeHint())
        _apply_app_window_icon(page_dlg)
        if page_dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        try:
            page_start, page_end = parse_pdf_page_range(
                page_dlg.textValue(), total_pages
            )
        except ValueError as exc:
            show_user_notice(tr("提示"), str(exc), self.view)
            return
        page_indices = list(range(page_start - 1, page_end))
        pages = len(page_indices)
        opts = self._prompt_pdf_output_options(recognition_model)
        if not opts:
            return
        fmt_key, dpi, doc_mode = opts
        self._pdf_output_format = fmt_key
        self._pdf_doc_style = doc_mode
        self._pdf_dpi = dpi
        self._pdf_structured_result = None
        if self.tasks.is_busy(source="main"):
            self.results.show_busy()
            return
        self.status.set_model_status(tr("识别中..."))
        if recognition_model == EXTERNAL_MODEL:
            config = self.models.external_config()
            if doc_mode != "parse":
                config.prompt_template = (
                    "ocr_document_page_v1"
                    if fmt_key == "markdown"
                    else "ocr_document_latex_v1"
                )
            worker = ExternalModelPdfWorker(
                self.coordinator,
                config,
                str(path),
                page_indices,
                fmt_key,
                dpi,
                doc_mode,
            )
        else:
            if dpi is None:
                raise RuntimeError(tr("内置 PDF 识别缺少渲染 DPI"))
            worker = PdfPredictWorker(
                self.coordinator,
                str(path),
                page_indices,
                recognition_model,
                fmt_key,
                dpi,
            )
        progress_text = (
            tr("正在解析 PDF 文档结构...")
            if doc_mode == "parse"
            else tr("正在识别 PDF...")
        )
        self._pdf_progress_text = progress_text
        self.pdf_progress = QProgressDialog(
            progress_text, tr("取消"), 0, pages, self.view
        )
        progress_bar = ProgressBar(self.pdf_progress)
        progress_bar.setRange(0, pages)
        self.pdf_progress.setBar(progress_bar)
        self.pdf_progress.setWindowModality(Qt.WindowModality.NonModal)
        self.pdf_progress.setMinimumDuration(0)
        self.pdf_progress.setWindowFlags(
            (
                self.pdf_progress.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.pdf_progress.setFixedSize(420, 120)
        self.pdf_progress.canceled.connect(self._on_pdf_cancel_requested)
        worker.progress.connect(self._on_pdf_progress)
        self.tasks.start(worker, self._on_pdf_predict_ok, self._on_pdf_predict_fail)
        try:
            self.pdf_progress.show()
        except Exception:
            pass

    def _release_pdf_progress(self):
        pd = getattr(self, "pdf_progress", None)
        self.pdf_progress = None
        if not pd:
            return
        try:
            pd.canceled.disconnect(self._on_pdf_cancel_requested)
        except Exception:
            pass
        try:
            pd.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass
        try:
            pd.hide()
        except Exception:
            pass
        try:
            pd.setParent(None)
        except Exception:
            pass
        try:
            pd.deleteLater()
        except Exception:
            pass
        try:
            self.view.setEnabled(True)
        except Exception:
            pass

    def _on_pdf_progress(self, current: int, total: int):
        if self.pdf_progress:
            try:
                self.pdf_progress.setMaximum(total)
                if total > 0:
                    percent = max(0, min(100, int(current * 100 / total)))
                    self.pdf_progress.setLabelText(
                        f"{self._pdf_progress_text}  {percent}% ({current}/{total})"
                    )
                self.pdf_progress.setValue(current)
            except Exception:
                pass

    def _on_pdf_cancel_requested(self):
        self.tasks.cancel()
        self.models.stop_worker()
        if self.pdf_progress is not None:
            self.pdf_progress.setLabelText(tr("正在取消识别..."))
        self.status.show_action_status(tr("已取消"), level="info", auto_clear_ms=3000)

    def _wrap_document_output(self, content: str, fmt_key: str, style_key: str) -> str:
        from exporting.document_output import wrap_document_output

        return wrap_document_output(content, fmt_key, style_key)

    def _show_document_dialog(
        self, text: str, fmt_key: str, structured_result: dict | None = None
    ):
        if not self._pdf_result_window:
            self._pdf_result_window = PdfResultWindow(
                status_cb=self.status.set_action_status,
                window_icon=self.view.icon,
                select_save_file=_select_save_file_with_icon,
                warning_dialog=show_user_notice,
                is_dark_ui=is_dark_ui,
            )
        self._pdf_result_window.set_content(
            text, fmt_key, structured_result=structured_result
        )
        self._pdf_result_window.show()
        self._pdf_result_window.raise_()
        self._pdf_result_window.activateWindow()

    def _on_pdf_predict_ok(self, content: str):
        self.tasks.clear_cancellation()
        if isinstance(self.tasks.worker, ExternalModelPdfWorker):
            used = self.models.external_display_name(config=self.tasks.worker.config)
        else:
            used = self.tasks.worker.model_name
        self.status.set_model_status(tr("完成"))
        self.status.set_action_status(tr("PDF 识别完成"), auto_clear_ms=3500)
        self._release_pdf_progress()
        elapsed = self.tasks.worker.elapsed
        if elapsed is not None:
            logger.info("PDF 识别完成 model=%s time=%ss", used, f"{elapsed:.2f}")
        else:
            logger.info("PDF 识别完成 model=%s", used)
        fmt_key = self._pdf_output_format or "markdown"
        style_key = self._pdf_doc_style or "document"
        structured_result = getattr(
            getattr(self.tasks, "worker", None), "structured_result", None
        )
        self._pdf_structured_result = (
            structured_result if isinstance(structured_result, dict) else None
        )
        doc = self._wrap_document_output(content, fmt_key, style_key)
        if not doc:
            show_user_notice(tr("提示"), tr("识别结果为空"), self.view)
            return
        QTimer.singleShot(
            0,
            lambda d=doc, f=fmt_key, s=self._pdf_structured_result: (
                self._show_document_dialog(d, f, s)
            ),
        )

    def _on_pdf_predict_fail(self, msg: str):
        self._release_pdf_progress()
        if self.results._is_user_cancelled_recognition_error(msg):
            try:
                logger.debug("PDF 识别已中断: %s", msg)
            except Exception:
                pass
            self.results.show_cancelled()
            return
        self.status.set_model_status(tr("失败"))
        if isinstance(self.tasks.worker, ExternalModelPdfWorker):
            used = self.models.external_display_name(config=self.tasks.worker.config)
        else:
            used = self.tasks.worker.model_name
        elapsed = self.tasks.worker.elapsed
        if elapsed is not None:
            logger.error(
                "PDF 识别失败 model=%s time=%ss err=%s", used, f"{elapsed:.2f}", msg
            )
        else:
            logger.error("PDF 识别失败 model=%s err=%s", used, msg)
        content = self.results.failure_content(
            msg, external_model=isinstance(self.tasks.worker, ExternalModelPdfWorker)
        )
        self.results._show_recognition_failure_notice(content)

    def task_state_changed(self):
        if not self.tasks.busy:
            self._release_pdf_progress()

    def shutdown(self):
        self._release_pdf_progress()
        if self._pdf_result_window is not None:
            self._pdf_result_window.close()

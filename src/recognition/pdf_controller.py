"""PDF recognition controller mixin for the main window."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QProgressDialog
from qfluentwidgets import InfoBar, InfoBarPosition

from backend.external_model import ExternalModelPdfWorker
from bootstrap.deps_bootstrap import custom_warning_dialog
from preview.math_preview import is_dark_ui
from ui.pdf_options_dialog import prompt_pdf_output_options
from ui.pdf_result_window import PdfResultWindow
from ui.window_helpers import (
    apply_app_window_icon as _apply_app_window_icon,
    select_open_file_with_icon as _select_open_file_with_icon,
    select_save_file_with_icon as _select_save_file_with_icon,
)
from workers.recognition_workers import PdfPredictWorker


class PdfRecognitionControllerMixin:
    def _model_supports_pdf(self, model_name: str) -> bool:
        m = (model_name or "").lower()
        return m == "mathcraft_mixed" or m == "external_model"

    def _prompt_pdf_output_options(self):
        external_cfg = self._get_external_model_config() if self.current_model == "external_model" else None
        return prompt_pdf_output_options(self, self.current_model, external_cfg)

    def _upload_pdf_recognition(self):
        """Upload a PDF and recognize it as Markdown or LaTeX document output."""
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择 PDF 文件",
            "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)",
        )
        if not file_path:
            return
        self._recognize_pdf_file(Path(file_path))

    def _recognize_pdf_file(self, file_path: str | Path):
        """Recognize a local PDF file selected by dialog or dropped onto the window."""
        self._next_predict_result_screen_index = None
        path = Path(file_path)
        if not path.is_file():
            custom_warning_dialog("错误", f"PDF 文件不存在: {path}", self)
            return
        if self._drop_file_kind(path) != "pdf":
            custom_warning_dialog("提示", "请拖入或选择 PDF 文件。", self)
            return
        if not self.model and self._get_preferred_model_for_predict() != "external_model":
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        preferred = self._get_preferred_model_for_predict()
        try:
            if preferred != self.current_model or (self.model and not self.model.is_model_ready(preferred)):
                self.on_model_changed(preferred)
        except Exception:
            if preferred != self.current_model:
                self.on_model_changed(preferred)
        if self.current_model == "external_model" and not self._is_external_model_configured():
            custom_warning_dialog("提示", "外部模型未配置，请先完成配置并测试连接。", self)
            return
        if self.current_model.startswith("mathcraft") and self.current_model != "mathcraft_mixed":
            from qfluentwidgets import MessageBox
            tip = MessageBox(
                "推荐模式",
                "PDF 识别会使用 MathCraft 混合识别并进行文档整理。\n是否切换并继续？",
                self
            )
            _apply_app_window_icon(tip)
            tip.yesButton.setText("切换并继续")
            tip.cancelButton.setText("取消")
            if tip.exec():
                self.on_model_changed("mathcraft_mixed")
                if not self._model_supports_pdf(self.current_model):
                    custom_warning_dialog("提示", "当前模型仍不支持 PDF 识别。", self)
                    return
            else:
                return
        if not self._model_supports_pdf(self.current_model):
            custom_warning_dialog("提示", "当前模型不支持 PDF 识别。", self)
            return
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            custom_warning_dialog("错误", f"缺少 PyMuPDF 依赖: {e}\n请在依赖环境中安装 pymupdf。", self)
            return
        try:
            doc = fitz.open(str(path))
            total_pages = doc.page_count
            doc.close()
        except Exception as e:
            custom_warning_dialog("错误", f"PDF 打开失败: {e}", self)
            return

        default_pages = min(total_pages, 5) if total_pages > 0 else 1
        page_dlg = QInputDialog(self)
        page_dlg.setWindowTitle("选择页数")
        page_dlg.setLabelText(f"PDF 共 {total_pages} 页，选择要识别的页数：")
        page_dlg.setInputMode(QInputDialog.InputMode.IntInput)
        page_dlg.setIntRange(1, max(total_pages, 1))
        page_dlg.setIntValue(default_pages)
        page_dlg.setIntStep(1)
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
        pages = page_dlg.intValue()

        opts = self._prompt_pdf_output_options()
        if not opts:
            return
        fmt_key, dpi, doc_mode = opts
        self._pdf_output_format = fmt_key
        self._pdf_doc_style = doc_mode
        self._pdf_dpi = dpi
        self._pdf_structured_result = None

        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return

        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status("识别中...")

        self.pdf_predict_thread = QThread()
        if self.current_model == "external_model":
            config = self._get_external_model_config()
            config.output_mode = fmt_key
            config.prompt_template = "ocr_document_parse_v1" if doc_mode == "parse" else "ocr_document_page_v1"
            self.pdf_predict_worker = ExternalModelPdfWorker(
                config,
                str(path),
                pages,
                fmt_key,
                dpi,
                doc_mode,
            )
        else:
            self.pdf_predict_worker = PdfPredictWorker(self.model, str(path), pages, self.current_model, fmt_key, dpi)
        self.pdf_predict_worker.moveToThread(self.pdf_predict_thread)

        progress_text = "正在解析 PDF 文档结构..." if doc_mode == "parse" else "正在识别 PDF..."
        self.pdf_progress = QProgressDialog(progress_text, "取消", 0, pages, self)

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
        self.pdf_predict_worker.progress.connect(self._on_pdf_progress)

        def _cleanup():
            self._predict_busy = False
            self._release_pdf_progress()

            self.pdf_predict_worker = None
            self.pdf_predict_thread = None

        self.pdf_predict_thread.started.connect(self.pdf_predict_worker.run)
        self.pdf_predict_worker.finished.connect(self._on_pdf_predict_ok)
        self.pdf_predict_worker.failed.connect(self._on_pdf_predict_fail)
        self.pdf_predict_worker.finished.connect(self.pdf_predict_thread.quit)
        self.pdf_predict_worker.failed.connect(self.pdf_predict_thread.quit)
        self.pdf_predict_thread.finished.connect(_cleanup)
        self.pdf_predict_thread.start()
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
            app = QApplication.instance()
            if app:
                app.processEvents()
        except Exception:
            pass
        try:

            self.setEnabled(True)
        except Exception:
            pass

    def _on_pdf_progress(self, current: int, total: int):
        if self.pdf_progress:
            try:
                self.pdf_progress.setMaximum(total)
                self.pdf_progress.setValue(current)
            except Exception:
                pass

    def _on_pdf_cancel_requested(self):
        self._recognition_cancel_requested = True
        if self.pdf_predict_worker:
            try:
                self.pdf_predict_worker.cancel()
            except Exception:
                pass
        model = getattr(self, "model", None)
        if model and hasattr(model, "_stop_mathcraft_worker"):
            try:
                model._stop_mathcraft_worker()
            except Exception:
                pass
        if self.pdf_progress:
            try:
                self.pdf_progress.setLabelText("正在取消识别...")
            except Exception:
                pass
        if self.pdf_predict_thread:
            try:
                self.pdf_predict_thread.requestInterruption()
            except Exception:
                pass
        self.set_action_status("已取消", auto_clear_ms=3000)

    def _wrap_document_output(self, content: str, fmt_key: str, style_key: str) -> str:
        from core.pdf_output_contract import wrap_document_output

        return wrap_document_output(content, fmt_key, style_key)

    def _show_document_dialog(self, text: str, fmt_key: str, structured_result: dict | None = None):
        if not self._pdf_result_window:
            self._pdf_result_window = PdfResultWindow(
                status_cb=self.set_action_status,
                window_icon=self.icon,
                select_save_file=_select_save_file_with_icon,
                warning_dialog=custom_warning_dialog,
                is_dark_ui=is_dark_ui,
            )
        self._pdf_result_window.set_content(text, fmt_key, structured_result=structured_result)
        print(f"[DEBUG] PDF 结果窗口打开 length={len(text or '')}")
        self._pdf_result_window.show()
        self._pdf_result_window.raise_()
        self._pdf_result_window.activateWindow()

    def _on_pdf_predict_ok(self, content: str):
        self._recognition_cancel_requested = False
        used = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "pdf_predict_worker", None), "config", None)
                )
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            used = None
        if not used:
            used = getattr(self, "current_model", "mathcraft")
        self.set_model_status("完成")
        self.set_action_status("PDF 识别完成", auto_clear_ms=3500)
        self._release_pdf_progress()
        try:
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] PDF 识别完成 model={used} time={elapsed:.2f}s")
            else:
                print(f"[INFO] PDF 识别完成 model={used}")
        except Exception:
            pass
        fmt_key = self._pdf_output_format or "markdown"
        style_key = self._pdf_doc_style or "document"
        structured_result = getattr(getattr(self, "pdf_predict_worker", None), "structured_result", None)
        self._pdf_structured_result = structured_result if isinstance(structured_result, dict) else None
        doc = self._wrap_document_output(content, fmt_key, style_key)
        if not doc:
            custom_warning_dialog("提示", "识别结果为空", self)
            return

        QTimer.singleShot(0, lambda d=doc, f=fmt_key, s=self._pdf_structured_result: self._show_document_dialog(d, f, s))

    def _on_pdf_predict_fail(self, msg: str):
        self._release_pdf_progress()
        if msg == "已取消" or self._is_user_cancelled_recognition_error(msg):
            try:
                print(f"[INFO] PDF 识别已中断: {msg}")
            except Exception:
                pass
            self._show_recognition_cancelled_infobar()
            return
        self.set_model_status("失败")
        self.set_action_status(f"PDF 识别失败: {msg}", auto_clear_ms=4500)
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "pdf_predict_worker", None), "config", None)
                )
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] PDF 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                print(f"[INFO] PDF 识别失败 model={used} err={msg}")
        except Exception:
            pass

        content = self._recognition_failure_content(msg, worker_attr="pdf_predict_worker")
        self.set_action_status(content, auto_clear_ms=4500)
        try:
            InfoBar.error(
                title="识别失败",
                content=content,
                parent=self,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("错误", content, self)

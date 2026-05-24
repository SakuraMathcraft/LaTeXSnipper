"""Secondary window opener mixin for the main window."""

from __future__ import annotations

import threading

from backend.typst_utils import looks_like_latex_math
from bootstrap.deps_bootstrap import custom_warning_dialog
from core.mathcraft_document_engine import convert_latex_to_typst
from editor.workbench_window import WorkbenchWindow
from exporting.formula_converters import get_current_render_mode, convert_typst_to_latex
from handwriting import HandwritingWindow
from handwriting.model_policy import is_internal_handwriting_model, resolve_handwriting_recognition_model
from ui.settings_window import SettingsWindow


class WindowOpenersMixin:
    def open_settings(self):
        if self.settings_window and self.settings_window.isVisible():
            try:
                if hasattr(self.settings_window, "apply_theme_styles"):
                    self.settings_window.apply_theme_styles(force=True)
            except Exception:
                pass
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if not self.settings_window:
            self.settings_window = SettingsWindow(self)
            self.settings_window.model_changed.connect(self.on_model_changed)
            self.settings_window.render_mode_changed.connect(self._on_render_mode_changed)
            self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
        self.settings_window.show()
        try:
            if hasattr(self.settings_window, "apply_theme_styles"):
                self.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def open_favorites(self):
        fav = self._ensure_favorites_window()
        fav.show()
        fav.raise_()
        fav.activateWindow()

    def _on_workbench_insert(self, latex: str):
        text = (latex or "").strip()
        if text == "__LOAD_FROM_MAIN__":
            text = self.latex_editor.toPlainText().strip()
            if not text:
                if getattr(self, "workbench_window", None):
                    self.workbench_window.show_info("当前无内容", "主编辑器为空，没有可载入的公式")
                return
            # If the main editor contains Typst (Typst mode), convert back
            # to LaTeX so MathLive can understand it.
            if get_current_render_mode() == "typst":
                text = self._normalize_editor_text_for_workbench(text)
            self.workbench_window.set_latex(text)
            self.workbench_window.show_success("已载入", "主编辑器内容已载入数学工作台")
            return
        if not text:
            if getattr(self, "workbench_window", None):
                self.workbench_window.show_info("当前无内容", "数学工作台为空，没有可写回的内容")
            return
        if get_current_render_mode() == "typst":
            # Only convert if the content still looks like LaTeX.
            looks_latex = looks_like_latex_math(text)
            if looks_latex:
                text = convert_latex_to_typst(text)
            if text and not text.startswith("$"):
                text = "$$ " + text + " $$"
        self.latex_editor.setPlainText(text)
        self.render_latex_in_preview(text)
        self.set_action_status("工作台内容已回填到主编辑器")
        if getattr(self, "workbench_window", None):
            self.workbench_window.show_success("已写回", "数学工作台内容已写回主编辑器")

    def _on_handwriting_insert(self, latex: str):
        text = (latex or "").strip()
        if not text:
            return
        if get_current_render_mode() == "typst":
            # Only convert if the content still looks like LaTeX.
            # The handwriting window may have already converted it to Typst.
            looks_latex = looks_like_latex_math(text)
            if looks_latex:
                text = convert_latex_to_typst(text)
            if text and not text.startswith("$"):
                text = "$$ " + text + " $$"
        self._set_editor_text_silent(text)
        try:
            ctype = self._get_preferred_model_for_predict()
            if not ctype:
                ctype = getattr(self, "current_model", "mathcraft")
            self._formula_types[text] = ctype
        except Exception:
            pass
        self._refresh_preview()
        self.set_action_status("手写识别结果已写入主编辑器")
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def open_handwriting_window(self):
        preferred = self._get_preferred_model_for_predict()
        handwriting_model = resolve_handwriting_recognition_model(preferred)
        self._sync_current_model_status_from_preference()
        if not self.model and handwriting_model != "external_model":
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        if handwriting_model == "external_model" and not self._is_external_model_configured():
            custom_warning_dialog("提示", "外部模型未配置，请先完成配置并测试连接。", self)
            self.open_settings()
            return
        if getattr(self, "handwriting_window", None) and self.handwriting_window.isVisible():
            self.handwriting_window.raise_()
            self.handwriting_window.activateWindow()
            self._warmup_handwriting_model_async(handwriting_model)
            return
        self.handwriting_window = HandwritingWindow(self.model, owner=self, parent=None)
        self.handwriting_window.latexInserted.connect(self._on_handwriting_insert)
        self.handwriting_window.destroyed.connect(lambda: setattr(self, "handwriting_window", None))
        self.handwriting_window.show()
        self.handwriting_window.raise_()
        self.handwriting_window.activateWindow()
        self._warmup_handwriting_model_async(handwriting_model)

    def _warmup_handwriting_model_async(self, handwriting_model: str) -> None:
        if not is_internal_handwriting_model(handwriting_model) or not self.model:
            return
        try:
            if self.model.is_model_ready(handwriting_model):
                return
        except Exception:
            pass

        def worker() -> None:
            try:
                self._apply_mathcraft_env()
                self.model._lazy_load_mathcraft(handwriting_model)
            except Exception as exc:
                try:
                    print(f"[WARN] Handwriting MathCraft warmup failed: {exc}", flush=True)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _normalize_editor_text_for_workbench(text: str) -> str:
        """Convert editor text (possibly Typst) to LaTeX for MathLive workbench."""
        import re
        body = text.strip()
        # Strip $$ or $ delimiters
        body = re.sub(r'^\$\$?\s*', '', body)
        body = re.sub(r'\s*\$\$?\s*$', '', body)
        body = body.strip()
        if not body:
            return text
        # If content is already LaTeX, return as-is
        if looks_like_latex_math(body):
            return body
        # Content is Typst - convert back to LaTeX for MathLive
        converted = convert_typst_to_latex(body)
        return converted if converted and converted.strip() else body

    def open_workbench(self):
        if getattr(self, "workbench_window", None) and self.workbench_window.isVisible():
            self.workbench_window.raise_()
            self.workbench_window.activateWindow()
        else:
            from editor.workbench_window import WorkbenchWindow

            self.workbench_window = WorkbenchWindow(None, on_insert_latex=self._on_workbench_insert)
            self.workbench_window.destroyed.connect(lambda: setattr(self, "workbench_window", None))
            self.workbench_window.apply_theme_styles(force=True)
            self.workbench_window.show()
        current = self.latex_editor.toPlainText().strip()
        if current:
            # If the main editor contains Typst, convert to LaTeX so
            # MathLive can understand it on initial load.
            if get_current_render_mode() == "typst":
                current = self._normalize_editor_text_for_workbench(current)
            self.workbench_window.set_latex(current)
        self.workbench_window.raise_()
        self.workbench_window.activateWindow()

    def open_bilingual_reader(self):
        window = getattr(self, "bilingual_pdf_window", None)
        if window is not None:
            try:
                if window.isVisible():
                    window.raise_()
                    window.activateWindow()
                    return
            except RuntimeError:
                pass
            self.bilingual_pdf_window = None
        try:
            from handwriting.bilingual_pdf_window import BilingualPdfWindow

            window = BilingualPdfWindow(cfg=self.cfg, parent=None)
        except Exception as exc:
            custom_warning_dialog("错误", f"双语阅读窗口初始化失败: {exc}", self)
            return
        self.bilingual_pdf_window = window
        window.destroyed.connect(lambda: setattr(self, "bilingual_pdf_window", None))
        window.show()
        window.raise_()
        window.activateWindow()

    def show_window(self):
        self.system_provider.activate_window(self)
        self.set_action_status("主窗口已显示")

    def _open_terminal_from_settings(self, env_key: str | None = None):
        try:
            if not self.settings_window:
                self.settings_window = SettingsWindow(self)
            self.settings_window._open_terminal(env_key=env_key)
        except Exception as e:
            custom_warning_dialog("错误", f"打开终端失败: {e}", self)

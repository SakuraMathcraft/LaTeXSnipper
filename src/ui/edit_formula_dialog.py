"""Edit recognition content with the preview strategy recorded for its type."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QTimer
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout
from qfluentwidgets import BodyLabel

from localization.manager import translate as tr
from preview.content_preview import build_mixed_content_html
from preview.math_preview import build_math_html, get_mathjax_base_url
from runtime.content_types import normalize_content_type
from ui.theme_tokens import dialog_theme_tokens, is_dark_ui
from ui.window_helpers import apply_no_minimize_window_flags

logger = logging.getLogger(f"latexsnipper.{__name__}")


class EditFormulaDialog(QDialog):
    def __init__(self, latex: str, parent=None, *, content_type: str):
        super().__init__(parent)
        self._content_type = normalize_content_type(content_type)
        self.setWindowTitle(tr("编辑"))
        apply_no_minimize_window_flags(self)
        self.resize(700, 500)
        self._theme_is_dark_cached = None

        lay = QVBoxLayout(self)

        self.editor = QTextEdit(self)
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(True)
        self.editor.setPlainText(latex or "")
        self.editor.setMaximumHeight(150)
        lay.addWidget(self.editor)

        preview_label = BodyLabel(tr("实时预览:"))
        lay.addWidget(preview_label)

        self._pending_latex = None
        self.preview_view = None
        if self._content_type == "mathcraft_text":
            self.preview_view = QTextEdit(self)
            self.preview_view.setReadOnly(True)
        else:
            web_view_cls = self._load_webengine_view()
            if web_view_cls is not None:
                self.preview_view = web_view_cls()
        if self.preview_view is not None:
            self.preview_view.setMinimumHeight(150)
            lay.addWidget(self.preview_view, 1)

            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._do_render)
            self.editor.textChanged.connect(self._on_text_changed)
            self._do_render()
        else:
            fallback = QLabel(tr("WebEngine 未加载，无法预览"))
            fallback.setStyleSheet(
                f"color: {dialog_theme_tokens()['muted']}; padding: 20px;"
            )
            lay.addWidget(fallback, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @staticmethod
    def _load_webengine_view():
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            return QWebEngineView
        except Exception:
            return None

    def _apply_theme_styles(self, force: bool = False):
        dark = is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        if self.preview_view is not None:
            self._pending_latex = None
            self._do_render()

    def _build_preview_payload(self, latex: str):
        text = str(latex or "")
        if self._content_type == "mathcraft_mixed":
            return build_mixed_content_html(text), get_mathjax_base_url()
        return build_math_html(text, center_viewport=True), get_mathjax_base_url()

    def event(self, event):
        result = super().event(event)
        try:
            if event.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def _on_text_changed(self):
        if hasattr(self, "_render_timer") and self._render_timer:
            self._render_timer.stop()
            self._render_timer.start(300)

    def _do_render(self):
        if not self.preview_view:
            return
        latex = self.editor.toPlainText()
        if latex == self._pending_latex:
            return
        self._pending_latex = latex
        try:
            if isinstance(self.preview_view, QTextEdit):
                self.preview_view.setPlainText(latex)
            else:
                html, base_url = self._build_preview_payload(latex)
                self.preview_view.setHtml(html, base_url)
        except Exception as exc:
            logger.warning("编辑内容预览渲染失败: %s", exc)

    def closeEvent(self, event):
        try:
            if hasattr(self, "_render_timer") and self._render_timer:
                self._render_timer.stop()
        except Exception:
            pass
        return super().closeEvent(event)

    def value(self) -> str:
        return self.editor.toPlainText().strip()

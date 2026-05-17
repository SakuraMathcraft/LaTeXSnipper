"""Formula edit dialog with live MathJax preview."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, QUrl
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout

from exporting.formula_converters import convert_typst_to_latex, get_current_render_mode
from preview.math_preview import dialog_theme_tokens, is_dark_ui, build_math_html
from runtime.app_paths import get_app_root
from ui.window_helpers import apply_no_minimize_window_flags


class EditFormulaDialog(QDialog):
    def __init__(self, latex: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑")
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

        preview_label = QLabel("实时预览:")
        lay.addWidget(preview_label)

        self._pending_latex = ""
        self.preview_view = None
        web_view_cls = self._load_webengine_view()
        if web_view_cls is not None:
            self.preview_view = web_view_cls()
            self.preview_view.setMinimumHeight(200)
            init_html, init_base_url = self._build_preview_payload(latex or "")
            self.preview_view.setHtml(init_html, init_base_url)
            self._pending_latex = latex or ""
            lay.addWidget(self.preview_view, 1)

            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._do_render)
            self.editor.textChanged.connect(self._on_text_changed)
        else:
            fallback = QLabel("WebEngine 未加载，无法预览")
            fallback.setStyleSheet(f"color: {dialog_theme_tokens()['muted']}; padding: 20px;")
            lay.addWidget(fallback, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
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
            self._pending_latex = ""
            self._do_render()

    def _fallback_local_mathjax_base_url(self):
        candidates = []
        try:
            app_dir = get_app_root()
            if app_dir and str(app_dir).strip():
                candidates.append(Path(app_dir) / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass
        try:
            exe_dir = Path(sys.executable).parent
            candidates.append(exe_dir / "_internal" / "assets" / "MathJax-3.2.2" / "es5")
            candidates.append(exe_dir / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass
        try:
            candidates.append(Path(__file__).resolve().parents[1] / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass

        for es5_dir in candidates:
            try:
                if es5_dir.exists():
                    return QUrl.fromLocalFile(str(es5_dir) + os.sep)
            except Exception:
                pass
        return QUrl()

    def _build_preview_payload(self, latex: str):
        text = str(latex or "").strip()
        # When the render engine is Typst, the dialog content is Typst syntax.
        # Convert Typst → LaTeX so MathJax can render it as a preview.
        if get_current_render_mode() == "typst" and text:
            converted = convert_typst_to_latex(text)
            # If conversion produced a different result, use it; otherwise
            # pass the original (MathJax will show the raw text which is
            # better than nothing).
            if converted and converted != text:
                text = converted
        return build_math_html(text), self._fallback_local_mathjax_base_url()

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
        latex = self.editor.toPlainText().strip()
        if latex == self._pending_latex:
            return
        self._pending_latex = latex
        try:
            html, base_url = self._build_preview_payload(latex)
            self.preview_view.setHtml(html, base_url)
        except Exception as exc:
            print(f"[EditDialog Render] 渲染失败: {exc}")

    def closeEvent(self, event):
        try:
            if hasattr(self, "_render_timer") and self._render_timer:
                self._render_timer.stop()
        except Exception:
            pass
        return super().closeEvent(event)

    def value(self) -> str:
        return self.editor.toPlainText().strip()

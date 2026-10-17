"""PreviewController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ui.controllers.status import StatusController
    from ui.main_window import MainWindow

from PyQt6.QtCore import QObject, QTimer

from localization.manager import translate as tr
from preview.math_preview import get_mathjax_base_url
from preview.smart_preview import (
    build_preview_error_html,
    build_smart_preview_html,
)
from runtime.content_types import FORMULA_CONTENT_TYPE, ContentType


class PreviewController(QObject):
    def __init__(
        self,
        view: MainWindow,
        status: StatusController,
        label_for: Callable[[str], str],
    ):
        super().__init__(view)
        self.view = view
        self.status = status
        self.label_for = label_for
        self._rendered_formulas = []
        self._editor_preview_source = ""
        self._editor_preview_content_type = FORMULA_CONTENT_TYPE
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.refresh)
        view.latex_editor.textChanged.connect(self._on_editor_text_changed)

    def _on_editor_text_changed(self):
        """Handle editor text changes with debounced rendering."""
        text = self.view.latex_editor.toPlainText().strip()
        if text != getattr(self, "_editor_preview_source", ""):
            self._editor_preview_source = text
            self._editor_preview_content_type = FORMULA_CONTENT_TYPE
        if self._render_timer:
            self._render_timer.stop()
            self._render_timer.start(300)

    def set_editor_text(self, text: str) -> None:
        """Set editor text without triggering live rendering."""
        if not self.view.latex_editor:
            return
        if self._render_timer:
            self._render_timer.stop()
        try:
            was_blocked = self.view.latex_editor.blockSignals(True)
            self.view.latex_editor.setPlainText(text)
        finally:
            try:
                self.view.latex_editor.blockSignals(was_blocked)
            except Exception:
                pass

    def render_latex_in_preview(
        self, latex: str, content_type: ContentType, label: str | None = None
    ):
        """Render a LaTeX formula in the preview area."""
        if not self.view.preview_view:
            return
        latex = latex.strip()
        if not latex:
            return
        existing_formulas = [f for f, _, _ in self._rendered_formulas]
        if latex in existing_formulas:
            return
        self._editor_preview_source = latex
        self._editor_preview_content_type = content_type
        if label is None:
            label = self.label_for(latex)
        self._rendered_formulas.insert(0, (latex, label, content_type))
        if len(self._rendered_formulas) > 20:
            self._rendered_formulas = self._rendered_formulas[:20]
        self.refresh()

    def refresh(self):
        """Refresh the preview area using each record type."""
        if not self.view.preview_view:
            return
        all_items = []
        editor_text = self.view.latex_editor.toPlainText().strip()
        existing_formulas = [f for f, _, _ in self._rendered_formulas]
        if editor_text and editor_text not in existing_formulas:
            all_items.append(
                (editor_text, tr("编辑中"), self._editor_preview_content_type)
            )
        all_items.extend(self._rendered_formulas)
        try:
            html = build_smart_preview_html(all_items)
            base_url = get_mathjax_base_url()
            self.view.preview_view.setHtml(html, base_url)
        except Exception as e:
            try:
                self.view.preview_view.setHtml(
                    build_preview_error_html(e), get_mathjax_base_url()
                )
            except Exception:
                pass

    def clear(self):
        """Clear all formulas from the preview area."""
        self._rendered_formulas = []
        self.refresh()
        self.status.set_action_status(tr("已清空预览"))

    def set_source(self, text, content_type):
        self.set_editor_text(text)
        self._editor_preview_source = text
        self._editor_preview_content_type = content_type
        self.refresh()

    def shutdown(self):
        self._render_timer.stop()

    def set_label(self, text, name):
        for i, (formula, label, content_type) in enumerate(self._rendered_formulas):
            if formula == text:
                prefix = label.split(" ", 1)[0] if label.startswith("#") else ""
                self._rendered_formulas[i] = (
                    formula,
                    f"{prefix} {name}".strip(),
                    content_type,
                )
        self.refresh()

    def replace_content(self, old, new):
        self._rendered_formulas = [
            (new if text == old else text, label, content_type)
            for text, label, content_type in self._rendered_formulas
        ]
        self.refresh()

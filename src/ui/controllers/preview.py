"""PreviewController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ui.controllers.status import StatusController
    from ui.main_window import MainWindow
import re

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from localization.manager import translate as tr
from preview.math_preview import get_mathjax_base_url
from preview.smart_preview import (
    build_preview_error_html,
    build_smart_preview_html,
    render_formula_content_html,
)
from rendering.latex import get_document_render_mode, get_latex_renderer
from runtime.content_types import FORMULA_CONTENT_TYPE, ContentType


class PreviewLatexRenderWorker(QObject):
    finished = pyqtSignal(str, object)

    def render_formula(self, cache_key: str, latex_code: str):
        svg = None
        try:
            renderer = get_latex_renderer()
            if renderer and renderer.is_available():
                svg = renderer.render_to_svg(str(latex_code or ""))
        except Exception:
            svg = None
        self.finished.emit(str(cache_key or ""), svg)


class PreviewController(QObject):
    _preview_latex_render_request = pyqtSignal(str, str)

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
        self._closing = False
        self._preview_svg_cache = {}
        self._preview_svg_pending = set()
        self._preview_render_thread = None
        self._preview_render_worker = None
        self._rendered_formulas = []
        self._editor_preview_source = ""
        self._editor_preview_content_type = FORMULA_CONTENT_TYPE
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._do_render_latex)
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

    def _do_render_latex(self):
        """Run live rendering."""
        self.refresh()

    def _build_preview_latex_cache_key(self, latex_code: str) -> str:
        mode = get_document_render_mode()
        return f"{str(mode or '').strip()}|{str(latex_code or '').strip()}"

    def _namespace_preview_svg_ids(self, svg: str, namespace: str) -> str:
        text = str(svg or "")
        ns = re.sub("[^0-9A-Za-z_]+", "_", str(namespace or "").strip())
        if not text or not ns:
            return text
        id_pattern = re.compile('\\bid="([^"]+)"')
        ids = id_pattern.findall(text)
        if not ids:
            return text
        mapping = {old: f"{ns}_{old}" for old in ids}
        for old, new in mapping.items():
            text = re.sub(f'\\bid="{re.escape(old)}"', f'id="{new}"', text)
            text = re.sub(f"url\\(#({re.escape(old)})\\)", f"url(#{new})", text)
            text = re.sub(
                f"""(["\\'])#({re.escape(old)})(["\\'])""", f"\\1#{new}\\3", text
            )
        return text

    def _ensure_preview_latex_render_worker(self):
        if self._preview_render_thread and self._preview_render_worker:
            return
        self._preview_render_thread = QThread(self)
        self._preview_render_worker = PreviewLatexRenderWorker()
        self._preview_render_worker.moveToThread(self._preview_render_thread)
        self._preview_render_thread.finished.connect(
            self._preview_render_worker.deleteLater
        )
        self._preview_latex_render_request.connect(
            self._preview_render_worker.render_formula
        )
        self._preview_render_worker.finished.connect(
            self._on_preview_latex_render_finished
        )
        self._preview_render_thread.start()

    def _schedule_preview_latex_render(self, latex_code: str):
        text = str(latex_code or "").strip()
        if not text:
            return None
        cache_key = self._build_preview_latex_cache_key(text)
        if (
            cache_key in self._preview_svg_cache
            or cache_key in self._preview_svg_pending
        ):
            return cache_key
        self._ensure_preview_latex_render_worker()
        self._preview_svg_pending.add(cache_key)
        self._preview_latex_render_request.emit(cache_key, text)
        return cache_key

    def _on_preview_latex_render_finished(self, cache_key: str, svg: object):
        if self._closing:
            return
        key = str(cache_key or "")
        if not key:
            return
        self._preview_svg_pending.discard(key)
        self._preview_svg_cache[key] = str(svg) if svg else ""
        try:
            self.refresh()
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
            html = self._build_smart_preview_html(all_items)
            base_url = get_mathjax_base_url()
            self.view.preview_view.setHtml(html, base_url)
        except Exception as e:
            try:
                self.view.preview_view.setHtml(
                    build_preview_error_html(e), get_mathjax_base_url()
                )
            except Exception:
                pass

    def _render_formula_preview_content(self, content: str) -> str:
        render_mode = get_document_render_mode()
        cache_key = (
            self._build_preview_latex_cache_key(content)
            if render_mode and render_mode.startswith("latex_")
            else ""
        )
        has_cached_svg = bool(cache_key) and cache_key in self._preview_svg_cache
        cached_svg = (
            self._preview_svg_cache.get(cache_key, "") if has_cached_svg else ""
        )
        return render_formula_content_html(
            content,
            render_mode=render_mode,
            cache_key=cache_key,
            has_cached_svg=has_cached_svg,
            cached_svg=cached_svg or "",
            namespace_svg_ids=self._namespace_preview_svg_ids,
            schedule_render=self._schedule_preview_latex_render,
        )

    def _build_smart_preview_html(self, items: list) -> str:
        return build_smart_preview_html(items, self._render_formula_preview_content)

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
        self._closing = True
        self._render_timer.stop()
        thread = self._preview_render_thread
        if thread is not None:
            thread.quit()
            thread.wait()
            thread.deleteLater()
        self._preview_render_thread = None
        self._preview_render_worker = None

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

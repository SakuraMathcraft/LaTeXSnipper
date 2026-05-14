"""MainWindow preview and editor-preview synchronization mixin."""

from __future__ import annotations

import re
import sys

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from backend.latex_renderer import get_latex_renderer
from preview.math_preview import get_mathjax_base_url
from preview.smart_preview import build_preview_error_html, build_smart_preview_html, render_formula_content_html


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


class PreviewControllerMixin:
    def _on_editor_text_changed(self):
        """Handle editor text changes with debounced rendering."""
        if self._render_timer:
            self._render_timer.stop()
            self._render_timer.start(300)

    def _set_editor_text_silent(self, text: str) -> None:
        """Set editor text without triggering live rendering."""
        if not self.latex_editor:
            return
        if self._render_timer:
            self._render_timer.stop()
        try:
            was_blocked = self.latex_editor.blockSignals(True)
            self.latex_editor.setPlainText(text)
        finally:
            try:
                self.latex_editor.blockSignals(was_blocked)
            except Exception:
                pass

    def _do_render_latex(self):
        """Run live rendering."""
        self._refresh_preview()

    def _build_preview_latex_cache_key(self, latex_code: str) -> str:
        try:
            from backend.latex_renderer import _latex_settings

            mode = _latex_settings.get_render_mode() if _latex_settings else "latex_pdflatex"
        except Exception:
            mode = "latex_pdflatex"
        return f"{str(mode or '').strip()}|{str(latex_code or '').strip()}"

    def _namespace_preview_svg_ids(self, svg: str, namespace: str) -> str:
        text = str(svg or "")
        ns = re.sub(r"[^0-9A-Za-z_]+", "_", str(namespace or "").strip())
        if not text or not ns:
            return text

        id_pattern = re.compile(r'\bid="([^"]+)"')
        ids = id_pattern.findall(text)
        if not ids:
            return text

        mapping = {old: f"{ns}_{old}" for old in ids}
        for old, new in mapping.items():
            text = re.sub(rf'\bid="{re.escape(old)}"', f'id="{new}"', text)
            text = re.sub(rf'url\(#({re.escape(old)})\)', f'url(#{new})', text)
            text = re.sub(rf'(["\'])#({re.escape(old)})(["\'])', rf'\1#{new}\3', text)
        return text

    def _ensure_preview_latex_render_worker(self):
        if self._preview_render_thread and self._preview_render_worker:
            return
        self._preview_render_thread = QThread(self)
        self._preview_render_worker = PreviewLatexRenderWorker()
        self._preview_render_worker.moveToThread(self._preview_render_thread)
        self._preview_latex_render_request.connect(self._preview_render_worker.render_formula)
        self._preview_render_worker.finished.connect(self._on_preview_latex_render_finished)
        self._preview_render_thread.start()

    def _schedule_preview_latex_render(self, latex_code: str):
        text = str(latex_code or "").strip()
        if not text:
            return None
        cache_key = self._build_preview_latex_cache_key(text)
        if cache_key in self._preview_svg_cache or cache_key in self._preview_svg_pending:
            return cache_key
        self._ensure_preview_latex_render_worker()
        self._preview_svg_pending.add(cache_key)
        self._preview_latex_render_request.emit(cache_key, text)
        return cache_key

    def _on_preview_latex_render_finished(self, cache_key: str, svg: object):
        key = str(cache_key or "")
        if not key:
            return
        self._preview_svg_pending.discard(key)
        self._preview_svg_cache[key] = str(svg) if svg else ""
        try:
            self._refresh_preview()
        except Exception:
            pass

    def render_latex_in_preview(self, latex: str, label: str = None):
        """Render a LaTeX formula in the preview area."""
        if not self.preview_view:
            return
        latex = latex.strip()
        if not latex:
            return

        existing_formulas = [f for f, _ in self._rendered_formulas]
        if latex in existing_formulas:
            return

        if hasattr(self, "_formula_types") and latex not in self._formula_types:
            self._formula_types[latex] = getattr(self, "current_model", "mathcraft")

        if label is None:
            label = self._formula_names.get(latex, "")

        self._rendered_formulas.insert(0, (latex, label))

        if len(self._rendered_formulas) > 20:
            self._rendered_formulas = self._rendered_formulas[:20]

        self._refresh_preview()

    def _refresh_preview(self):
        """Refresh the preview area using each record type."""
        if not self.preview_view:
            return

        all_items = []
        editor_text = self.latex_editor.toPlainText().strip()
        existing_formulas = [f for f, _ in self._rendered_formulas]
        if editor_text and editor_text not in existing_formulas:
            current_mode = getattr(self, "current_model", "mathcraft")
            all_items.append((editor_text, "编辑中", current_mode))

        for formula, label in self._rendered_formulas:
            content_type = self._formula_types.get(formula, "mathcraft")
            all_items.append((formula, label, content_type))

        try:
            html = self._build_smart_preview_html(all_items)
            base_url = get_mathjax_base_url()
            self.preview_view.setHtml(html, base_url)
        except Exception as e:
            try:
                self.preview_view.setHtml(build_preview_error_html(e), get_mathjax_base_url())
            except Exception:
                pass

    def _render_formula_preview_content(self, content: str) -> str:
        render_mode = None
        try:
            from backend.latex_renderer import _latex_settings

            render_mode = _latex_settings.get_render_mode() if _latex_settings else None
        except Exception:
            render_mode = None

        cache_key = self._build_preview_latex_cache_key(content) if render_mode and render_mode.startswith("latex_") else ""
        has_cached_svg = bool(cache_key) and cache_key in self._preview_svg_cache
        cached_svg = self._preview_svg_cache.get(cache_key, "") if has_cached_svg else ""
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
        return build_smart_preview_html(
            items,
            self._render_formula_preview_content,
            debug=not getattr(sys, "frozen", False),
        )

    def _clear_preview(self):
        """Clear all formulas from the preview area."""
        self._rendered_formulas = []
        self._refresh_preview()
        self.set_action_status("已清空预览")

    def _add_preview_to_history(self):
        """Add the preview formula to history while preserving its label."""
        if not self._rendered_formulas:
            self.set_action_status("预览中没有公式")
            return

        added_count = 0
        for formula, label in self._rendered_formulas:
            if formula and formula not in self.history:
                self.history.insert(0, formula)

                if hasattr(self, "_formula_types"):
                    if formula not in self._formula_types:
                        self._formula_types[formula] = getattr(self, "current_model", "mathcraft")

                if label:
                    name = label.strip()
                    if name.startswith('#'):
                        parts = name.split(' ', 1)
                        if len(parts) > 1:
                            name = parts[1].strip()
                        else:
                            name = ""
                    if name:
                        self._formula_names[formula] = name
                added_count += 1

        if added_count > 0:
            self.save_history()
            self.rebuild_history_ui()
            self.set_action_status(f"已添加 {added_count} 个公式到历史")
        else:
            self.set_action_status("公式已在历史中")

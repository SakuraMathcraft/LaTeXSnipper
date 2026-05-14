"""Editor copy, favorite, and export action mixin."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication
from exporting.formula_converters import latex_to_mathml, latex_to_omml, latex_to_svg_code
from ui.favorites_window import FavoritesWindow
from ui.formula_export_menu import export_formula_to_clipboard, show_formula_export_menu
from ui.menu_helpers import CenterMenu
from ui.window_helpers import select_save_file_with_icon as _select_save_file_with_icon


class EditorActionsControllerMixin:
    def _ensure_favorites_window(self):
        if self.favorites_window is None:
            print("[DEBUG] 延迟初始化收藏窗口")
            self.favorites_window = FavoritesWindow(self.cfg, self, select_save_file=_select_save_file_with_icon)
        return self.favorites_window

    def _copy_editor_content(self):
        """Copy editor content to the clipboard."""
        text = self.latex_editor.toPlainText().strip()
        if not text:
            self.set_action_status("编辑器为空")
            return
        try:
            QApplication.clipboard().setText(text)
            self.set_action_status("已复制")
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(text)
                self.set_action_status("已复制")
            except Exception:
                self.set_action_status("复制失败")

    def _add_editor_to_fav(self):
        """Add editor content to favorites."""
        text = self.latex_editor.toPlainText().strip()
        if not text:
            self.set_action_status("编辑器为空")
            return
        content_type = None
        try:
            if hasattr(self, "_formula_types") and text in self._formula_types:
                content_type = self._formula_types.get(text)
        except Exception:
            content_type = None
        if not content_type:
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
        if not content_type:
            content_type = getattr(self, "current_model", "mathcraft")
        self._ensure_favorites_window().add_favorite(text, content_type=content_type)

    def _show_export_menu(self):
        """Show the export format menu."""
        self._show_export_menu_for_source(
            self.export_btn,
            lambda: self.latex_editor.toPlainText(),
            empty_hint="编辑器为空",
        )

    def _show_export_menu_for_source(self, anchor_widget, text_source, empty_hint: str = "内容为空", info_parent=None):
        """Show the export menu below a specific widget."""
        show_formula_export_menu(
            parent=self,
            menu_cls=CenterMenu,
            anchor_widget=anchor_widget,
            text_source=text_source,
            status_callback=lambda message: self.set_action_status(message, parent=info_parent),
            export_callback=lambda format_type, text: self._export_as(format_type, text, info_parent=info_parent),
            empty_hint=empty_hint,
        )

    def _export_as(self, format_type: str, latex: str, info_parent=None):
        """Export the formula in the requested format."""
        try:
            _ok, message = export_formula_to_clipboard(
                format_type,
                latex,
                mathml_converter=latex_to_mathml,
                omml_converter=latex_to_omml,
                svg_converter=latex_to_svg_code,
            )
        except Exception as e:
            self.set_action_status(f"导出失败: {e}", parent=info_parent)
            return
        self.set_action_status(message, parent=info_parent)

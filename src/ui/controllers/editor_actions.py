"""EditorActionsController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.config_manager import ConfigManager
    from ui.controllers.status import StatusController
    from ui.main_window import MainWindow
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from exporting.formula_converters import (
    latex_to_mathml,
    latex_to_omml,
    latex_to_svg_code,
)
from exporting.formula_export import is_export_format_available
from localization.manager import translate as tr
from ui.formula_export_menu import export_formula_to_clipboard, show_formula_export_menu
from ui.menu_helpers import CenterMenu


class EditorActionsController(QObject):
    export_format_changed = pyqtSignal(str)

    def __init__(self, view: MainWindow, cfg: ConfigManager, status: StatusController):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.status = status

    def _remember_export_format(self, format_type: str) -> None:
        key = str(format_type or "").strip()
        if not is_export_format_available(key):
            return
        try:
            self.cfg.set("last_export_format", key)
        except Exception:
            pass
        self.export_format_changed.emit(key)

    def copy_content(self):
        """Copy editor content to the clipboard."""
        text = self.view.latex_editor.toPlainText().strip()
        if not text:
            self.status.show_action_status(tr("编辑器为空"), level="warning")
            return
        try:
            QApplication.clipboard().setText(text)
            self.status.set_action_status(tr("已复制"))
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(text)
                self.status.set_action_status(tr("已复制"))
            except Exception:
                self.status.show_action_status(tr("复制失败"), level="error")

    def show_export_menu(self):
        """Show the export format menu."""
        self.show_source_export_menu(
            self.view.export_btn,
            lambda: self.view.latex_editor.toPlainText(),
            empty_hint=tr("编辑器为空"),
        )

    def show_source_export_menu(
        self,
        anchor_widget,
        text_source,
        empty_hint: str | None = None,
        info_parent=None,
    ):
        """Show the export menu below a specific widget."""
        show_formula_export_menu(
            parent=self.view,
            menu_cls=CenterMenu,
            anchor_widget=anchor_widget,
            text_source=text_source,
            status_callback=lambda message, level: self.status.show_action_status(
                message, level=level, parent=info_parent
            ),
            export_callback=lambda format_type, text: self.export(
                format_type, text, info_parent=info_parent
            ),
            empty_hint=empty_hint or tr("内容为空"),
        )

    def export(self, format_type: str, latex: str, info_parent=None):
        """Export the formula in the requested format."""
        self._remember_export_format(format_type)
        try:
            ok, message = export_formula_to_clipboard(
                format_type,
                latex,
                mathml_converter=latex_to_mathml,
                omml_converter=latex_to_omml,
                svg_converter=latex_to_svg_code,
                parent=info_parent or self.view,
                status_callback=lambda message, level: self.status.show_action_status(
                    message, level=level, parent=info_parent
                ),
            )
        except Exception as e:
            self.status.show_action_status(
                tr("导出失败: {error}").format(error=e),
                level="error",
                parent=info_parent,
            )
            return
        if ok:
            level = "info" if message.startswith(tr("正在导出 ")) else "success"
        else:
            level = "info" if message == tr("已取消导出") else "error"
        self.status.show_action_status(message, level=level, parent=info_parent)

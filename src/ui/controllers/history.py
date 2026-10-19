"""HistoryController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.config_manager import ConfigManager
    from ui.controllers.editor_actions import EditorActionsController
    from ui.controllers.preview import PreviewController
    from ui.controllers.status import StatusController
    from ui.controllers.theme import ThemeController
    from ui.controllers.windows import WindowController
    from ui.main_window import MainWindow
import logging

import pyperclip
from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
from qfluentwidgets import Action, InfoBar, InfoBarPosition

from localization.manager import translate as tr
from runtime.content_types import ContentType, normalize_content_type
from runtime.history_store import load_history_store, save_history_store
from ui.edit_formula_dialog import EditFormulaDialog
from ui.formula_export_menu import populate_formula_export_menu
from ui.history_panel import (
    clear_history_rows,
    history_display_entries,
    refresh_history_order_button,
)
from ui.history_panel import create_history_row as create_history_row_widget
from ui.menu_helpers import CenterMenu
from ui.window_helpers import (
    exec_close_only_message_box as _exec_close_only_message_box,
)
from ui.window_helpers import show_formula_rename_dialog as _show_formula_rename_dialog

logger = logging.getLogger(f"latexsnipper.{__name__}")
MAX_HISTORY = 200


class HistoryController(QObject):
    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        editor: EditorActionsController,
        preview: PreviewController,
        status: StatusController,
        theme: ThemeController,
        windows: WindowController,
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.editor = editor
        self.preview = preview
        self.status = status
        self.theme = theme
        self.windows = windows
        from runtime.config_manager import default_user_data_file

        self.history_file = str(default_user_data_file("history.json"))
        self.history = []
        self.history_reverse = bool(cfg.get("history_reverse", True))
        self._formula_names = {}
        self._formula_types = {}

    def _show_history_context_menu(self, row: QWidget, global_pos):
        if not self._row_is_alive(row):
            return
        latex = self._safe_row_text(row)
        m = CenterMenu(parent=self.view)
        m.addAction(Action(tr("编辑"), triggered=lambda: self._edit_history_row(row)))
        m.addAction(Action(tr("复制"), triggered=lambda: self._do_copy_row(row)))
        m.addAction(Action(tr("收藏"), triggered=lambda: self._do_fav_row(row)))
        export_menu = CenterMenu(tr("导出为..."), parent=m)
        populate_formula_export_menu(
            export_menu, lambda format_type: self.editor.export(format_type, latex)
        )
        m.addMenu(export_menu)
        m.addAction(
            Action(tr("重命名"), triggered=lambda: self._rename_history_row(row))
        )
        m.addAction(Action(tr("删除"), triggered=lambda: self._do_delete_row(row)))
        m.exec(global_pos)

    def _rename_history_row(self, row: QWidget):
        """Rename a formula history row."""
        latex = self._safe_row_text(row)
        if not latex:
            return
        current_name = self._formula_names.get(latex, "")
        new_name, ok = _show_formula_rename_dialog(
            self.view,
            current_name=current_name,
            title=tr("重命名公式"),
            prompt=tr("输入公式名称："),
        )
        if not ok:
            return
        self.set_label(latex, new_name)
        self.windows.favorites_window.set_label(latex, new_name)

    def _history_row_index(self, row: QWidget):
        actual_index = getattr(row, "_history_index", None)
        if isinstance(actual_index, int) and 0 <= actual_index < len(self.history):
            return actual_index
        total = self.view.history_layout.count() - 1
        for i in range(total):
            item = self.view.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w is row:
                return i
        return None

    def _edit_history_row(self, row: QWidget):
        old_latex = getattr(row, "_latex_text", "")
        dlg = EditFormulaDialog(
            old_latex, self.view, content_type=self._formula_types[old_latex]
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_latex = dlg.value()
        if not new_latex or new_latex == old_latex:
            return
        if old_latex in self._formula_names:
            self._formula_names[new_latex] = self._formula_names.pop(old_latex)
        if old_latex in self._formula_types:
            self._formula_types[new_latex] = self._formula_types.pop(old_latex)
        row._latex_text = new_latex
        lbl = getattr(row, "_content_label", None)
        if lbl:
            lbl.setText(new_latex)
            self.theme.style_formula_label(lbl)
        idx = self._history_row_index(row)
        if idx is not None and 0 <= idx < len(self.history):
            self.history[idx] = new_latex
            try:
                self.save_history()
            except Exception as e:
                logger.warning("保存历史失败: %s", e)
        self.preview.replace_content(old_latex, new_latex)
        self.status.set_action_status(tr("已更新"))

    def _history_display_entries(self):
        return history_display_entries(
            self.history, bool(getattr(self, "history_reverse", False))
        )

    def _refresh_history_order_button(self):
        refresh_history_order_button(
            getattr(self.view, "history_order_button", None),
            bool(getattr(self, "history_reverse", False)),
        )

    def toggle_history_order(self):
        self.history_reverse = not bool(getattr(self, "history_reverse", False))
        self.cfg.set("history_reverse", self.history_reverse)
        self._refresh_history_order_button()
        self.rebuild_history_ui()

    def rebuild_history_ui(self):
        clear_history_rows(self.view.history_layout)
        for display_index, history_index, text in self._history_display_entries():
            self.view.history_layout.insertWidget(
                self.view.history_layout.count() - 1,
                self.create_history_row(text, display_index, history_index),
            )
        self._refresh_history_order_button()
        self.update_history_ui()

    def _row_is_alive(self, row):
        if not row:
            return False
        if getattr(row, "_deleted", False):
            return False
        if sip.isdeleted(row):
            return False
        if row.parent() is None:
            return False
        return True

    def _safe_row_text(self, row):
        if not self._row_is_alive(row):
            return ""
        return (getattr(row, "_latex_text", "") or "").strip()

    def _do_copy_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.status.show_action_status(tr("内容不存在"), level="warning")
            return
        try:
            QApplication.clipboard().setText(txt)
            self.status.set_action_status(tr("已复制"))
        except Exception:
            try:
                pyperclip.copy(txt)
                self.status.set_action_status(tr("已复制"))
            except Exception:
                self.status.show_action_status(tr("复制失败"), level="error")

    def _do_fav_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.status.show_action_status(tr("内容不存在"), level="warning")
            return
        self.windows.favorites_window.add_favorite(
            txt, content_type=normalize_content_type(self._formula_types[txt])
        )

    def _do_delete_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.status.set_action_status(tr("已删除"))
            return
        self.delete_history_item(row, txt)

    def _load_history_row_to_editor(self, row):
        txt = self._safe_row_text(row)
        if txt:
            self.preview.set_editor_text(txt)
            idx = getattr(row, "_index", 0)
            name = self._formula_names.get(txt, "")
            if name:
                label = f"#{idx} {name}"
            elif idx > 0:
                label = f"#{idx}"
            else:
                label = ""
            self.preview.render_latex_in_preview(
                txt, normalize_content_type(self._formula_types[txt]), label
            )
            self.status.set_action_status(tr("已加载到编辑器"))

    def create_history_row(
        self, t: str, index: int = 0, history_index: int | None = None
    ):
        return create_history_row_widget(
            parent=self.view,
            history_container=self.view.history_container,
            text=t,
            index=index,
            history_index=history_index,
            formula_names=self._formula_names,
            apply_row_theme=self.theme.style_history_row,
            row_is_alive=self._row_is_alive,
            on_load_to_editor=self._load_history_row_to_editor,
            on_copy=self._do_copy_row,
            on_context_menu=self._show_history_context_menu,
        )

    def add_history_record(self, text: str, content_type: ContentType):
        t = (text or "").strip()
        if not t:
            return
        self._formula_types[t] = normalize_content_type(content_type)
        if t in self.history:
            self.history.remove(t)
        self.history.append(t)
        if len(self.history) > MAX_HISTORY:
            removed = self.history[:-MAX_HISTORY]
            self.history = self.history[-MAX_HISTORY:]
            for old_text in removed:
                self._formula_names.pop(old_text, None)
                self._formula_types.pop(old_text, None)
        self.save_history()
        self.rebuild_history_ui()
        self.status.set_action_status(tr("已加入历史"))

    def load_history(self):
        try:
            self.history, self._formula_names, self._formula_types = load_history_store(
                self.history_file
            )
        except Exception as e:
            logger.warning("加载历史失败: %s", e)
            self.history = []
        self.rebuild_history_ui()

    def delete_history_item(self, widget, text):
        if text in self.history:
            self.history.remove(text)
            self._formula_names.pop(text, None)
            self._formula_types.pop(text, None)
        if widget:
            try:
                if self.view.history_layout.indexOf(widget) != -1:
                    self.view.history_layout.removeWidget(widget)
            except Exception:
                pass
            widget.setParent(None)
            widget.deleteLater()
        self.save_history()
        self.status.set_action_status(tr("已删除"))
        self.update_history_ui()

    def update_history_ui(self):
        self.view.clear_history_button.setText(tr("清空历史记录"))
        if self.history:
            self.view.clear_history_button.setToolTip(tr("清空所有历史记录"))
        else:
            self.view.clear_history_button.setToolTip(tr("当前无历史记录，点击会提示"))
        self.view.clear_history_button.setEnabled(True)

    def save_history(self):
        try:
            save_history_store(
                self.history_file,
                self.history,
                self._formula_names,
                self._formula_types,
            )
        except Exception as e:
            logger.warning("保存历史失败: %s", e)

    def clear_history(self):
        if not self.history:
            InfoBar.info(
                title=tr("提示"),
                content=tr("当前没有历史记录可清空"),
                parent=self.status.notification_parent(),
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return
        ret = _exec_close_only_message_box(
            self.view,
            tr("确认"),
            tr("确定要清空所有 {count} 条历史记录吗？").format(count=len(self.history)),
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.history.clear()
        self._formula_names.clear()
        self._formula_types.clear()
        self.save_history()
        self.rebuild_history_ui()
        self.update_history_ui()
        self.status.set_action_status(tr("已清空历史"))

    def label_for(self, text):
        return self._formula_names.get(text, "")

    def contains(self, text):
        return text in self.history

    def add_named_record(self, text, content_type, name):
        if name:
            self._formula_names[text] = name
        self.add_history_record(text, content_type)

    def set_label(self, text, name):
        if name:
            self._formula_names[text] = name
        else:
            self._formula_names.pop(text, None)
        self.save_history()
        self.rebuild_history_ui()
        self.preview.set_label(text, name)

"""History controller mixin for the main window."""

from __future__ import annotations

import pyperclip
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget
from qfluentwidgets import Action, InfoBar, InfoBarPosition

from runtime.config_manager import normalize_content_type
from runtime.history_store import load_history_store, save_history_store
from ui.edit_formula_dialog import EditFormulaDialog
from ui.formula_export_menu import populate_formula_export_menu
from ui.history_panel import (
    clear_history_rows,
    create_history_row as create_history_row_widget,
    history_display_entries,
    refresh_history_order_button,
)
from ui.menu_helpers import CenterMenu
from ui.window_helpers import (
    exec_close_only_message_box as _exec_close_only_message_box,
    show_formula_rename_dialog as _show_formula_rename_dialog,
)

try:
    from PyQt6 import sip
except Exception:
    try:
        import sip  # pyright: ignore[reportMissingImports]
    except Exception:
        sip = None

MAX_HISTORY = 200


class HistoryControllerMixin:
    def _show_history_context_menu(self, row: QWidget, global_pos):
        if not self._row_is_alive(row):
            return
        latex = self._safe_row_text(row)
        m = CenterMenu(parent=self)
        m.addAction(Action("编辑", triggered=lambda: self._edit_history_row(row)))
        m.addAction(Action("复制", triggered=lambda: self._do_copy_row(row)))
        m.addAction(Action("收藏", triggered=lambda: self._do_fav_row(row)))

        export_menu = CenterMenu("导出为...", parent=m)
        populate_formula_export_menu(export_menu, lambda format_type: self._export_as(format_type, latex))
        m.addMenu(export_menu)

        m.addAction(Action("重命名", triggered=lambda: self._rename_history_row(row)))
        m.addAction(Action("删除", triggered=lambda: self._do_delete_row(row)))
        m.exec(global_pos)

    def _rename_history_row(self, row: QWidget):
        """Rename a formula history row."""
        latex = self._safe_row_text(row)
        if not latex:
            return
        current_name = self._formula_names.get(latex, "")
        new_name, ok = _show_formula_rename_dialog(
            self,
            current_name=current_name,
            title="重命名公式",
            prompt="输入公式名称（留空则清除名称）：",
        )
        if not ok:
            return
        if new_name:
            self._formula_names[latex] = new_name
            if hasattr(self, "favorites_window") and self.favorites_window:
                self.favorites_window._favorite_names[latex] = new_name
                self.favorites_window.save_favorites()
                self.favorites_window.refresh_list()
        else:
            self._formula_names.pop(latex, None)
            if (
                hasattr(self, "favorites_window")
                and self.favorites_window
            ):
                self.favorites_window._favorite_names.pop(latex, None)
                self.favorites_window.save_favorites()
                self.favorites_window.refresh_list()
        self.save_history()



        for i, (formula, label) in enumerate(self._rendered_formulas):
            if formula == latex:
                s = (label or "").strip()
                prefix = ""
                if s.startswith("#"):
                    prefix = s.split(" ", 1)[0]
                if new_name:
                    new_label = f"{prefix} {new_name}".strip() if prefix else new_name
                else:
                    new_label = prefix
                self._rendered_formulas[i] = (formula, new_label)


        self.rebuild_history_ui()
        self._refresh_preview()
        self.set_action_status(f"已命名: {new_name}" if new_name else "已清除名称")

    def _history_row_index(self, row: QWidget):
        actual_index = getattr(row, "_history_index", None)
        if isinstance(actual_index, int) and 0 <= actual_index < len(self.history):
            return actual_index

        total = self.history_layout.count() - 1
        for i in range(total):
            item = self.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w is row:
                return i
        return None

    def _edit_history_row(self, row: QWidget):
        old_latex = getattr(row, "_latex_text", "")
        dlg = EditFormulaDialog(old_latex, self)
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
            self._apply_formula_label_theme(lbl)

        idx = self._history_row_index(row)
        if idx is not None and 0 <= idx < len(self.history):
            self.history[idx] = new_latex
            try:
                self.save_history()
            except Exception as e:
                print("[WARN] 保存历史失败:", e)


        for i, (formula, label) in enumerate(self._rendered_formulas):
            if formula == old_latex:
                self._rendered_formulas[i] = (new_latex, label)
        self._refresh_preview()

        self.set_action_status("已更新")

    def _history_display_entries(self):
        return history_display_entries(self.history, bool(getattr(self, "history_reverse", False)))

    def _refresh_history_order_button(self):
        refresh_history_order_button(
            getattr(self, "history_order_button", None),
            bool(getattr(self, "history_reverse", False)),
        )

    def toggle_history_order(self):
        self.history_reverse = not bool(getattr(self, "history_reverse", False))
        self.cfg.set("history_reverse", self.history_reverse)
        self._refresh_history_order_button()
        self.rebuild_history_ui()

    def rebuild_history_ui(self):
        clear_history_rows(self.history_layout)
        for display_index, history_index, text in self._history_display_entries():
            self.history_layout.insertWidget(
                self.history_layout.count() - 1,
                self.create_history_row(text, display_index, history_index),
            )
        self._refresh_history_order_button()
        self.update_history_ui()

    def _row_is_alive(self, row):
        if not row:
            return False
        if getattr(row, "_deleted", False):
            return False
        if sip and hasattr(sip, "isdeleted"):
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
            self.set_action_status("内容不存在")
            return
        try:
            QApplication.clipboard().setText(txt)
            self.set_action_status("已复制")
        except Exception:
            try:
                pyperclip.copy(txt)
                self.set_action_status("已复制")
            except Exception:
                self.set_action_status("复制失败")

    def _do_fav_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("内容不存在")
            return
        content_type = None
        try:
            if hasattr(self, "_formula_types"):
                content_type = self._formula_types.get(txt)
        except Exception:
            content_type = None
        if not content_type:
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
        if not content_type:
            content_type = getattr(self, "current_model", "mathcraft")
        self._ensure_favorites_window().add_favorite(txt, content_type=content_type)

    def _do_delete_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("已删除（空）")
            return

        self.delete_history_item(row, txt)

    def _load_history_row_to_editor(self, row):
        txt = self._safe_row_text(row)
        if txt:
            self._set_editor_text_silent(txt)
            idx = getattr(row, '_index', 0)
            name = self._formula_names.get(txt, "")
            if name:
                label = f"#{idx} {name}"
            elif idx > 0:
                label = f"#{idx}"
            else:
                label = ""
            self.render_latex_in_preview(txt, label)
            self.set_action_status("已加载到编辑器")

    def create_history_row(self, t: str, index: int = 0, history_index: int | None = None):
        return create_history_row_widget(
            parent=self,
            history_container=self.history_container,
            text=t,
            index=index,
            history_index=history_index,
            formula_names=self._formula_names,
            apply_row_theme=self._apply_history_row_theme,
            row_is_alive=self._row_is_alive,
            on_load_to_editor=self._load_history_row_to_editor,
            on_copy=self._do_copy_row,
            on_context_menu=self._show_history_context_menu,
        )

    def add_history_record(self, text: str, content_type: str = None):
        t = (text or "").strip()
        if not t:
            return

        if content_type is None:
            content_type = getattr(self, "current_model", "mathcraft")
        self._formula_types[t] = normalize_content_type(content_type)

        self.history.append(t)

        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        self.save_history()
        self.rebuild_history_ui()
        self.set_action_status("已加入历史")
        print(f"[HistoryAdd] total={len(self.history)} type={content_type} last='{t[:60]}'")

    def load_history(self):
        try:
            self.history, self._formula_names, self._formula_types = load_history_store(self.history_path)
        except Exception as e:
            print("加载历史失败:", e)
            self.history = []
        self.rebuild_history_ui()

    def delete_history_item(self, widget, text):
        print(f"[Delete] request text='{text}' history_len={len(self.history)}")
        if text in self.history:
            self.history.remove(text)
        if widget:

            try:
                if self.history_layout.indexOf(widget) != -1:
                    self.history_layout.removeWidget(widget)
            except Exception:
                pass
            widget.setParent(None)
            widget.deleteLater()
        self.save_history()
        self.set_action_status("已删除")
        self.update_history_ui()

    def update_history_ui(self):
        self.clear_history_button.setText("清空历史记录")
        if self.history:

            self.clear_history_button.setToolTip("清空所有历史记录")
        else:

            self.clear_history_button.setToolTip("当前无历史记录，点击会提示")

        self.clear_history_button.setEnabled(True)

    def save_history(self):
        try:
            save_history_store(self.history_path, self.history, self._formula_names, self._formula_types)
        except Exception as e:
            print("历史保存失败:", e)

    def clear_history(self):

        if not self.history:
            InfoBar.info(
                title="提示",
                content="当前没有历史记录可清空",
                parent=self._get_infobar_parent(),
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return
        ret = _exec_close_only_message_box(
            self,
            "确认",
            f"确定要清空所有 {len(self.history)} 条历史记录吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.history.clear()
        self.save_history()
        self.rebuild_history_ui()
        self.update_history_ui()
        self.set_action_status("已清空历史")

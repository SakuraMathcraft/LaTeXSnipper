"""Favorites window."""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import Action, InfoBar, InfoBarPosition, RoundMenu

from exporting.formula_converters import latex_to_mathml, latex_to_omml, latex_to_svg_code
from preview.math_preview import preview_theme_tokens
from runtime.app_paths import resource_path
from runtime.config_manager import normalize_content_type, resolve_user_data_file
from ui.edit_formula_dialog import EditFormulaDialog
from ui.formula_export_menu import export_formula_to_clipboard, populate_formula_export_menu
from ui.window_helpers import (
    apply_close_only_window_flags as _apply_close_only_window_flags,
    exec_close_only_message_box,
    show_formula_rename_dialog,
)

DEFAULT_FAVORITES_NAME = "favorites.json"

class FavoritesWindow(QMainWindow):
    """Favorites window with list-only functionality."""
    def __init__(self, cfg, parent=None, select_save_file=None):
        super().__init__(parent)
        self.cfg = cfg
        self._select_save_file = select_save_file
        self._theme_is_dark_cached = None
        self.setWindowFlag(Qt.WindowType.Window, True)
        _apply_close_only_window_flags(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("公式收藏夹")
        self.setMinimumSize(400, 350)

        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Use a container widget.
        container = QWidget()
        main_lay = QVBoxLayout(container)
        main_lay.setContentsMargins(6, 6, 6, 6)
        main_lay.setSpacing(6)
        
        from qfluentwidgets import PushButton, FluentIcon
        
        # Top button row.
        top_btn_layout = QHBoxLayout()
        btn_save_path = PushButton(FluentIcon.FOLDER, "保存路径")
        btn_save_path.clicked.connect(self.select_file)
        top_btn_layout.addWidget(btn_save_path)
        
        btn_clear = PushButton(FluentIcon.DELETE, "清空收藏夹")
        btn_clear.clicked.connect(self._clear_all_favorites)
        top_btn_layout.addWidget(btn_clear)
        main_lay.addLayout(top_btn_layout)

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setWordWrap(True)
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setMinimumHeight(200)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_lay.addWidget(self.list_widget, 1)

        close_btn = PushButton(FluentIcon.CLOSE, "关闭窗口")
        close_btn.clicked.connect(self.close)
        main_lay.addWidget(close_btn, 0)

        # Set the container as the central widget.
        self.setCentralWidget(container)

        self.favorites = []
        self._favorite_names = {}   # Favorite names: {content: name}.
        self._favorite_types = {}   # Favorite types: {content: content_type}.
        favorites_path = resolve_user_data_file(self.cfg, "favorites_path", DEFAULT_FAVORITES_NAME)
        self.file_path = favorites_path
        self.load_favorites()

        # --- ESC shortcut close; fallback when child widgets intercept key events ---
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.close)
        self.apply_theme_styles(force=True)

    # --- Capture the ESC key ---
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _favorites_list_qss(self) -> str:
        t = preview_theme_tokens()
        return f"""
            QListWidget {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {t['table_border']};
                padding: 8px 6px;
                color: {t['body_text']};
                background: transparent;
                outline: none;
                border-left: none;
                border-right: none;
            }}
            QListWidget::item:hover {{
                background: {t['panel_bg']};
            }}
            QListWidget::item:selected {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:selected:active {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:selected:!active {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:focus {{
                border: none;
                outline: none;
            }}
        """

    def apply_theme_styles(self, force: bool = False):
        dark = False
        try:
            from qfluentwidgets import isDarkTheme
            dark = bool(isDarkTheme())
        except Exception:
            try:
                pal = self.palette().window().color()
                dark = ((pal.red() + pal.green() + pal.blue()) / 3.0) < 128
            except Exception:
                dark = False
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        try:
            self.list_widget.setStyleSheet(self._favorites_list_qss())
        except Exception:
            pass

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self.apply_theme_styles()
        except Exception:
            pass
        return result

    # ---------- Status ----------
    def _set_status(self, msg: str):
        p = self.parent()
        if p and hasattr(p, "set_action_status"):
            p.set_action_status(msg)
    
    def _on_item_double_clicked(self, item):
        """Load the formula into the editor and render it on double-click."""
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            latex = item.text()
        
        p = self.parent()
        if p and hasattr(p, 'latex_editor') and hasattr(p, 'render_latex_in_preview'):
            if hasattr(p, "_set_editor_text_silent"):
                p._set_editor_text_silent(latex)
            else:
                p.latex_editor.setPlainText(latex)
            
            # Ensure the parent window has type metadata for this content.
            content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            
            # Get the index and name, preferring the favorites name.
            idx = self.list_widget.row(item) + 1
            name = self._favorite_names.get(latex, "")
            if not name and hasattr(p, '_formula_names'):
                name = p._formula_names.get(latex, "")
            
            if name:
                label = f"#{idx} {name}"
            else:
                label = f"#{idx}"
            p.render_latex_in_preview(latex, label)
            self._set_status("已加载到编辑器")

    # ---------- Menu ----------
    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            return
        
        menu = RoundMenu(parent=self)
        menu.addAction(Action("复制", triggered=lambda: self._copy_item(latex)))

        export_menu = RoundMenu("导出为...", parent=menu)
        populate_formula_export_menu(export_menu, lambda format_type: self._export_as(format_type, latex))
        menu.addMenu(export_menu)

        menu.addSeparator()
        menu.addAction(Action("添加到历史", triggered=lambda: self._add_to_history(latex)))
        menu.addAction(Action("重命名", triggered=lambda: self._rename_item(latex)))
        menu.addAction(Action("编辑", triggered=lambda: self._edit_item(item, latex)))
        menu.addAction(Action("删除", triggered=lambda: self._delete_item(latex)))
        menu.exec(self.list_widget.mapToGlobal(pos))
    
    def _add_to_history(self, latex: str):
        """Add a favorite formula to history, inheriting label and type."""
        p = self.parent()
        if not p or not hasattr(p, 'history'):
            self._set_status("无法添加到历史")
            return
        
        if latex in p.history:
            self._set_status("公式已在历史中")
            return
        
        # Get the favorite type.
        content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
        # Inherit the name; write the history-name mapping first so the new row shows its label immediately.
        name = self._favorite_names.get(latex, "")
        if name and hasattr(p, '_formula_names'):
            p._formula_names[latex] = name
        
        # Add through add_history_record so the type is handled automatically.
        if hasattr(p, 'add_history_record'):
            p.add_history_record(latex, content_type)
        else:
            # Fallback path.
            p.history.insert(0, latex)
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            if hasattr(p, 'save_history'):
                p.save_history()
            if hasattr(p, 'rebuild_history_ui'):
                p.rebuild_history_ui()
            self._set_status("已添加到历史记录")

    def _export_as(self, format_type: str, latex: str):
        """Export the formula to the requested format."""
        try:
            _ok, message = export_formula_to_clipboard(
                format_type,
                latex,
                mathml_converter=latex_to_mathml,
                omml_converter=latex_to_omml,
                svg_converter=latex_to_svg_code,
            )
        except Exception as e:
            self._set_status(f"导出失败: {e}")
            return
        self._set_status(message)

    def _copy_item(self, latex: str):
        """Copy the formula to the clipboard."""
        import pyperclip
        if latex:
            pyperclip.copy(latex)
            self._set_status("已复制到剪贴板")

    def _rename_item(self, latex: str):
        """Rename a formula in favorites."""
        p = self.parent()
        # Use the favorites window name dictionary.
        current_name = self._favorite_names.get(latex, "")
        if not current_name:
            if p and hasattr(p, "_formula_names"):
                current_name = p._formula_names.get(latex, "")
        new_name, ok = show_formula_rename_dialog(
            self,
            current_name=current_name,
            title="公式命名",
            prompt="输入公式名称（留空则清除名称）：",
        )
        if not ok:
            return
        if new_name:
            self._favorite_names[latex] = new_name
            if p and hasattr(p, "_formula_names"):
                p._formula_names[latex] = new_name
                if hasattr(p, "save_history"):
                    p.save_history()
            self._set_status(f"已命名为: {new_name}")
        else:
            self._favorite_names.pop(latex, None)
            if p and hasattr(p, "_formula_names"):
                p._formula_names.pop(latex, None)
                if hasattr(p, "save_history"):
                    p.save_history()
            self._set_status("已清除名称")

        # Save favorites.
        self.save_favorites()

        # Refresh the list display.
        self.refresh_list()
        # Refresh main-window history so names for the same formula update immediately.
        if p and hasattr(p, "rebuild_history_ui"):
            p.rebuild_history_ui()
        # Refresh the main-window preview label so it does not keep the old name.
        if p and hasattr(p, "_rendered_formulas"):
            updated = False
            new_rendered = []
            for formula, label in getattr(p, "_rendered_formulas", []):
                if formula != latex:
                    new_rendered.append((formula, label))
                    continue
                s = (label or "").strip()
                prefix = ""
                if s.startswith("#"):
                    prefix = s.split(" ", 1)[0]
                if new_name:
                    new_label = f"{prefix} {new_name}".strip() if prefix else new_name
                else:
                    new_label = prefix
                new_rendered.append((formula, new_label))
                updated = True
            if updated:
                p._rendered_formulas = new_rendered
                if hasattr(p, "_refresh_preview"):
                    p._refresh_preview()

    def _edit_item(self, item, latex: str):
        """Edit formula content."""
        dlg = EditFormulaDialog(latex, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.value()
            if new and new != latex:
                # Find the index in favorites.
                if latex in self.favorites:
                    idx = self.favorites.index(latex)
                    self.favorites[idx] = new

                    # Update the favorites window name and type mappings.
                    if latex in self._favorite_names:
                        self._favorite_names[new] = self._favorite_names.pop(latex)
                    if latex in self._favorite_types:
                        self._favorite_types[new] = self._favorite_types.pop(latex)

                    self.save_favorites()
                    self.refresh_list()
                    self._set_status("已更新")

    def _delete_item(self, latex: str):
        """Delete a favorite item."""
        if latex in self.favorites:
            self.favorites.remove(latex)
            # Clean up name and type mappings.
            self._favorite_names.pop(latex, None)
            self._favorite_types.pop(latex, None)
            self.refresh_list()
            self.save_favorites()
            self._set_status("已删除")

    # ---------- List/File ----------
    def refresh_list(self):
        self.list_widget.clear()

        # Type display names.
        type_names = {
            "mathcraft": "公式",
            "mathcraft_text": "文字",
            "mathcraft_mixed": "混合",
        }

        for idx, formula in enumerate(self.favorites, start=1):
            # Create a styled list item.
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, formula)  # Store the original formula.

            # Get name and type, preferring favorites-owned metadata.
            name = self._favorite_names.get(formula, "")
            if not name:
                p = self.parent()
                if p and hasattr(p, "_formula_names"):
                    name = p._formula_names.get(formula, "")
            content_type = normalize_content_type(self._favorite_types.get(formula, "mathcraft"))
            type_display = type_names.get(content_type, "")

            # Build display text.
            parts = [f"#{idx}"]
            if name:
                parts.append(f"[{name}]")
            if type_display and type_display != "公式":  # Formula is the default and is not shown.
                parts.append(f"<{type_display}>")
            display_text = " ".join(parts) + f"\n{formula}"

            item.setText(display_text)
            item.setToolTip(formula)

            # Set item size and style.
            from PyQt6.QtCore import QSize
            item.setSizeHint(QSize(0, 50))  # Minimum height.

            self.list_widget.addItem(item)

        self.list_widget.setStyleSheet(self._favorites_list_qss())

    def select_file(self):
        path, _ = self._select_save_file(
            self,
            "选择收藏夹保存路径",
            os.path.dirname(self.file_path),
            "JSON Files (*.json)",
        )
        if path:
            self.file_path = path
            self.cfg.set("favorites_path", path)
            self.save_favorites()
            self._set_status("已更新保存路径")

    def load_favorites(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # New format: favorites list, names, and types.
                    fav_list = data.get("favorites", [])
                    self.favorites = [str(x) for x in fav_list]
                    # Load names.
                    names = data.get("names", {})
                    if isinstance(names, dict):
                        self._favorite_names = {str(k): str(v) for k, v in names.items()}
                    # Load types.
                    types = data.get("types", {})
                    if isinstance(types, dict):
                        self._favorite_types = {
                            str(k): normalize_content_type(str(v))
                            for k, v in types.items()
                        }
            except Exception as e:
                print("[Favorites] 加载失败:", e)
        self.refresh_list()

    def save_favorites(self):
        try:
            # Save favorites list, names, and types.
            data = {
                "favorites": self.favorites,
                "names": self._favorite_names,
                "types": self._favorite_types
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[Favorites] 保存失败:", e)

    def _clear_all_favorites(self):
        """Clear all favorites."""
        if not self.favorites:
            info_parent = self.parent() if self.parent() is not None else self
            InfoBar.info(
                title="提示",
                content="收藏夹已经是空的",
                parent=info_parent,
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return

        ret = exec_close_only_message_box(
            self,
            "确认",
            f"确定要清空所有 {len(self.favorites)} 条收藏吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.favorites.clear()
        self._favorite_names.clear()
        self._favorite_types.clear()
        self.save_favorites()
        self.refresh_list()
        self._set_status("已清空收藏夹")

    # ---------- Public API ----------
    def add_favorite(self, text: str, content_type: str = None, name: str = None):
        """Add a favorite item."""
        t = (text or "").strip()
        if not t:
            self._set_status("空公式，忽略")
            return
        if t in self.favorites:
            self._set_status("已存在")
            return

        self.favorites.append(t)

        # Store type; when missing, read the current mode from the parent window.
        if content_type is None:
            p = self.parent()
            if p and hasattr(p, "_formula_types") and t in p._formula_types:
                content_type = p._formula_types.get(t)
            elif p:
                try:
                    content_type = getattr(getattr(p, "model", None), "last_used_model", None)
                except Exception:
                    content_type = None
                if not content_type and hasattr(p, "current_model"):
                    content_type = p.current_model
            if not content_type:
                content_type = "mathcraft"
        self._favorite_types[t] = normalize_content_type(content_type)

        # Store name; when missing, read it from the parent window.
        if name is None:
            p = self.parent()
            if p and hasattr(p, "_formula_names"):
                name = p._formula_names.get(t, "")
        if name:
            self._favorite_names[t] = name

        self.refresh_list()
        self.save_favorites()
        self.show()
        self.raise_()
        self.activateWindow()
        self._set_status("已加入收藏")

"""Favorites window."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import Action, InfoBar, InfoBarPosition, RoundMenu

from localization.manager import translate as tr
from preview.math_preview import preview_theme_tokens
from runtime.app_paths import resource_path
from runtime.config_manager import default_user_data_file
from runtime.content_types import ContentType, normalize_content_type
from ui.edit_formula_dialog import EditFormulaDialog
from ui.formula_export_menu import populate_formula_export_menu
from ui.window_helpers import (
    apply_close_only_window_flags as _apply_close_only_window_flags,
)
from ui.window_helpers import (
    exec_close_only_message_box,
    show_formula_rename_dialog,
    show_normal_window,
)

logger = logging.getLogger(f"latexsnipper.{__name__}")
DEFAULT_FAVORITES_NAME = "favorites.json"


class FavoritesWindow(QMainWindow):
    """Favorites window with list-only functionality."""

    def __init__(
        self,
        cfg,
        *,
        export_formula: Callable[[str, str, QWidget], None],
        parent=None,
        select_export_directory=None,
        history,
        preview,
        status,
    ):
        super().__init__(parent)
        self.history = history
        self.preview = preview
        self.status = status
        self.cfg = cfg
        self._export_formula = export_formula
        self._select_export_directory = (
            select_export_directory or self._select_export_directory_fallback
        )
        self._theme_is_dark_cached = None
        self.setWindowFlag(Qt.WindowType.Window, True)
        _apply_close_only_window_flags(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle(tr("公式收藏夹"))
        self.setMinimumSize(400, 350)
        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        container = QWidget()
        main_lay = QVBoxLayout(container)
        main_lay.setContentsMargins(6, 6, 6, 6)
        main_lay.setSpacing(6)
        from qfluentwidgets import FluentIcon, PushButton

        top_btn_layout = QHBoxLayout()
        btn_export_data = PushButton(FluentIcon.SAVE, tr("导出收藏夹"))
        btn_export_data.clicked.connect(self.export_data)
        top_btn_layout.addWidget(btn_export_data)
        btn_clear = PushButton(FluentIcon.DELETE, tr("清空收藏夹"))
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
        self.list_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_lay.addWidget(self.list_widget, 1)
        close_btn = PushButton(FluentIcon.CLOSE, tr("关闭窗口"))
        close_btn.clicked.connect(self.close)
        main_lay.addWidget(close_btn, 0)
        self.setCentralWidget(container)
        self.favorites = []
        self._favorite_names = {}
        self._favorite_types = {}
        self.file_path = str(default_user_data_file(DEFAULT_FAVORITES_NAME))
        self.load_favorites()
        from PyQt6.QtGui import QKeySequence, QShortcut

        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.close)
        self.apply_theme_styles(force=True)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _favorites_list_qss(self) -> str:
        t = preview_theme_tokens()
        return f"\n            QListWidget {{\n                border: none;\n                background: transparent;\n                outline: none;\n            }}\n            QListWidget::item {{\n                border-bottom: 1px solid {t['table_border']};\n                padding: 8px 6px;\n                color: {t['body_text']};\n                background: transparent;\n                outline: none;\n                border-left: none;\n                border-right: none;\n            }}\n            QListWidget::item:hover {{\n                background: {t['panel_bg']};\n            }}\n            QListWidget::item:selected {{\n                background: {t['badge_formula_bg']};\n                color: {t['body_text']};\n                border: none;\n                outline: none;\n            }}\n            QListWidget::item:selected:active {{\n                background: {t['badge_formula_bg']};\n                color: {t['body_text']};\n                border: none;\n                outline: none;\n            }}\n            QListWidget::item:selected:!active {{\n                background: {t['badge_formula_bg']};\n                color: {t['body_text']};\n                border: none;\n                outline: none;\n            }}\n            QListWidget::item:focus {{\n                border: none;\n                outline: none;\n            }}\n        "

    def apply_theme_styles(self, force: bool = False):
        dark = False
        try:
            from qfluentwidgets import isDarkTheme

            dark = bool(isDarkTheme())
        except Exception:
            try:
                pal = self.palette().window().color()
                dark = (pal.red() + pal.green() + pal.blue()) / 3.0 < 128
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

    def _set_status(self, msg: str):
        self.status.set_action_status(msg)

    def _on_item_double_clicked(self, item):
        latex = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self.preview.set_editor_text(latex)
        name = self._favorite_names.get(latex, "") or self.history.label_for(latex)
        index = self.list_widget.row(item) + 1
        label = f"#{index} {name}".strip()
        self.preview.render_latex_in_preview(latex, self._favorite_types[latex], label)
        self._set_status(tr("已加载到编辑器"))

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            return
        menu = RoundMenu(parent=self)
        menu.addAction(Action(tr("复制"), triggered=lambda: self._copy_item(latex)))
        export_menu = RoundMenu(tr("导出为..."), parent=menu)
        populate_formula_export_menu(
            export_menu,
            lambda format_type: self._export_formula(format_type, latex, self),
        )
        menu.addMenu(export_menu)
        menu.addSeparator()
        menu.addAction(
            Action(tr("添加到历史"), triggered=lambda: self._add_to_history(latex))
        )
        menu.addAction(Action(tr("重命名"), triggered=lambda: self._rename_item(latex)))
        menu.addAction(
            Action(tr("编辑"), triggered=lambda: self._edit_item(item, latex))
        )
        menu.addAction(Action(tr("删除"), triggered=lambda: self._delete_item(latex)))
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _add_to_history(self, latex: str):
        if self.history.contains(latex):
            self._set_status(tr("公式已在历史中"))
            return
        self.history.add_named_record(
            latex, self._favorite_types[latex], self._favorite_names.get(latex, "")
        )

    def _copy_item(self, latex: str):
        """Copy the formula to the clipboard."""
        import pyperclip

        if latex:
            pyperclip.copy(latex)
            self._set_status(tr("已复制到剪贴板"))

    def _rename_item(self, latex: str):
        current_name = self._favorite_names.get(latex, "") or self.history.label_for(
            latex
        )
        new_name, ok = show_formula_rename_dialog(
            self,
            current_name=current_name,
            title=tr("公式命名"),
            prompt=tr("输入公式名称："),
        )
        if not ok:
            return
        self.set_label(latex, new_name)
        self.history.set_label(latex, new_name)
        self._set_status(
            tr("已命名为: {name}").format(name=new_name)
            if new_name
            else tr("已清除名称")
        )

    def _edit_item(self, item, latex: str):
        """Edit formula content."""
        dlg = EditFormulaDialog(latex, self, content_type=self._favorite_types[latex])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.value()
            if new and new != latex:
                if latex in self.favorites:
                    idx = self.favorites.index(latex)
                    self.favorites[idx] = new
                    if latex in self._favorite_names:
                        self._favorite_names[new] = self._favorite_names.pop(latex)
                    if latex in self._favorite_types:
                        self._favorite_types[new] = self._favorite_types.pop(latex)
                    self.save_favorites()
                    self.refresh_list()
                    self._set_status(tr("已更新"))

    def _delete_item(self, latex: str):
        """Delete a favorite item."""
        if latex in self.favorites:
            self.favorites.remove(latex)
            self._favorite_names.pop(latex, None)
            self._favorite_types.pop(latex, None)
            self.refresh_list()
            self.save_favorites()
            self._set_status(tr("已删除"))

    def refresh_list(self):
        self.list_widget.clear()
        type_names = {
            "mathcraft": tr("公式"),
            "mathcraft_text": tr("文字"),
            "mathcraft_mixed": tr("混合"),
        }
        for idx, formula in enumerate(self.favorites, start=1):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, formula)
            name = self._favorite_names.get(formula, "")
            if not name:
                name = self.history.label_for(formula)
            content_type = self._favorite_types[formula]
            type_display = type_names.get(content_type, "")
            parts = [f"#{idx}"]
            if name:
                parts.append(f"[{name}]")
            if content_type != "mathcraft" and type_display:
                parts.append(f"<{type_display}>")
            display_text = " ".join(parts) + f"\n{formula}"
            item.setText(display_text)
            item.setToolTip(formula)
            from PyQt6.QtCore import QSize

            item.setSizeHint(QSize(0, 50))
            self.list_widget.addItem(item)
        self.list_widget.setStyleSheet(self._favorites_list_qss())

    def _favorites_data(self) -> dict:
        return {
            "favorites": self.favorites,
            "names": self._favorite_names,
            "types": self._favorite_types,
        }

    def _select_export_directory_fallback(
        self, parent, title: str, initial_dir: str
    ) -> str:
        return QFileDialog.getExistingDirectory(parent, title, initial_dir)

    def export_data(self):
        directory = self._select_export_directory(
            self, tr("选择收藏夹导出文件夹"), str(Path(self.file_path).parent)
        )
        if not directory:
            return
        target = Path(directory) / DEFAULT_FAVORITES_NAME
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(self._favorites_data(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self._set_status(tr("导出失败: {error}").format(error=e))
            return
        self._set_status(tr("已导出收藏夹: {path}").format(path=target))

    def load_favorites(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    fav_list = data.get("favorites", [])
                    self.favorites = [str(x) for x in fav_list]
                    names = data.get("names", {})
                    if isinstance(names, dict):
                        self._favorite_names = {
                            str(k): str(v) for k, v in names.items()
                        }
                    types = data.get("types", {})
                    if isinstance(types, dict):
                        self._favorite_types = {
                            str(k): normalize_content_type(str(v))
                            for k, v in types.items()
                        }
            except Exception as e:
                logger.warning("收藏夹加载失败: %s", e)
        self.refresh_list()

    def save_favorites(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._favorites_data(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("收藏夹保存失败: %s", e)

    def _clear_all_favorites(self):
        """Clear all favorites."""
        if not self.favorites:
            info_parent = self.parent() if self.parent() is not None else self
            InfoBar.info(
                title=tr("提示"),
                content=tr("收藏夹已经是空的"),
                parent=info_parent,
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return
        ret = exec_close_only_message_box(
            self,
            tr("确认"),
            tr("确定要清空所有 {count} 条收藏吗？").format(count=len(self.favorites)),
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
        self._set_status(tr("已清空收藏夹"))

    def add_favorite(
        self, text: str, content_type: ContentType, name: str | None = None
    ):
        """Add a favorite item."""
        t = (text or "").strip()
        if not t:
            self._set_status(tr("空公式，忽略"))
            return
        if t in self.favorites:
            self._set_status(tr("已存在"))
            return
        self.favorites.append(t)
        self._favorite_types[t] = normalize_content_type(content_type)
        if name is None:
            name = self.history.label_for(t)
        if name:
            self._favorite_names[t] = name
        self.refresh_list()
        self.save_favorites()
        show_normal_window(self)
        self._set_status(tr("已加入收藏"))

    def set_label(self, text, label):
        if text not in self.favorites:
            return
        if label:
            self._favorite_names[text] = label
        else:
            self._favorite_names.pop(text, None)
        self.save_favorites()
        self.refresh_list()

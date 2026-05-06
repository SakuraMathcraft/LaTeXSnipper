"""Favorites window."""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import InfoBar, InfoBarPosition

from preview.math_preview import (
    latex_display,
    latex_equation,
    latex_inline,
    mathml_standardize,
    mathml_to_html_fragment,
    mathml_with_prefix,
    normalize_latex_for_export,
    preview_theme_tokens,
    latex_to_svg,
)
from runtime.app_paths import resource_path
from runtime.config_manager import normalize_content_type, resolve_user_data_file
from ui.edit_formula_dialog import EditFormulaDialog
from ui.window_helpers import (
    apply_close_only_window_flags as _apply_close_only_window_flags,
    exec_close_only_message_box,
    show_formula_rename_dialog,
)

DEFAULT_FAVORITES_NAME = "favorites.json"

class FavoritesWindow(QMainWindow):
    """收藏夹窗口 - 简化版，只保留列表功能"""
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

        # 使用容器 widget
        container = QWidget()
        main_lay = QVBoxLayout(container)
        main_lay.setContentsMargins(6, 6, 6, 6)
        main_lay.setSpacing(6)
        
        from qfluentwidgets import PushButton, FluentIcon
        
        # 顶部按钮行
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

        # 将容器设置为中心 widget
        self.setCentralWidget(container)

        self.favorites = []
        self._favorite_names = {}   # 收藏名称: {content: name}
        self._favorite_types = {}   # 收藏类型: {content: content_type}
        favorites_path = resolve_user_data_file(self.cfg, "favorites_path", DEFAULT_FAVORITES_NAME)
        self.file_path = favorites_path
        self.load_favorites()

        # --- 新增: ESC 快捷关闭（备用方案，防止某些子控件截获按键） ---
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.close)
        self.apply_theme_styles(force=True)

    # --- 新增: 捕获 ESC 按键 ---
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

    # ---------- 状态 ----------
    def _set_status(self, msg: str):
        p = self.parent()
        if p and hasattr(p, "set_action_status"):
            p.set_action_status(msg)
    
    def _on_item_double_clicked(self, item):
        """双击加载公式到编辑器并渲染"""
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            latex = item.text()
        
        p = self.parent()
        if p and hasattr(p, 'latex_editor') and hasattr(p, 'render_latex_in_preview'):
            if hasattr(p, "_set_editor_text_silent"):
                p._set_editor_text_silent(latex)
            else:
                p.latex_editor.setPlainText(latex)
            
            # 确保父窗口有这个内容的类型信息
            content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            
            # 获取编号和名称（优先使用收藏夹的名称）
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

    # ---------- 菜单 ----------
    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            return
        
        menu = QMenu(self)
        a_copy = menu.addAction("复制")
        
        # 导出子菜单 - 增加更多导出格式
        export_menu = menu.addMenu("导出为...")
        a_latex = export_menu.addAction("LaTeX (行内 $...$)")
        alatex_display = export_menu.addAction("LaTeX (display \\[...\\])")
        alatex_equation = export_menu.addAction("LaTeX (equation 编号)")
        export_menu.addSeparator()
        a_md_inline = export_menu.addAction("Markdown (行内 $...$)")
        a_md_block = export_menu.addAction("Markdown (块级 $$...$$)")
        export_menu.addSeparator()
        a_mathml = export_menu.addAction("MathML")
        a_mathml_mml = export_menu.addAction("MathML (.mml)")
        a_mathml_m = export_menu.addAction("MathML (<m>)")
        a_mathml_attr = export_menu.addAction("MathML (attr)")
        export_menu.addSeparator()
        a_html = export_menu.addAction("HTML")
        a_omml = export_menu.addAction("Word OMML")
        a_svgcode = export_menu.addAction("SVG Code")
        
        menu.addSeparator()
        a_add_history = menu.addAction("添加到历史")
        a_rename = menu.addAction("重命名")
        a_edit = menu.addAction("编辑")
        a_del = menu.addAction("删除")
        act = menu.exec(self.list_widget.mapToGlobal(pos))
        if act == a_copy:
            self._copy_item(latex)
        elif act == a_add_history:
            self._add_to_history(latex)
        elif act == a_rename:
            self._rename_item(latex)
        elif act == a_edit:
            self._edit_item(item, latex)
        elif act == a_del:
            self._delete_item(latex)
        elif act == a_latex:
            self._export_as("latex", latex)
        elif act == alatex_display:
            self._export_as("latex_display", latex)
        elif act == alatex_equation:
            self._export_as("latex_equation", latex)
        elif act == a_html:
            self._export_as("html", latex)
        elif act == a_md_inline:
            self._export_as("markdown_inline", latex)
        elif act == a_md_block:
            self._export_as("markdown_block", latex)
        elif act == a_mathml:
            self._export_as("mathml", latex)
        elif act == a_mathml_mml:
            self._export_as("mathml_mml", latex)
        elif act == a_mathml_m:
            self._export_as("mathml_m", latex)
        elif act == a_mathml_attr:
            self._export_as("mathml_attr", latex)
        elif act == a_omml:
            self._export_as("omml", latex)
        elif act == a_svgcode:
            self._export_as("svgcode", latex)
    
    def _add_to_history(self, latex: str):
        """将收藏夹公式添加到历史记录（继承标签和类型）"""
        p = self.parent()
        if not p or not hasattr(p, 'history'):
            self._set_status("无法添加到历史")
            return
        
        if latex in p.history:
            self._set_status("公式已在历史中")
            return
        
        # 获取收藏的类型
        content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
        # 继承名称（先写入历史名称映射，确保新插入行立即显示标签）
        name = self._favorite_names.get(latex, "")
        if name and hasattr(p, '_formula_names'):
            p._formula_names[latex] = name
        
        # 使用 add_history_record 方法添加（会自动处理类型）
        if hasattr(p, 'add_history_record'):
            p.add_history_record(latex, content_type)
        else:
            # 回退方式
            p.history.insert(0, latex)
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            if hasattr(p, 'save_history'):
                p.save_history()
            if hasattr(p, 'rebuild_history_ui'):
                p.rebuild_history_ui()
            self._set_status("已添加到历史记录")

    def _export_as(self, format_type: str, latex: str):
        """导出公式为指定格式（统一使用 matplotlib SVG）"""
        result = ""
        format_name = ""
        clean = normalize_latex_for_export(latex)

        if format_type == "latex":
            result = latex_inline(clean)
            format_name = "LaTeX (行内)"
        elif format_type == "latex_display":
            result = latex_display(clean)
            format_name = "LaTeX (display \\[\\])"
        elif format_type == "latex_equation":
            result = latex_equation(clean)
            format_name = "LaTeX (equation)"
        elif format_type == "html":
            # HTML 格式
            try:
                result = mathml_to_html_fragment(self._latex_to_mathml(clean))
            except Exception as e:
                self._set_status(f"HTML 导出失败: {e}")
                return
            format_name = "HTML"
        elif format_type == "markdown_inline":
            result = latex_inline(clean)
            format_name = "Markdown 行内"
        elif format_type == "markdown_block":
            result = f"$$\n{clean}\n$$"
            format_name = "Markdown 块级"
        elif format_type == "mathml":
            try:
                result = self._latex_to_mathml(clean)
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML"
        elif format_type == "mathml_mml":
            try:
                result = mathml_with_prefix(self._latex_to_mathml(clean), "mml")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (.mml)"
        elif format_type == "mathml_m":
            try:
                result = mathml_with_prefix(self._latex_to_mathml(clean), "m")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (<m>)"
        elif format_type == "mathml_attr":
            try:
                result = mathml_with_prefix(self._latex_to_mathml(clean), "attr")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (attr)"
        elif format_type == "omml":
            try:
                result = self._latex_to_omml(clean)
            except Exception as e:
                self._set_status(f"OMML 导出失败: {e}")
                return
            format_name = "Word OMML"
        elif format_type == "svgcode":
            try:
                result = self._latex_to_svg_code(clean)
            except Exception as e:
                self._set_status(f"SVG 导出失败: {e}")
                return
            format_name = "SVG Code"
        
        if result:
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.clipboard().setText(result)
                self._set_status(f"已复制 {format_name} 格式")
            except Exception:
                try:
                    import pyperclip
                    pyperclip.copy(result)
                    self._set_status(f"已复制 {format_name} 格式")
                except Exception:
                    self._set_status("复制失败")
    
    def _latex_to_svg_code(self, latex: str) -> str:
        """将 LaTeX 转换为 SVG 代码"""
        return latex_to_svg(latex)
    
    def _latex_to_mathml(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 格式"""
        latex = normalize_latex_for_export(latex)
        import latex2mathml.converter
        mathml = latex2mathml.converter.convert(latex)
        return mathml_standardize(mathml)
    
    def _latex_to_mathml_element(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML <m> 元素格式"""
        return mathml_with_prefix(self._latex_to_mathml(latex), "m")
    
    def _latex_to_mathml_with_attr(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 属性格式"""
        return mathml_with_prefix(self._latex_to_mathml(latex), "attr")
    def _latex_to_omml(self, latex: str) -> str:
        """将 LaTeX 转换为 OMML 格式"""
        try:
            latex = normalize_latex_for_export(latex)
            import latex2mathml.converter as _latex2mathml_converter
            _ = _latex2mathml_converter
            mathml = self._latex_to_mathml(latex)

            try:
                from lxml import etree
                import os

                xsl_paths = [
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
                ]

                for xsl_path in xsl_paths:
                    if os.path.exists(xsl_path):
                        xslt = etree.parse(xsl_path)
                        transform = etree.XSLT(xslt)
                        doc = etree.fromstring(mathml.encode())
                        result = transform(doc)
                        return str(result)

                return mathml
            except ImportError:
                return mathml
        except ImportError:
            escaped = latex.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            return f"{{ EQ \\\\o\\\\al(\\\\lc\\\\(({escaped})\\\\rc\\\\))"
        except Exception:
            raise

    def _copy_item(self, latex: str):
        """复制公式到剪贴板"""
        import pyperclip
        if latex:
            pyperclip.copy(latex)
            self._set_status("已复制到剪贴板")

    def _rename_item(self, latex: str):
        """重命名收藏夹中的公式"""
        p = self.parent()
        # 使用收藏夹自己的名称字典
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

        # 保存收藏夹
        self.save_favorites()

        # 刷新列表显示
        self.refresh_list()
        # 同步刷新主窗口历史记录（否则历史中的同公式名称不会立即更新）
        if p and hasattr(p, "rebuild_history_ui"):
            p.rebuild_history_ui()
        # 同步刷新主窗口预览中的标签（否则预览标签可能保持旧名称）
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
        """编辑公式内容"""
        dlg = EditFormulaDialog(latex, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.value()
            if new and new != latex:
                # 查找在 favorites 中的索引
                if latex in self.favorites:
                    idx = self.favorites.index(latex)
                    self.favorites[idx] = new

                    # 更新收藏夹自己的名称和类型映射
                    if latex in self._favorite_names:
                        self._favorite_names[new] = self._favorite_names.pop(latex)
                    if latex in self._favorite_types:
                        self._favorite_types[new] = self._favorite_types.pop(latex)

                    self.save_favorites()
                    self.refresh_list()
                    self._set_status("已更新")

    def _delete_item(self, latex: str):
        """删除收藏项"""
        if latex in self.favorites:
            self.favorites.remove(latex)
            # 清理名称和类型映射
            self._favorite_names.pop(latex, None)
            self._favorite_types.pop(latex, None)
            self.refresh_list()
            self.save_favorites()
            self._set_status("已删除")

    # ---------- 列表/文件 ----------
    def refresh_list(self):
        self.list_widget.clear()

        # 类型显示名称
        type_names = {
            "mathcraft": "公式",
            "mathcraft_text": "文字",
            "mathcraft_mixed": "混合",
        }

        for idx, formula in enumerate(self.favorites, start=1):
            # 创建带样式的列表项
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, formula)  # 存储原始公式

            # 获取名称和类型（优先使用收藏夹自己的）
            name = self._favorite_names.get(formula, "")
            if not name:
                p = self.parent()
                if p and hasattr(p, "_formula_names"):
                    name = p._formula_names.get(formula, "")
            content_type = normalize_content_type(self._favorite_types.get(formula, "mathcraft"))
            type_display = type_names.get(content_type, "")

            # 构建显示文本
            parts = [f"#{idx}"]
            if name:
                parts.append(f"[{name}]")
            if type_display and type_display != "公式":  # 公式是默认，不显示
                parts.append(f"<{type_display}>")
            display_text = " ".join(parts) + f"\n{formula}"

            item.setText(display_text)
            item.setToolTip(formula)

            # 设置项目大小和样式
            from PyQt6.QtCore import QSize
            item.setSizeHint(QSize(0, 50))  # 最小高度

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
                    # 新格式：包含收藏列表、名称和类型
                    fav_list = data.get("favorites", [])
                    self.favorites = [str(x) for x in fav_list]
                    # 加载名称
                    names = data.get("names", {})
                    if isinstance(names, dict):
                        self._favorite_names = {str(k): str(v) for k, v in names.items()}
                    # 加载类型
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
            # 保存收藏列表、名称和类型
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
        """清空所有收藏"""
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

    # ---------- 对外 ----------
    def add_favorite(self, text: str, content_type: str = None, name: str = None):
        """添加收藏

        Args:
            text: 内容文本
            content_type: 内容类型 (mathcraft, mathcraft_mixed 等)
            name: 自定义名称
        """
        t = (text or "").strip()
        if not t:
            self._set_status("空公式，忽略")
            return
        if t in self.favorites:
            self._set_status("已存在")
            return

        self.favorites.append(t)

        # 存储类型（如果没指定，从父窗口获取当前模式）
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

        # 存储名称（如果没指定，从父窗口获取）
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

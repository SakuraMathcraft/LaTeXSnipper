from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QUrl, QUrlQuery, Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, PushButton, isDarkTheme

from editor.latex_snippet_panel import LaTeXSnippetPanel
from editor.workbench_bridge import WorkbenchBridge
from localization.manager import (
    current_ui_language,
    mark_for_translation,
    translate as tr,
)
from runtime.app_paths import resource_path


class WorkbenchWindow(QWidget):
    EXAMPLES = {
        "fraction": (mark_for_translation("分式计算"), r"\frac{1}{3}+\frac{5}{12}"),
        "trigonometry": (mark_for_translation("三角恒等式"), r"\sin\left(\frac{\pi}{4}\right)^2+\cos\left(\frac{\pi}{4}\right)^2"),
        "polynomial": (mark_for_translation("多项式展开"), r"(x+1)^3"),
        "factor": (mark_for_translation("因式分解"), r"x^2-5x+6"),
        "equation": (mark_for_translation("方程求解"), r"x^2-5x+6=0"),
        "sum_root": (mark_for_translation("求和开方"), r"\sqrt{6\sum_{n=1}^{\infty} \frac{1}{n^2}}"),
        "derivative": (mark_for_translation("导数"), r"\frac{d}{dx}\left(x^3+3x^2+1\right)"),
        "definite_integral": (mark_for_translation("定积分"), r"\int_0^1 x^2\,dx"),
        "limit": (mark_for_translation("极限"), r"\lim_{x\to 0}\frac{\sin x}{x}"),
        "improper_integral": (mark_for_translation("广义积分"), r"\int_0^{\infty} e^{-x}\,dx"),
        "geometric_series": (mark_for_translation("几何级数"), r"\sum_{n=0}^{\infty} \left(\frac{1}{2}\right)^n"),
        "infinite_series": (mark_for_translation("无穷级数"), r"\sum_{n=1}^{\infty} \frac{1}{n^2}"),
        "infinite_product": (mark_for_translation("无穷乘积"), r"\prod_{n=1}^{\infty}\left(1-\frac{1}{2^n}\right)"),
        "wallis_product": (mark_for_translation("Wallis 乘积"), r"\prod_{n=1}^{\infty}\frac{4n^2}{4n^2-1}"),
    }
    COPY_ACTIONS = {
        "latex": mark_for_translation("复制 LaTeX"),
        "mathjson": mark_for_translation("复制 MathJSON"),
    }

    def __init__(self, parent=None, on_insert_latex=None):
        # Keep a logical owner, but create a true top-level desktop window.
        super().__init__(None)
        self._owner = parent
        self._on_insert_latex = on_insert_latex
        self._pending_latex = ""
        self._theme_is_dark_cached = None
        self._centered_once = False

        self.setWindowTitle(tr("数学工作台"))
        self.resize(1160, 700)
        self.setMinimumSize(1160, 700)
        try:
            self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        except Exception:
            pass
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        self.title_label = QLabel(tr("工作台"))
        top_bar.addWidget(self.title_label)
        top_bar.addStretch()

        self.load_btn = PushButton(FluentIcon.FOLDER, tr("载入"))
        self.eval_btn = PushButton(FluentIcon.LABEL, tr("计算"))
        self.simplify_btn = PushButton(FluentIcon.PENCIL_INK, tr("化简"))
        self.numeric_btn = PushButton(FluentIcon.CALORIES, tr("数值化"))
        self.solve_btn = PushButton(FluentIcon.COMMAND_PROMPT, tr("求解"))
        self.expand_btn = PushButton(FluentIcon.ZOOM, tr("展开"))
        self.factor_btn = PushButton(FluentIcon.TILES, tr("因式分解"))
        self.multiline_combo = ComboBox()
        self.multiline_apply_btn = PushButton(FluentIcon.APPLICATION, tr("应用"))
        self.snippet_panel = LaTeXSnippetPanel(self, on_insert_key=self._insert_snippet_key)
        self.snippet_combo = self.snippet_panel.combo
        self.snippet_insert_btn = self.snippet_panel.button
        self.copy_combo = ComboBox()
        self.copy_run_btn = PushButton(FluentIcon.PASTE, tr("复制"))
        self.insert_btn = PushButton(FluentIcon.FOLDER_ADD, tr("写回"))
        self.example_combo = ComboBox()
        self.example_load_btn = PushButton(FluentIcon.CONNECT, tr("载入"))
        self.multiline_combo.addItem("displaylines", userData="displaylines")
        self.multiline_combo.addItem("multline", userData="multline")
        self.multiline_combo.addItem("align", userData="align")
        for key, label in self.COPY_ACTIONS.items():
            self.copy_combo.addItem(tr(label), userData=key)
        for key, (label, _latex) in self.EXAMPLES.items():
            self.example_combo.addItem(tr(label), userData=key)

        for btn in (
            self.load_btn,
            self.eval_btn,
            self.simplify_btn,
            self.numeric_btn,
            self.solve_btn,
            self.expand_btn,
            self.factor_btn,
            self.multiline_apply_btn,
            self.snippet_insert_btn,
            self.copy_run_btn,
            self.insert_btn,
            self.example_load_btn,
        ):
            btn.setFixedHeight(30)
            btn.setMinimumWidth(0)
        self.example_combo.setFixedHeight(32)
        self.example_combo.setMinimumWidth(132)
        self.multiline_combo.setFixedHeight(32)
        self.multiline_combo.setMinimumWidth(112)
        self.copy_combo.setFixedHeight(32)
        self.copy_combo.setMinimumWidth(126)

        top_bar.addWidget(self._make_group_label(tr("工作流")))
        top_bar.addWidget(self.load_btn)
        top_bar.addWidget(self.insert_btn)
        top_bar.addWidget(self._make_group_divider())
        top_bar.addWidget(self._make_group_label(tr("基础运算")))
        top_bar.addWidget(self.eval_btn)
        top_bar.addWidget(self.simplify_btn)
        top_bar.addWidget(self.numeric_btn)
        top_bar.addWidget(self.solve_btn)
        top_bar.addWidget(self._make_group_divider())
        top_bar.addWidget(self._make_group_label(tr("排版")))
        top_bar.addWidget(self.multiline_combo)
        top_bar.addWidget(self.multiline_apply_btn)
        top_bar.addStretch()
        root.addLayout(top_bar)

        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)
        bottom_bar.addWidget(self._make_group_label(tr("进阶运算")))
        bottom_bar.addWidget(self.expand_btn)
        bottom_bar.addWidget(self.factor_btn)
        bottom_bar.addWidget(self._make_group_divider())
        bottom_bar.addWidget(self._make_group_label(tr("快捷插入")))
        bottom_bar.addWidget(self.snippet_panel)
        bottom_bar.addWidget(self._make_group_divider())
        bottom_bar.addWidget(self._make_group_label(tr("示例")))
        bottom_bar.addWidget(self.example_combo)
        bottom_bar.addWidget(self.example_load_btn)
        bottom_bar.addWidget(self._make_group_divider())
        bottom_bar.addWidget(self._make_group_label(tr("复制")))
        bottom_bar.addWidget(self.copy_combo)
        bottom_bar.addWidget(self.copy_run_btn)
        bottom_bar.addStretch()
        root.addLayout(bottom_bar)

        self.web_view = QWebEngineView(self)
        root.addWidget(self.web_view, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.setContentsMargins(0, 0, 0, 0)
        self.status_caption = QLabel(tr("状态"))
        self.status_caption.setObjectName("workbenchStatusCaption")
        self.status_label = QLabel(tr("正在加载数学工作台..."))
        self.status_label.setObjectName("workbenchStatusText")
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer.addWidget(self.status_caption)
        footer.addWidget(self.status_label, 1)
        root.addLayout(footer)

        self.setStyleSheet(
            """
            QLabel#workbenchStatusCaption {
                color: #7f8ea3;
                font-size: 12px;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }
            QLabel#workbenchStatusText {
                color: #8aa9c9;
                font-size: 12px;
                padding: 2px 0 0 0;
            }
            """
        )

        self.bridge = WorkbenchBridge(self)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self.bridge.readyChanged.connect(self._on_editor_ready)
        self.bridge.statusChanged.connect(self._on_bridge_status)
        self.bridge.insertRequested.connect(self._emit_insert_request)

        self.load_btn.clicked.connect(lambda: self._emit_insert_request("__LOAD_FROM_MAIN__"))
        self.eval_btn.clicked.connect(lambda: self._run_compute_action("evaluate"))
        self.simplify_btn.clicked.connect(lambda: self._run_compute_action("simplify"))
        self.numeric_btn.clicked.connect(lambda: self._run_compute_action("numeric"))
        self.solve_btn.clicked.connect(lambda: self._run_compute_action("solve"))
        self.expand_btn.clicked.connect(lambda: self._run_compute_action("expand"))
        self.factor_btn.clicked.connect(lambda: self._run_compute_action("factor"))
        self.multiline_apply_btn.clicked.connect(self._apply_multiline_layout)
        self.copy_run_btn.clicked.connect(self._run_selected_copy_action)
        self.insert_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.insertToMain();"))
        self.example_load_btn.clicked.connect(self._load_selected_example)

        self._load_page()
        self.apply_theme_styles(force=True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._centered_once:
            return
        self._centered_once = True
        try:
            screen = None
            if self._owner is not None and self._owner.windowHandle() is not None:
                screen = self._owner.windowHandle().screen()
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())
        except Exception:
            pass

    def _asset_url(self, relative: str) -> QUrl:
        return QUrl.fromLocalFile(str(Path(resource_path(relative)).resolve()))

    def _svg_icon(self, relative: str) -> QIcon:
        try:
            return QIcon(resource_path(relative))
        except Exception:
            return QIcon()

    def _make_group_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color:#7f8ea3; font-size:12px; padding:0 4px;")
        return label

    def _make_group_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color:#3a4452;")
        return line

    def _load_page(self) -> None:
        page_url = self._asset_url("assets/mathlive/index.html")
        query = QUrlQuery()
        query.addQueryItem("lang", current_ui_language())
        page_url.setQuery(query)
        self.web_view.setUrl(page_url)

    def apply_theme_styles(self, force: bool = False) -> None:
        dark = bool(isDarkTheme())
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        mode = "dark" if dark else "light"
        self._run_js(f"window.workbenchApi?.setThemeMode('{mode}');")

    def _run_js(self, code: str) -> None:
        try:
            self.web_view.page().runJavaScript(code)
        except Exception as e:
            self._set_status(
                tr("工作台脚本调用失败: {message}").format(message=e)
            )

    def _json_arg(self, value: str) -> str:
        return json.dumps(value or "", ensure_ascii=False)

    def set_latex(self, latex: str) -> None:
        text = (latex or "").strip()
        if not text:
            return
        self._pending_latex = text
        if self.bridge.is_ready:
            self._run_js(f"window.workbenchApi?.setLatex({self._json_arg(text)});")

    def _on_editor_ready(self, _ready: bool) -> None:
        self.apply_theme_styles(force=True)
        self._set_status(tr("已就绪"))
        if self._pending_latex:
            self.set_latex(self._pending_latex)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text or "")

    def _on_bridge_status(self, level: str, text: str) -> None:
        message = (text or "").strip()
        self._set_status(message)
        if not message or not level:
            return
        if level == "info":
            self.show_info(tr("提示"), message)
            return
        if level == "error":
            self.show_error(tr("操作失败"), message)
            return
        if level == "success":
            self.show_success(tr("操作完成"), message)

    def _emit_insert_request(self, latex: str) -> None:
        if not callable(self._on_insert_latex):
            return
        self._on_insert_latex(latex)

    def _load_selected_example(self) -> None:
        key = str(self.example_combo.currentData() or "").strip()
        label, latex = self.EXAMPLES.get(key, ("", ""))
        if not latex:
            self.show_error(tr("载入失败"), tr("当前示例不存在或内容为空"))
            return
        self.set_latex(latex)
        self.show_success(
            tr("示例已载入"),
            tr("已载入示例：{name}").format(name=tr(label)),
        )

    def _apply_multiline_layout(self) -> None:
        kind = self.multiline_combo.currentData() or self.multiline_combo.currentText().strip() or "displaylines"
        self._run_js(f"window.workbenchApi?.applyMultilineLayout({self._json_arg(str(kind))});")

    def _insert_snippet_key(self, key: str) -> None:
        self._run_js(f"window.workbenchApi?.insertSnippet({self._json_arg(str(key))});")

    def _run_compute_action(self, action: str) -> None:
        action = (action or "").strip()
        js_map = {
            "evaluate": "window.workbenchApi?.evaluateExpression();",
            "simplify": "window.workbenchApi?.simplifyExpression();",
            "numeric": "window.workbenchApi?.numericEvaluate();",
            "expand": "window.workbenchApi?.expandExpression();",
            "factor": "window.workbenchApi?.factorExpression();",
            "solve": "window.workbenchApi?.solveExpression();",
        }
        code = js_map.get(action)
        if not code:
            self.show_error(tr("执行失败"), tr("当前运算动作不可用"))
            return
        self._run_js(code)

    def _run_selected_copy_action(self) -> None:
        action = (self.copy_combo.currentData() or "").strip()
        js_map = {
            "latex": "window.workbenchApi?.copyLatex();",
            "mathjson": "window.workbenchApi?.copyMathJson();",
        }
        code = js_map.get(action)
        if not code:
            self.show_error(tr("复制失败"), tr("当前复制动作不可用"))
            return
        self._run_js(code)

    def show_info(self, title: str, content: str) -> None:
        InfoBar.info(
            title=title,
            content=content,
            parent=self,
            duration=2500,
            position=InfoBarPosition.TOP,
        )

    def show_success(self, title: str, content: str) -> None:
        InfoBar.success(
            title=title,
            content=content,
            parent=self,
            duration=2500,
            position=InfoBarPosition.TOP,
        )

    def show_error(self, title: str, content: str) -> None:
        InfoBar.error(
            title=title,
            content=content,
            parent=self,
            duration=3200,
            position=InfoBarPosition.TOP,
        )

    def closeEvent(self, event) -> None:
        try:
            self.web_view.page().setWebChannel(None)
        except Exception:
            pass
        return super().closeEvent(event)

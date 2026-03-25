from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, InfoBar, InfoBarPosition, PushButton, isDarkTheme

from editor.workbench_bridge import WorkbenchBridge
from utils import resource_path


class WorkbenchWindow(QWidget):
    EXAMPLES = {
        "分式计算": r"\frac{1}{3}+\frac{5}{12}",
        "三角恒等式": r"\sin\left(\frac{\pi}{4}\right)^2+\cos\left(\frac{\pi}{4}\right)^2",
        "多项式展开": r"(x+1)^3",
        "因式分解": r"x^2-5x+6",
        "方程求解": r"x^2-5x+6=0",
        "求和开方": r"\sqrt{6\sum_{n=1}^{\infty} \frac{1}{n^2}}",
        "导数": r"\frac{d}{dx}\left(x^3+3x^2+1\right)",
        "定积分": r"\int_0^1 x^2\,dx",
        "极限": r"\lim_{x\to 0}\frac{\sin x}{x}",
        "广义积分": r"\int_0^{\infty} e^{-x}\,dx",
        "几何级数": r"\sum_{n=0}^{\infty} \left(\frac{1}{2}\right)^n",
        "无穷级数": r"\sum_{n=1}^{\infty} \frac{1}{n^2}",
        "无穷乘积": r"\prod_{n=1}^{\infty}\left(1-\frac{1}{2^n}\right)",
        "Wallis 乘积": r"\prod_{n=1}^{\infty}\frac{4n^2}{4n^2-1}",
    }

    def __init__(self, parent=None, on_insert_latex=None):
        # Keep a logical owner, but create a true top-level desktop window.
        super().__init__(None)
        self._owner = parent
        self._on_insert_latex = on_insert_latex
        self._pending_latex = ""
        self._theme_is_dark_cached = None
        self._centered_once = False

        self.setWindowTitle("LaTeXSnipper 数学工作台")
        self.resize(1160, 760)
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
        self.title_label = QLabel("数学工作台")
        top_bar.addWidget(self.title_label)
        top_bar.addStretch()

        self.load_btn = PushButton(FluentIcon.ADD, "载入主编辑器")
        self.eval_btn = PushButton(FluentIcon.PLAY, "计算")
        self.simplify_btn = PushButton(FluentIcon.EDIT, "化简")
        self.numeric_btn = PushButton(FluentIcon.CALORIES, "数值化")
        self.expand_btn = PushButton(FluentIcon.ZOOM, "展开")
        self.factor_btn = PushButton(FluentIcon.ALIGNMENT, "因式分解")
        self.solve_btn = PushButton(FluentIcon.COMMAND_PROMPT, "求解")
        self.copy_latex_btn = PushButton(FluentIcon.COPY, "复制 LaTeX")
        self.copy_json_btn = PushButton(FluentIcon.CODE, "复制 MathJSON")
        self.insert_btn = PushButton(FluentIcon.ACCEPT, "写回主编辑器")
        self.example_combo = ComboBox()
        self.example_load_btn = PushButton(FluentIcon.LIBRARY, "载入示例")
        for name in self.EXAMPLES:
            self.example_combo.addItem(name)

        for btn in (
            self.load_btn,
            self.eval_btn,
            self.simplify_btn,
            self.numeric_btn,
            self.expand_btn,
            self.factor_btn,
            self.solve_btn,
            self.copy_latex_btn,
            self.copy_json_btn,
            self.insert_btn,
            self.example_load_btn,
        ):
            btn.setFixedHeight(32)
        self.example_combo.setFixedHeight(32)
        self.example_combo.setMinimumWidth(150)

        top_bar.addWidget(self._make_group_label("工作流"))
        top_bar.addWidget(self.load_btn)
        top_bar.addWidget(self.insert_btn)
        top_bar.addWidget(self._make_group_divider())
        top_bar.addWidget(self._make_group_label("基础计算"))
        top_bar.addWidget(self.eval_btn)
        top_bar.addWidget(self.simplify_btn)
        top_bar.addWidget(self.numeric_btn)
        top_bar.addStretch()
        root.addLayout(top_bar)

        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)
        bottom_bar.addWidget(self._make_group_label("进阶计算"))
        bottom_bar.addWidget(self.expand_btn)
        bottom_bar.addWidget(self.factor_btn)
        bottom_bar.addWidget(self.solve_btn)
        bottom_bar.addWidget(self._make_group_divider())
        bottom_bar.addWidget(self._make_group_label("示例"))
        bottom_bar.addWidget(self.example_combo)
        bottom_bar.addWidget(self.example_load_btn)
        bottom_bar.addWidget(self._make_group_divider())
        bottom_bar.addWidget(self._make_group_label("复制"))
        bottom_bar.addWidget(self.copy_latex_btn)
        bottom_bar.addWidget(self.copy_json_btn)
        bottom_bar.addStretch()
        root.addLayout(bottom_bar)

        self.web_view = QWebEngineView(self)
        root.addWidget(self.web_view, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.status_caption = QLabel("状态")
        self.status_caption.setObjectName("workbenchStatusCaption")
        self.status_label = QLabel("正在加载数学工作台...")
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
        self.eval_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.evaluateExpression();"))
        self.simplify_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.simplifyExpression();"))
        self.numeric_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.numericEvaluate();"))
        self.expand_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.expandExpression();"))
        self.factor_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.factorExpression();"))
        self.solve_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.solveExpression();"))
        self.copy_latex_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.copyLatex();"))
        self.copy_json_btn.clicked.connect(lambda: self._run_js("window.workbenchApi?.copyMathJson();"))
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
            self._set_status(f"工作台脚本调用失败: {e}")

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
        self._set_status("已就绪")
        if self._pending_latex:
            self.set_latex(self._pending_latex)

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text or "")

    def _on_bridge_status(self, text: str) -> None:
        message = (text or "").strip()
        self._set_status(message)
        if not message or message in {"正在编辑", "已就绪"}:
            return
        lowered = message.lower()
        if "失败" in message or "未定义" in message or "无法" in message or "error" in lowered:
            self.show_error("操作失败", message)
            return
        success_prefixes = (
            "计算完成",
            "化简完成",
            "数值化完成",
            "展开完成",
            "因式分解完成",
            "求解完成",
            "已复制",
            "已载入",
            "已写回",
            "已切换本地高级引擎完成",
        )
        if message.startswith(success_prefixes):
            self.show_success("操作完成", message)

    def _emit_insert_request(self, latex: str) -> None:
        if not callable(self._on_insert_latex):
            return
        self._on_insert_latex(latex)

    def _load_selected_example(self) -> None:
        key = self.example_combo.currentText().strip()
        latex = self.EXAMPLES.get(key, "")
        if not latex:
            self.show_error("载入失败", "当前示例不存在或内容为空")
            return
        self.set_latex(latex)
        self.show_success("示例已载入", f"已载入示例：{key}")

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

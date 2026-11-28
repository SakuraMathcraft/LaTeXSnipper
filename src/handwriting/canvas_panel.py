"""Own the handwriting tools and their canvas viewport."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PushButton

from localization.manager import translate as tr

from .canvas_viewport import CanvasViewport
from .ink_canvas import InkCanvas
from .tools import HandwritingTool


class HandwritingCanvasPanel(QWidget):
    clear_requested = pyqtSignal()
    status_changed = pyqtSignal(str)
    mode_hint_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._tool_buttons = {
            HandwritingTool.WRITE: PushButton(FluentIcon.PENCIL_INK, tr("书写")),
            HandwritingTool.ERASE: PushButton(FluentIcon.ERASE_TOOL, tr("橡皮")),
            HandwritingTool.SELECT_CORRECT: PushButton(
                FluentIcon.CLIPPING_TOOL, tr("圈选修正")
            ),
        }
        self._base_button_styles = {
            tool: button.styleSheet() for tool, button in self._tool_buttons.items()
        }
        for tool, button in self._tool_buttons.items():
            button.setFixedHeight(34)
            button.clicked.connect(lambda checked=False, tool=tool: self.set_tool(tool))
            toolbar.addWidget(button)
        for icon, label, action in (
            (FluentIcon.DELETE, tr("清空"), self.clear_requested.emit),
            (FluentIcon.CANCEL, tr("撤销"), self._undo),
            (FluentIcon.SYNC, tr("重做"), self._redo),
        ):
            button = PushButton(icon, label)
            button.setFixedHeight(34)
            button.clicked.connect(action)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        title = QLabel(tr("手写画布"))
        title.setObjectName("handwritingSectionTitle")
        hint = QLabel(tr("支持鼠标与触控笔，可按住鼠标右键拖动画布。"))
        hint.setObjectName("handwritingHint")
        layout.addWidget(title)
        layout.addWidget(hint)
        self._canvas_view = CanvasViewport(self)
        layout.addWidget(self._canvas_view, 1)
        self._dark = False

    @property
    def canvas(self) -> InkCanvas:
        return self._canvas_view.canvas

    def set_tool(self, tool: HandwritingTool) -> None:
        self.canvas.set_tool(tool)
        labels = {
            HandwritingTool.WRITE: (tr("书写中"), tr("直接书写，停笔后自动识别")),
            HandwritingTool.ERASE: (
                tr("橡皮模式"),
                tr("像素级局部擦除命中的笔迹片段，保留其余部分"),
            ),
            HandwritingTool.SELECT_CORRECT: (
                tr("圈选修正"),
                tr("自由圈选后只擦除圈内笔段，便于局部重写"),
            ),
        }
        status, hint = labels[tool]
        self.status_changed.emit(status)
        self.mode_hint_changed.emit(hint)
        self._apply_button_styles()

    def apply_theme(self, dark: bool) -> None:
        self._dark = dark
        self.canvas.set_dark_mode(dark)
        self._apply_button_styles()

    def _apply_button_styles(self) -> None:
        dark = self._dark
        active_colors = (
            "#4da3ff" if dark else "#4f8fe8",
            "#6ab2ff" if dark else "#3f7fda",
            "#3c93ee" if dark else "#376fc0",
            "#9fd0ff" if dark else "#6aa3ef",
            "#ffffff",
        )
        inactive_colors = (
            "transparent",
            "rgba(255,255,255,0.06)" if dark else "rgba(15,23,42,0.04)",
            "rgba(255,255,255,0.1)" if dark else "rgba(15,23,42,0.08)",
            "#465162" if dark else "#d0d7de",
            "#eef2f7" if dark else "#16202a",
        )
        active_tool = self.canvas.current_tool
        for tool, button in self._tool_buttons.items():
            bg, hover, pressed, border, fg = (
                active_colors if tool is active_tool else inactive_colors
            )
            button.setStyleSheet(
                self._base_button_styles[tool]
                + f"""
                PushButton {{
                    background: {bg};
                    color: {fg};
                    border: 1px solid {border};
                }}
                PushButton:hover {{
                    background: {hover};
                    border: 1px solid {border};
                }}
                PushButton:pressed {{
                    background: {pressed};
                    border: 1px solid {border};
                }}
                """
            )

    def _undo(self) -> None:
        if self.canvas.undo():
            self.status_changed.emit(tr("已撤销"))

    def _redo(self) -> None:
        if self.canvas.redo():
            self.status_changed.emit(tr("已重做"))

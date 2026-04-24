# -*- coding: utf-8 -*-
"""Reusable dialog components."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
from qfluentwidgets import PrimaryPushButton


class LogViewerDialog(QDialog):
    """Live log viewer dialog."""

    def __init__(self, log_file: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("实时日志")
        self.resize(820, 520)
        self._log_file = Path(log_file)
        self._pos = 0

        lay = QVBoxLayout(self)
        self.lbl = QLabel(str(self._log_file))
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)

        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("打开目录")
        self.btn_clear = QPushButton("清空日志")
        self.btn_close = QPushButton("关闭")
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)

        lay.addWidget(self.lbl)
        lay.addWidget(self.txt, 1)
        lay.addLayout(btn_row)

        self.btn_open.clicked.connect(self._open_dir)
        self.btn_clear.clicked.connect(self._clear_log)
        self.btn_close.clicked.connect(self.close)

        self._ensure_file()
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._poll_file)
        self.timer.start()
        self._poll_file(_initial=True)

    def _ensure_file(self) -> None:
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._log_file.exists():
            self._log_file.write_text("", encoding="utf-8")
        self._pos = 0

    def _open_dir(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(self._log_file.parent)
            else:
                import subprocess

                subprocess.Popen(["xdg-open", str(self._log_file.parent)])
        except Exception:
            pass

    def _clear_log(self) -> None:
        try:
            self._log_file.write_text("", encoding="utf-8")
            self._pos = 0
            self.txt.clear()
        except Exception:
            pass

    def _poll_file(self, _initial: bool = False) -> None:
        try:
            with self._log_file.open("r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
            if chunk:
                self.txt.appendPlainText(chunk.rstrip("\n"))
                self.txt.verticalScrollBar().setValue(
                    self.txt.verticalScrollBar().maximum()
                )
        except Exception:
            pass

    def closeEvent(self, ev):
        try:
            self.timer.stop()
        except Exception:
            pass
        return super().closeEvent(ev)


class EditFormulaDialog(QDialog):
    """Formula editor dialog."""

    def __init__(self, latex: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑")
        flags = (
            self.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        flags = (
            flags
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        flags |= Qt.WindowType.WindowMaximizeButtonHint
        self.setWindowFlags(flags)
        self.resize(560, 360)

        lay = QVBoxLayout(self)
        self.editor = QTextEdit(self)
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(True)
        self.editor.setPlainText(latex or "")
        lay.addWidget(self.editor, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def value(self) -> str:
        return self.editor.toPlainText().strip()


class SettingsWindow(QDialog):
    """Small fallback settings dialog."""

    model_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(300, 160)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("选择公式识别模型:"))

        self.btn_mathcraft = PrimaryPushButton("MathCraft")
        lay.addWidget(self.btn_mathcraft)

        lay.addWidget(QLabel("检查更新"))
        self.btn_update = PrimaryPushButton("检查更新")
        lay.addWidget(self.btn_update)

        self.btn_mathcraft.clicked.connect(lambda: self.select_model("mathcraft"))
        self.update_model_buttons()

    def set_update_handler(self, handler) -> None:
        self.btn_update.clicked.connect(handler)

    def select_model(self, model_name: str) -> None:
        if self.parent():
            self.parent().on_model_changed(model_name)
        self.model_changed.emit(model_name)
        QMessageBox.information(self, "提示", f"已选择模型: {model_name}")
        self.update_model_buttons()

    def update_model_buttons(self) -> None:
        current = None
        if self.parent() and hasattr(self.parent(), "current_model"):
            current = self.parent().current_model

        if current == "mathcraft":
            self.btn_mathcraft.setStyleSheet("background-color: #4CAF50; color: white;")
        else:
            self.btn_mathcraft.setStyleSheet("")


def custom_warning_dialog(title: str, message: str, parent=None) -> None:
    QMessageBox.warning(parent, title, message)

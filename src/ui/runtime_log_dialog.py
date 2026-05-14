"""GUI runtime log window."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QIcon, QTextCursor
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from preview.math_preview import dialog_theme_tokens, is_dark_ui
from runtime.app_paths import resource_path


class RuntimeLogDialog(QDialog):
    """GUI runtime log window without using a system console."""

    def __init__(self, log_file: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LaTeXSnipper 初始化与运行日志")
        self.resize(980, 620)
        self._log_file = Path(log_file)
        self._pos = 0
        self._theme_is_dark_cached = None
        try:
            icon_path = resource_path("assets/icon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        lay = QVBoxLayout(self)
        self.lbl = QLabel(str(self._log_file))
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)

        use_fluent = False
        try:
            from qfluentwidgets import PushButton as FluentPushButton, FluentIcon

            use_fluent = True
        except Exception:
            FluentPushButton = None
            FluentIcon = None

        btn_row = QHBoxLayout()
        if use_fluent and FluentPushButton and FluentIcon:
            self.btn_open = FluentPushButton(FluentIcon.FOLDER, "打开目录")
            self.btn_copy_all = FluentPushButton(FluentIcon.COPY, "复制全部")
            self.btn_clear_view = FluentPushButton(FluentIcon.BROOM, "清空视图")
            self.btn_close = FluentPushButton(FluentIcon.CLOSE, "关闭")
        else:
            self.btn_open = QPushButton("打开目录")
            self.btn_copy_all = QPushButton("复制全部")
            self.btn_clear_view = QPushButton("清空视图")
            self.btn_close = QPushButton("关闭")
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_copy_all)
        btn_row.addWidget(self.btn_clear_view)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)

        lay.addWidget(self.lbl)
        lay.addWidget(self.txt, 1)
        lay.addLayout(btn_row)

        self.btn_open.clicked.connect(self._open_dir)
        self.btn_copy_all.clicked.connect(self._copy_all)
        self.btn_clear_view.clicked.connect(self._clear_view)
        self.btn_close.clicked.connect(self.hide)

        self._ensure_file()
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll_file)
        self.timer.start()
        self._poll_file(_initial=True)
        self._apply_theme_styles(force=True)

    def _apply_theme_styles(self, force: bool = False):
        dark = is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        try:
            self.lbl.setStyleSheet(f"color: {dialog_theme_tokens()['muted']};")
        except Exception:
            pass

    def _ensure_file(self):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._log_file.exists():
            self._log_file.write_text("", encoding="utf-8")
        self._pos = 0

    def _open_dir(self):
        try:
            if os.name == "nt":
                os.startfile(self._log_file.parent)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self._log_file.parent)])
        except Exception:
            pass

    def _copy_all(self):
        try:
            QApplication.clipboard().setText(self.txt.toPlainText())
            try:
                from qfluentwidgets import InfoBar, InfoBarPosition

                InfoBar.success(
                    title="已复制",
                    content="日志内容已复制到剪贴板",
                    parent=self,
                    duration=1500,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
        except Exception:
            pass

    def _clear_view(self):
        try:
            self.txt.clear()
            try:
                from qfluentwidgets import InfoBar, InfoBarPosition

                InfoBar.success(
                    title="已清空",
                    content="日志视图已清空",
                    parent=self,
                    duration=1500,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
        except Exception:
            pass

    def _poll_file(self, _initial: bool = False):
        try:
            with self._log_file.open("r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
            if chunk:
                self.txt.moveCursor(QTextCursor.MoveOperation.End)
                self.txt.insertPlainText(chunk)
                sb = self.txt.verticalScrollBar()
                sb.setValue(sb.maximum())
        except Exception:
            pass

    def closeEvent(self, ev):
        try:
            ev.ignore()
            self.hide()
            return
        except Exception:
            pass
        return super().closeEvent(ev)

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._apply_theme_styles(force=True)
        except Exception:
            pass

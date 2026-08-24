"""Dependency installation progress window."""

from __future__ import annotations

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QTextEdit, QVBoxLayout
from qfluentwidgets import FluentIcon, PushButton

from runtime.app_paths import resource_path


class InstallProgressDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("安装进度")
        self.resize(680, 440)
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

        self.info_label = QLabel("正在遍历寻找缺失的库，完成后将自动下载，请不要关闭此窗口(๑•̀ㅂ•́)و✧)...")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setMinimumWidth(400)
        self.cancel_button = PushButton(FluentIcon.CLOSE, "退出下载")
        self.cancel_button.setFixedHeight(32)
        self.pause_button = PushButton(FluentIcon.PAUSE, "暂停下载")
        self.pause_button.setFixedHeight(32)

        button_row = QHBoxLayout()
        button_row.addWidget(self.pause_button)
        button_row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.log_view, 1)
        layout.addWidget(self.progress_bar)
        layout.addLayout(button_row)
        self._theme_is_dark_cached: bool | None = None
        self._apply_theme_styles(force=True)

    @staticmethod
    def _is_dark_ui() -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        color = app.palette().window().color()
        return (color.red() + color.green() + color.blue()) / 3.0 < 128

    def _apply_theme_styles(self, *, force: bool = False) -> None:
        dark = self._is_dark_ui()
        if not force and self._theme_is_dark_cached == dark:
            return
        self._theme_is_dark_cached = dark
        muted = "#a9b3bf" if dark else "#666666"
        text = "#e7ebf0" if dark else "#222222"
        background = "#232934" if dark else "#ffffff"
        border = "#465162" if dark else "#cfd6dd"
        chunk = "#4c9aff" if dark else "#1976d2"
        self.info_label.setStyleSheet(f"color: {muted};")
        self.progress_bar.setStyleSheet(
            "QProgressBar {"
            f"border: 1px solid {border}; border-radius: 6px; text-align: center; "
            f"background-color: {background}; color: {text};"
            "}"
            f"QProgressBar::chunk {{ background: {chunk}; border-radius: 6px; }}"
        )

    def event(self, event) -> bool:
        if event.type() in {
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        }:
            self._apply_theme_styles()
        return super().event(event)

    def showEvent(self, event) -> None:
        self._apply_theme_styles(force=True)
        super().showEvent(event)

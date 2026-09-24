"""Dependency installation progress window."""

from __future__ import annotations

from localization.manager import translate as tr

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)
from qfluentwidgets import FluentIcon, PushButton, ProgressBar

from runtime.app_paths import resource_path


class InstallProgressDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.confirm_cancel = False
        self.setWindowTitle(tr("安装进度"))
        self.resize(680, 440)
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

        self.info_label = QLabel(
            tr("正在遍历寻找缺失的库，完成后将自动下载，请不要关闭此窗口(๑•̀ㅂ•́)و✧)...")
        )
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setMinimumWidth(400)
        self.percent_label = QLabel("0%", self)
        self.progress_bar.valueChanged.connect(
            lambda value: self.percent_label.setText(f"{max(0, min(100, value))}%")
        )
        self.cancel_button = PushButton(FluentIcon.CLOSE, tr("退出下载"))
        self.cancel_button.setFixedHeight(32)
        self.pause_button = PushButton(FluentIcon.PAUSE, tr("暂停下载"))
        self.pause_button.setFixedHeight(32)

        button_row = QHBoxLayout()
        button_row.addWidget(self.pause_button)
        button_row.addWidget(self.cancel_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.info_label)
        layout.addWidget(self.log_view, 1)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.percent_label)
        layout.addLayout(progress_row)
        layout.addLayout(button_row)
        self._theme_is_dark_cached: bool | None = None
        self._apply_theme_styles(force=True)

    def confirm_exit(self):
        if not self.confirm_cancel:
            return True
        answer = QMessageBox.question(
            self,
            tr("退出下载？"),
            tr("退出将停止当前任务。再次进入依赖管理并开始安装时，将跳过已安装的依赖；未完成的下载可能需要重新下载。"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.confirm_cancel = False
        return True

    def reject(self):
        if self.confirm_cancel:
            self.close()
        else:
            super().reject()

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
        self.info_label.setStyleSheet(f"color: {muted};")

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

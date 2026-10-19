"""Show the exact model directories selected by the desktop worker's policy."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PushButton

from localization.manager import translate as tr
from runtime.installed_resources import installed_resources
from runtime.model_resources import desktop_model_resources

logger = logging.getLogger(f"latexsnipper.{__name__}")


class ModelResourcesDialog(QDialog):
    checked = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._directory: Path | None = None
        self._checking = False
        self.setWindowTitle(tr("模型资源"))
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        self.description = QLabel(tr("正在读取模型路径，请稍候。"), self)
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.description)
        self.rows = QWidget(self)
        self.rows_layout = QVBoxLayout(self.rows)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rows)
        layout.addStretch()
        self.open_directory = PushButton(FluentIcon.FOLDER, tr("打开目录"), self)
        self.open_directory.setEnabled(False)
        self.open_directory.clicked.connect(self._open_directory)
        layout.addWidget(self.open_directory)
        self.checked.connect(self._apply)
        self._inspect_resources()

    def _inspect_resources(self):
        if self._checking:
            return
        self._checking = True

        def inspect():
            try:
                resources = desktop_model_resources(installed_resources())
                result = resources
                error = ""
            except Exception as exc:
                logger.exception("桌面模型资源检查失败")
                result, error = None, str(exc)
            try:
                self.checked.emit(result, error)
            except RuntimeError:
                pass

        threading.Thread(target=inspect, name="model-resources", daemon=True).start()

    def _apply(self, result, error: str):
        self._checking = False
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if error:
            self._directory = None
            self.open_directory.setEnabled(False)
            self.description.setText(
                tr("模型资源检查失败：{error}").format(error=error)
            )
            return
        resources = result
        self._directory = resources.root
        self.open_directory.setEnabled(self._directory.is_dir())
        self.open_directory.setToolTip(str(self._directory))
        if resources.manifest_path is not None:
            self.description.setText(
                tr("使用安装目录中的模型；缺失或损坏时，请重新运行完整安装包。")
            )
            self._add_directory_row(tr("安装模型"), resources.root)
        else:
            self.description.setText(
                tr("源码桌面端使用 MathCraft 默认缓存，加载前按模型清单校验。")
            )
            self._add_directory_row(tr("MathCraft 缓存"), resources.root)
        names = {
            "mathcraft-formula-det": tr("公式检测"),
            "mathcraft-formula-rec": tr("公式识别"),
            "mathcraft-text-det": tr("文字检测"),
            "mathcraft-text-rec": tr("文字识别"),
        }
        for model_id in resources.manifest.models:
            self._add_directory_row(
                names.get(model_id) or model_id, resources.root / model_id
            )

    def showEvent(self, event):
        self._inspect_resources()
        super().showEvent(event)

    def _open_directory(self):
        if self._directory is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._directory)))

    def _add_directory_row(self, label: str, path: Path):
        row = QWidget(self.rows)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label, row)
        name.setMinimumWidth(130)
        layout.addWidget(name)
        location = QLabel(str(path), row)
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(location, 1)
        self.rows_layout.addWidget(row)

"""Component update presentation; task state and installation live in services."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout
from qfluentwidgets import (
    FluentIcon,
    IndeterminateProgressBar,
    ProgressBar,
    PushButton,
    TextBrowser,
)

from localization.manager import translate as tr
from runtime.product_version import PRODUCT_VERSION
from ui.window_helpers import exec_close_only_message_box, show_normal_window
from update.component_controller import ComponentUpdateController
from update.component_release import RELEASES_PAGE

_dialog = None


class ComponentUpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(tr("应用更新"))
        self.setMinimumSize(560, 400)
        self.resize(650, 460)
        self._lifecycle = getattr(getattr(parent, "context", None), "lifecycle", None)
        self._release_url = RELEASES_PAGE
        self._has_release_notes = False
        self._state = "checking"
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(tr("当前版本: {version}").format(version=PRODUCT_VERSION), self)
        )
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = ProgressBar(self, useAni=False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.busy_progress = IndeterminateProgressBar(self)
        layout.addWidget(self.busy_progress)
        self.details = TextBrowser(self)
        self.details.setOpenExternalLinks(True)
        self.details.setMarkdown(
            tr("正在获取发布说明。") + "\n\n" + f"[{tr('发布页面')}]({RELEASES_PAGE})"
        )
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        self.action = PushButton(FluentIcon.DOWNLOAD, tr("下载更新"), self)
        self.action.clicked.connect(self._act)
        self.pause = PushButton(FluentIcon.PAUSE, tr("暂停"), self)
        self.pause.clicked.connect(self._pause)
        self.link = PushButton(FluentIcon.LINK, tr("发布页面"), self)
        self.link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self._release_url))
        )
        self.cancel = PushButton(FluentIcon.CLOSE, tr("关闭"), self)
        self.cancel.clicked.connect(self.close)
        for button in (self.action, self.pause, self.link, self.cancel):
            row.addWidget(button)
        layout.addLayout(row)
        self.controller = ComponentUpdateController(self)
        self.controller.changed.connect(self._render)
        self.controller.check()

    def _render(self, state: str, data: dict) -> None:
        if state == "release":
            self._show_release_notes(data["release"])
            return
        if state == "progress":
            total = data["total"]
            self.progress.setValue(int(data["done"] * 100 / total) if total else 100)
            return
        self._state = state
        messages = {
            "source": tr(
                "源码运行使用开发者环境，请通过源码更新；安装包可在发布页面获取。"
            ),
            "checking": tr("正在检查应用更新，请稍候。"),
            "downloading": tr("正在下载应用业务包。"),
            "verifying": tr("正在校验并暂存业务包，当前安装仍可使用。"),
            "paused": tr("下载已暂停。"),
            "ready": tr("业务包已校验完成。安装时应用将退出并自动重新打开。"),
            "handoff": tr("正在准备独立安装进程；如有系统权限提示，请完成授权。"),
            "handoff-ready": tr("正在退出应用并安装已校验的业务包。"),
            "cancelled": tr("更新已取消，当前安装未改变。"),
            "failed": tr("更新失败：{error}").format(error=data.get("error", "")),
        }
        busy = state in {"checking", "verifying", "handoff", "handoff-ready"}
        self.busy_progress.setVisible(busy)
        self.busy_progress.start() if busy else self.busy_progress.stop()
        self.progress.setVisible(state in {"downloading", "paused", "ready"})
        if state == "checking":
            self.progress.setValue(0)
        self.action.setEnabled(state in {"available", "ready", "failed", "cancelled"})
        self.pause.setEnabled(state in {"downloading", "paused"})
        self.pause.setText(tr("继续") if state == "paused" else tr("暂停"))
        self.action.setText(
            tr("退出并安装")
            if state == "ready"
            else tr("重新检查")
            if state in {"failed", "cancelled"}
            else tr("下载更新")
        )
        if state == "available":
            release, plan, resources = data["release"], data["plan"], data["resources"]
            self._show_release_notes(release)
            if plan.installer_required:
                self.status.setText(
                    tr(
                        "此版本需要新的固定底座，请从发布页面下载并运行对应的完整安装包。"
                    )
                )
                self.action.setEnabled(False)
            elif (
                not plan.downloads and plan.target.version == resources.manifest.version
            ):
                self.status.setText(tr("当前应用已是最新版本。"))
                self.action.setEnabled(False)
            else:
                self.status.setText(
                    tr(
                        "目标版本 {version}；需要更新：{components}；下载约 {size:.1f} MB。"
                    ).format(
                        version=plan.target.version,
                        components=tr("应用"),
                        size=plan.download_bytes / 1048576,
                    )
                )
        else:
            self.status.setText(messages.get(state, state))
            if state == "failed" and not self._has_release_notes:
                self.details.setPlainText(messages["failed"])
        if state == "handoff-ready":
            self.cancel.setEnabled(False)
            QTimer.singleShot(0, self._exit_for_install)

    def _show_release_notes(self, release) -> None:
        self._release_url = release.url
        self._has_release_notes = True
        document = self.details.document()
        assert document is not None
        document.setBaseUrl(QUrl(release.url + "/"))
        notes = release.notes.strip() or tr("此版本未提供发布说明。")
        self.details.setMarkdown(
            f"## {release.tag}\n\n{notes}\n\n[{tr('发布页面')}]({release.url})"
        )

    def _act(self) -> None:
        if self._state == "ready":
            if self._lifecycle is None:
                self._render(
                    "failed", {"error": tr("应用退出服务不可用，安装未开始。")}
                )
                return
            self.controller.deploy()
        elif self._state in {"failed", "cancelled"}:
            self.controller.check()
        else:
            self.controller.prepare()

    def _pause(self) -> None:
        self.controller.pause()

    def _exit_for_install(self) -> None:
        if self._lifecycle is None:
            self._state = "failed"
            self.status.setText(tr("应用退出服务不可用，安装未开始。"))
            self.controller.close()
            self.cancel.setEnabled(True)
            return
        self._lifecycle.prepare_restart()
        QCoreApplication.quit()

    def closeEvent(self, event) -> None:
        if self._state == "handoff-ready":
            event.ignore()
            return
        if self._state == "downloading":
            answer = exec_close_only_message_box(
                self,
                tr("确认关闭"),
                tr("关闭窗口会暂停下载并保留进度，下次可继续。是否关闭？"),
                QMessageBox.Icon.Question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.controller.close()
        _clear_dialog(self)
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
        else:
            super().keyPressEvent(event)


def _clear_dialog(owner) -> None:
    global _dialog
    if _dialog is owner:
        _dialog = None


def check_update_dialog(parent=None):
    global _dialog
    if _dialog is not None:
        try:
            show_normal_window(_dialog)
            return _dialog
        except RuntimeError:
            _dialog = None
    dialog = ComponentUpdateDialog(parent)
    _dialog = dialog
    dialog.destroyed.connect(lambda: _clear_dialog(dialog))
    show_normal_window(dialog)
    return dialog

"""Coordinate the tour without owning recognition or model initialization."""

import sys

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import qconfig

from localization.manager import current_ui_language, translate as tr
from runtime.hotkey_config import display_hotkey
from ui.onboarding_steps import tour_steps
from ui.onboarding_view import TourSurface
from ui.runtime_log_controller import show_runtime_log_window
from update.release_types import _RELEASES_PAGE

AUTO_SHOW_KEY = "onboarding_auto_show"
PROJECT_URL = _RELEASES_PAGE.removesuffix("/releases")


class OnboardingController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.central_widget = window.centralWidget()
        self.surface = TourSurface(self.central_widget)
        self.surface.hide()
        self.steps = tour_steps()
        self.index = 0
        self.active = False
        self.automatic = False
        self.auxiliary = None
        self.surface.nextRequested.connect(self.advance)
        self.surface.backRequested.connect(self.back)
        self.surface.exitRequested.connect(self.finish)
        self.surface.actionRequested.connect(self.action)
        window.installEventFilter(self)
        self.central_widget.installEventFilter(self)
        window.modelStatusChanged.connect(self.refresh_busy)
        qconfig.themeChanged.connect(self.surface.apply_theme)

    def start_automatically(self):
        if (
            self.window.cfg.get(AUTO_SHOW_KEY, True)
            and not QApplication.activeModalWidget()
        ):
            self.start(automatic=True)

    def start(self, automatic=False):
        if self.active:
            if self.auxiliary is not None:
                self.auxiliary.raise_()
                self.auxiliary.activateWindow()
            else:
                self.surface.raise_()
                self.surface.next.setFocus()
            return
        self.active = True
        self.automatic = automatic
        self.index = 0
        self.render()

    def render(self):
        if not self.active or sip.isdeleted(self.window):
            return
        step = self.steps[self.index]
        self.surface.targets = [
            widget
            for name in step.targets
            if (widget := getattr(self.window, name, None)) is not None
        ]
        actions = []
        detail = ""
        if self.index == 2:
            detail = display_hotkey(self.window.cfg.get("hotkey"), sys.platform)
            actions = [("shortcut", tr("修改快捷键"))]
        elif self.index == 3:
            actions = [("logs", tr("查看日志"))]
        elif self.index == 4:
            actions = [
                ("star", tr("为项目点亮 Star")),
                ("issues", tr("反馈问题")),
                ("support", tr("社区 / 支持项目")),
            ]
        self.surface.show()
        self.surface.set_content(step, self.index, len(self.steps), actions, detail)
        self.refresh_busy()
        self.surface.reposition()
        self.surface.raise_()

    def refresh_busy(self):
        if sip.isdeleted(self.window) or sip.isdeleted(self.surface):
            return
        self.surface.ring.setVisible(
            self.active
            and self.index == 3
            and bool(self.window._model_warmup_in_progress)
        )
        if self.surface.isVisible():
            self.surface.reposition()

    def advance(self):
        if self.index == len(self.steps) - 1:
            self.finish()
        else:
            self.index += 1
            self.render()

    def back(self):
        self.index = max(0, self.index - 1)
        self.render()

    def finish(self):
        if self.automatic:
            self.window.cfg.set(AUTO_SHOW_KEY, False)
        self.active = False
        self.surface.hide()
        self.window.onboarding_button.setFocus()

    def action(self, key):
        if key in ("shortcut", "logs"):
            self.surface.hide()
            if key == "shortcut":
                self.window.set_shortcut()
                auxiliary = self.window.shortcut_window
            else:
                auxiliary = show_runtime_log_window(self.window)
            if auxiliary is None:
                self.render()
                return
            self.auxiliary = auxiliary
            auxiliary.installEventFilter(self)
            return
        url = PROJECT_URL
        if key == "issues":
            url += "/issues"
        elif key == "support":
            page = (
                "README.zh-CN.md#支持本项目"
                if current_ui_language() == "zh_CN"
                else "readme.md#support-the-project"
            )
            url += f"/blob/main/{page}"
        if not QDesktopServices.openUrl(QUrl(url)):
            self.surface.detail.setText(tr("无法打开链接，请检查默认浏览器设置。"))
            self.surface.detail.show()
            self.surface.reposition()

    def eventFilter(self, watched, event):
        if sip.isdeleted(self.window) or sip.isdeleted(self.surface):
            self.active = False
            return False
        if watched is self.auxiliary and event.type() in (
            QEvent.Type.Hide,
            QEvent.Type.Close,
        ):
            watched.removeEventFilter(self)
            self.auxiliary = None
            if self.active:
                QTimer.singleShot(0, self.render)
        elif watched is self.central_widget and event.type() == QEvent.Type.Resize:
            self.surface.reposition()
        elif watched is self.window and event.type() == QEvent.Type.Close:
            self.active = False
            self.surface.hide()
        return False

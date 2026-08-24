"""Window visibility policy used while starting a screen capture."""

from __future__ import annotations

import ctypes
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


class CaptureWindowManager:
    def __init__(self, owner) -> None:
        self._owner = owner

    def prepare(self, *, preserve_pinned_result: bool = False) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        changed = False
        for widget in list(app.topLevelWidgets()):
            try:
                if widget is None or widget is self._owner:
                    continue
                if preserve_pinned_result and bool(getattr(widget, "_predict_result_pinned", False)):
                    continue
                if widget.isVisible():
                    widget.hide()
                    changed = True
                if widget.isMinimized():
                    widget.setWindowState(widget.windowState() & ~Qt.WindowState.WindowMinimized)
                    changed = True
            except Exception:
                continue
        try:
            if self._owner.isVisible() and not self._owner.isMinimized():
                self._owner.showMinimized()
                changed = True
        except Exception:
            pass
        return changed

    @staticmethod
    def flush_desktop() -> None:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if os.name == "nt":
            try:
                ctypes.windll.dwmapi.DwmFlush()
            except Exception:
                pass
        if app is not None:
            app.processEvents()

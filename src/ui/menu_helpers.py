"""Shared menu helpers for main-window controllers."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidgetAction
from qfluentwidgets import PushButton, RoundMenu


class CenterMenu(RoundMenu):
    def __init__(self, title: str = "", parent=None):
        super().__init__(title=title, parent=parent)

    def add_center_button(self, text: str, slot):
        btn = PushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)

        btn.clicked.connect(slot)
        act = QWidgetAction(self)
        act.setDefaultWidget(btn)
        self.addAction(act)
        return act

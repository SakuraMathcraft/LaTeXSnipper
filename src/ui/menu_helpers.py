"""Shared menu helpers for main-window controllers."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidgetAction
from qfluentwidgets import PushButton, RoundMenu

from preview.math_preview import is_dark_ui


def action_btn_style() -> str:
    if is_dark_ui():
        return (
            "PrimaryPushButton{background:#2f6ea8;color:#f5f7fb;border:1px solid #4d8dca;"
            "border-radius:4px;padding:4px 10px;font-size:12px;}"
            "PrimaryPushButton:hover{background:#3e82c3;}"
            "PrimaryPushButton:pressed{background:#245a8d;}"
            "PrimaryPushButton:disabled{background:#2b3440;color:#7f8a98;border:1px solid #465162;}"
        )
    return (
        "PrimaryPushButton{background:#3daee9;color:#ffffff;border:1px solid #2b94cb;"
        "border-radius:4px;padding:4px 10px;font-size:12px;}"
        "PrimaryPushButton:hover{background:#5dbff2;}"
        "PrimaryPushButton:pressed{background:#319fd9;}"
        "PrimaryPushButton:disabled{background:#eef2f6;color:#8a94a3;border:1px solid #d0d7de;}"
    )


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

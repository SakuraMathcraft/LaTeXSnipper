"""Shared non-blocking notifications for application windows."""

from __future__ import annotations

from qfluentwidgets import InfoBar, InfoBarPosition


def show_user_notice(title: str, message: str, parent) -> None:
    level = "error" if title in {"错误", "权限不足", "清理未完成"} else "warning"
    notifier = InfoBar.error if level == "error" else InfoBar.warning
    notifier(
        title=title,
        content=message,
        parent=parent,
        duration=5000,
        position=InfoBarPosition.TOP,
    )

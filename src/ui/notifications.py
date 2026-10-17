"""Shared non-blocking notifications for application windows."""

from __future__ import annotations

from qfluentwidgets import InfoBar, InfoBarPosition

from localization.manager import translate as tr


def show_user_notice(title: str, message: str, parent) -> None:
    error_titles = {tr("错误"), tr("权限不足"), tr("清理未完成")}
    level = "error" if title in error_titles else "warning"
    notifier = InfoBar.error if level == "error" else InfoBar.warning
    notifier(
        title=title,
        content=message,
        parent=parent,
        duration=5000,
        position=InfoBarPosition.TOP,
    )

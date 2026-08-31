"""Global hotkey controller mixin for the main window."""

from __future__ import annotations

import sys

from localization.manager import translate as tr
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog
from qfluentwidgets import InfoBar, InfoBarPosition

from runtime.hotkey_config import (
    display_hotkey,
    normalize_hotkey,
    normalize_hotkey_or_default,
)
from ui.hotkey_dialog import create_hotkey_dialog, localized_hotkey_help_text
from ui.window_helpers import show_normal_window


class HotkeyControllerMixin:
    def register_hotkey(self, seq: str):
        if not getattr(self, "hotkey_provider", None):
            return
        try:
            self.hotkey_provider.register(seq)
        except Exception as e:
            print(f"[WARN] 全局快捷键注册失败: {e}")

    def _blocking_window(self):
        app = QApplication.instance()
        if app is None:
            return None
        try:
            modal = app.activeModalWidget()
            if modal is not None and modal is not self and modal.isVisible():
                return modal
        except Exception:
            pass
        try:
            popup = app.activePopupWidget()
            if popup is not None and popup.isVisible():
                active = app.activeWindow()
                return active if active is not None and active.isVisible() else popup
        except Exception:
            pass
        try:
            for widget in app.topLevelWidgets():
                if widget is None or widget is self or (not widget.isVisible()):
                    continue
                try:
                    if (
                        bool(widget.isModal())
                        or widget.windowModality() != Qt.WindowModality.NonModal
                    ):
                        return widget
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def on_hotkey_triggered(self):
        blocking_window = self._blocking_window()
        if blocking_window is not None:
            try:
                InfoBar.info(
                    title=tr("提示"),
                    content=tr("请先关闭当前对话框，再执行截图识别"),
                    parent=blocking_window,
                    duration=2200,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
            return
        self.start_capture(preserve_pinned_result=True)

    def set_shortcut(self):
        if self.shortcut_window:
            show_normal_window(self.shortcut_window)
            return

        current_hotkey = display_hotkey(
            normalize_hotkey_or_default(self.cfg.get("hotkey", None), sys.platform),
            sys.platform,
        )
        dlg = create_hotkey_dialog(
            self,
            current_hotkey,
            self.update_hotkey,
            on_destroyed=lambda: setattr(self, "shortcut_window", None),
        )
        self.shortcut_window = dlg
        show_normal_window(dlg)

    def update_hotkey(self, text: str, dialog: QDialog):
        normalized_hotkey = normalize_hotkey(text, sys.platform)
        if normalized_hotkey is None:
            InfoBar.error(
                title=tr("快捷键格式错误"),
                content=tr("格式必须为 {format}").format(
                    format=localized_hotkey_help_text(sys.platform)
                ),
                parent=dialog,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        self.register_hotkey(normalized_hotkey)
        if getattr(self, "hotkey_provider", None) and (
            not self.hotkey_provider.is_registered()
        ):
            InfoBar.error(
                title=tr("快捷键注册失败"),
                content=tr("请更换其他 {format} 组合后重试").format(
                    format=localized_hotkey_help_text(sys.platform)
                ),
                parent=dialog,
                duration=3500,
                position=InfoBarPosition.TOP,
            )
            return
        self.cfg.set("hotkey", normalized_hotkey)
        try:
            dialog.close()
        except Exception:
            pass
        InfoBar.success(
            title=tr("快捷键已更新"),
            content=tr("已更新为 {hotkey}").format(
                hotkey=display_hotkey(normalized_hotkey, sys.platform)
            ),
            parent=self._get_infobar_parent(),
            duration=2500,
            position=InfoBarPosition.TOP,
        )
        self.update_tray_tooltip()
        self.update_tray_menu()

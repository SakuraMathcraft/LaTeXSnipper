"""Global hotkey controller mixin for the main window."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog
from qfluentwidgets import InfoBar, InfoBarPosition

from runtime.hotkey_config import HOTKEY_HELP_TEXT, normalize_hotkey, normalize_hotkey_or_default
from ui.hotkey_dialog import create_hotkey_dialog


class HotkeyControllerMixin:
    def register_hotkey(self, seq: str):
        if not getattr(self, "hotkey_provider", None):
            return
        print(f"[Hotkey] try register {seq}")
        try:
            self.hotkey_provider.register(seq)
            print(f"[Hotkey] global registered={self.hotkey_provider.is_registered()}")
        except Exception as e:
            print(f"[Hotkey] global failed: {e}")

    def _has_blocking_window(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            modal = app.activeModalWidget()
            if modal is not None and modal is not self and modal.isVisible():
                return True
        except Exception:
            pass
        try:
            popup = app.activePopupWidget()
            if popup is not None and popup.isVisible():
                return True
        except Exception:
            pass
        try:
            for widget in app.topLevelWidgets():
                if widget is None or widget is self or (not widget.isVisible()):
                    continue
                try:
                    if bool(widget.isModal()) or widget.windowModality() != Qt.WindowModality.NonModal:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def on_hotkey_triggered(self):
        print("[Hotkey] Triggered")
        if self._has_blocking_window():
            try:
                InfoBar.info(
                    title="提示",
                    content="请先关闭当前对话框，再执行截图识别",
                    parent=self._get_infobar_parent(),
                    duration=2200,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
            return
        self.start_capture()

    def set_shortcut(self):
        if self.shortcut_window and self.shortcut_window.isVisible():
            self.shortcut_window.raise_()
            self.shortcut_window.activateWindow()
            return

        current_hotkey = normalize_hotkey_or_default(self.cfg.get("hotkey", "Ctrl+F"))
        dlg = create_hotkey_dialog(
            self,
            current_hotkey,
            self.update_hotkey,
            on_destroyed=lambda: setattr(self, "shortcut_window", None),
        )
        self.shortcut_window = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def update_hotkey(self, text: str, dialog: QDialog):
        from qfluentwidgets import InfoBar, InfoBarPosition

        normalized_hotkey = normalize_hotkey(text)
        if normalized_hotkey is None:
            InfoBar.error(
                title="快捷键格式错误",
                content=f"格式必须为 {HOTKEY_HELP_TEXT}",
                parent=self._get_infobar_parent(),
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        self.register_hotkey(normalized_hotkey)
        if (
            getattr(self, "hotkey_provider", None)
            and (not self.hotkey_provider.is_registered())
        ):
            InfoBar.error(
                title="快捷键注册失败",
                content=f"请更换其他 {HOTKEY_HELP_TEXT} 组合后重试",
                parent=self._get_infobar_parent(),
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
            title="快捷键已更新",
            content=f"已更新为 {normalized_hotkey}",
            parent=self._get_infobar_parent(),
            duration=2500,
            position=InfoBarPosition.TOP,
        )
        self.update_tray_tooltip()
        self.update_tray_menu()

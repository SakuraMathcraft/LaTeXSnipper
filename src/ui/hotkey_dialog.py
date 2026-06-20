"""Hotkey settings dialog."""

from __future__ import annotations

from collections.abc import Callable
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout
from qfluentwidgets import FluentIcon, PushButton

from preview.math_preview import dialog_theme_tokens, is_dark_ui
from runtime.hotkey_config import hotkey_help_text, hotkey_modifier_label
from ui.window_helpers import apply_close_only_window_flags


def create_hotkey_dialog(
    parent,
    current_hotkey: str,
    on_confirm: Callable[[str, QDialog], None],
    on_destroyed: Callable[[], None] | None = None,
) -> QDialog:
    dlg = QDialog(parent)
    apply_close_only_window_flags(dlg)
    dlg.setWindowTitle("设置快捷键")
    dlg.setFixedSize(300, 148)
    dlg.setModal(False)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    if on_destroyed is not None:
        dlg.destroyed.connect(lambda: on_destroyed())

    t = dialog_theme_tokens()
    is_macos = sys.platform == "darwin"
    modifier_label = hotkey_modifier_label()
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(6)

    current_label = QLabel(f"当前快捷键：{current_hotkey}")
    current_label.setStyleSheet(f"color: {t['text']}; font-weight: 600;")
    hint_label = QLabel(f"按下新的：{hotkey_help_text()}")
    hint_label.setStyleSheet(f"color: {t['muted']};")
    lay.addWidget(current_label)
    lay.addWidget(hint_label)

    edit = QLineEdit(dlg)
    edit.setReadOnly(True)
    edit.setFixedHeight(34)
    edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    edit.setStyleSheet(
        f"""
QLineEdit {{
    background: {t['panel_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {"#3b4756" if is_dark_ui() else "#d7e3f1"};
    selection-color: {t['text']};
}}
QLineEdit:focus {{
    border: 1px solid {"#66788a" if is_dark_ui() else "#9aa9bb"};
}}
"""
    )

    def keyPressEvent(ev):
        if ev.key() == Qt.Key.Key_Escape:
            dlg.reject()
            return
        k = ev.key()
        mods = ev.modifiers()
        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        has_meta = bool(mods & Qt.KeyboardModifier.MetaModifier)
        has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        has_extra = bool(
            mods
            & (
                Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.GroupSwitchModifier
            )
        )
        has_primary = has_meta if is_macos else has_ctrl
        has_forbidden_primary = has_ctrl if is_macos else has_meta
        if has_primary and not has_forbidden_primary and not has_extra and Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
            edit.setText(f"{modifier_label}+Shift+{chr(k)}" if has_shift else f"{modifier_label}+{chr(k)}")
            edit.setFocus()
            edit.selectAll()
        else:
            edit.setText("")
            edit.setFocus()

    edit.keyPressEvent = keyPressEvent
    lay.addWidget(edit)
    lay.addSpacing(8)

    btn = PushButton(FluentIcon.ACCEPT, "确定")
    btn.setFixedHeight(32)
    btn.clicked.connect(lambda: on_confirm(edit.text().strip(), dlg))
    lay.addWidget(btn)

    QTimer.singleShot(0, edit.setFocus)
    return dlg

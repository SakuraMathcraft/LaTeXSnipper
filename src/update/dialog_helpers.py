import os
import subprocess
import sys
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox


def _resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = _resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _is_dark_ui() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    c = app.palette().window().color()
    return ((c.red() + c.green() + c.blue()) / 3.0) < 128


def _update_dialog_theme() -> dict:
    if _is_dark_ui():
        return {
            "dialog_bg": "#1b1f27",
            "text": "#e7ebf0",
            "muted": "#a9b3bf",
            "panel_bg": "#232934",
            "border": "#465162",
            "code_bg": "#161a20",
            "accent": "#4c9aff",
            "warn_bg": "#3e2e18",
            "warn_border": "#b8843b",
            "warn_text": "#ffd08a",
        }
    return {
        "dialog_bg": "#f5f7fa",
        "text": "#2e3135",
        "muted": "#555555",
        "panel_bg": "#ffffff",
        "border": "#cfd6dd",
        "code_bg": "#f6f8fa",
        "accent": "#1976d2",
        "warn_bg": "#fff4e0",
        "warn_border": "#f5c182",
        "warn_text": "#d35400",
    }


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    }
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs



_UPDATE_DIALOG: Optional[QDialog] = None


def _set_update_dialog(dlg: QDialog | None) -> None:
    global _UPDATE_DIALOG
    _UPDATE_DIALOG = dlg


def _show_existing_update_dialog():
    if _UPDATE_DIALOG is None:
        return None
    try:
        if _UPDATE_DIALOG.isVisible():
            _UPDATE_DIALOG.show()
            _UPDATE_DIALOG.raise_()
            _UPDATE_DIALOG.activateWindow()
            return _UPDATE_DIALOG
    except RuntimeError:
        pass
    _clear_global()
    return None


def _clear_global():
    global _UPDATE_DIALOG
    _UPDATE_DIALOG = None


def question_close_only(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    default: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
) -> QMessageBox.StandardButton:
    msg = QMessageBox(parent)
    _apply_app_window_icon(msg)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setStandardButtons(buttons)
    msg.setDefaultButton(default)
    msg.setWindowFlags(
        (
            msg.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
    )
    msg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
    msg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
    msg.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)
    return QMessageBox.StandardButton(msg.exec())

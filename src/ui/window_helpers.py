"""Shared window and dialog helpers."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QFileDialog, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from runtime.app_paths import resource_path


def apply_app_window_icon(win) -> None:
    from core.window_icons import apply_app_window_icon as _apply_app_window_icon

    _apply_app_window_icon(win, resource_path("assets/icon.ico"))


def select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    # Use QFileDialog.getExistingDirectory() static method (safer than manual .exec())
    # but keep the native-dialog icon hack via schedule_native_dialog_icon.
    from core.window_icons import schedule_native_dialog_icon

    icon_timer = schedule_native_dialog_icon(title, resource_path("assets/icon.ico"))
    try:
        return QFileDialog.getExistingDirectory(parent, title, initial_dir)
    finally:
        if icon_timer is not None:
            icon_timer.stop()


def select_save_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    # Use QFileDialog.getSaveFileName() static method — safer than manual .exec()
    return QFileDialog.getSaveFileName(parent, title, initial_path, filter_)


def select_open_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    # Use QFileDialog.getOpenFileName() static method — safer than manual .exec()
    return QFileDialog.getOpenFileName(parent, title, initial_path, filter_)


def apply_close_only_window_flags(win):
    """Keep only the top-right close button for prompt/tool windows."""
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    win.setWindowFlags(flags)


def apply_no_minimize_window_flags(win):
    """Keep maximize and close buttons for tool windows, and remove minimize."""
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMaximizeButtonHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    flags |= Qt.WindowType.WindowMaximizeButtonHint
    win.setWindowFlags(flags)


def show_formula_rename_dialog(
    parent,
    current_name: str = "",
    title: str = "重命名公式",
    prompt: str = "输入公式名称（留空则清除名称）：",
):
    """Shared formula rename dialog with only the top-right close button and fixed size."""
    from PyQt6.QtWidgets import QLineEdit

    dlg = QDialog(parent)
    apply_close_only_window_flags(dlg)
    dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(prompt))

    edit = QLineEdit(dlg)
    edit.setText(current_name or "")
    edit.selectAll()
    edit.setClearButtonEnabled(True)
    lay.addWidget(edit)

    btn_row = QHBoxLayout()
    btn_ok = QPushButton("OK", dlg)
    btn_cancel = QPushButton("Cancel", dlg)
    btn_ok.clicked.connect(dlg.accept)
    btn_cancel.clicked.connect(dlg.reject)
    edit.returnPressed.connect(dlg.accept)
    btn_row.addWidget(btn_ok)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)

    dlg.adjustSize()
    dlg.setFixedSize(max(340, dlg.width()), dlg.height())
    apply_app_window_icon(dlg)
    QTimer.singleShot(0, edit.setFocus)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return "", False
    return edit.text().strip(), True


def exec_close_only_message_box(
    parent,
    title: str,
    text: str,
    icon=QMessageBox.Icon.Information,
    buttons=QMessageBox.StandardButton.Ok,
    default_button=None,
    informative_text: str | None = None,
):
    """Show a modal message box using PyQt6 static methods (safer than manual .exec())."""
    full_text = f"{text}\n\n{informative_text}" if informative_text else text
    if default_button is None:
        default_button = buttons

    if icon == QMessageBox.Icon.Question:
        return QMessageBox.question(parent, title, full_text, buttons, default_button)
    elif icon == QMessageBox.Icon.Warning:
        return QMessageBox.warning(parent, title, full_text, buttons, default_button)
    elif icon == QMessageBox.Icon.Critical:
        return QMessageBox.critical(parent, title, full_text, buttons, default_button)
    else:
        return QMessageBox.information(parent, title, full_text, buttons, default_button)

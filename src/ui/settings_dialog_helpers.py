import os

from runtime.app_paths import resource_path


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _select_open_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_path, filter_)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return "", ""
    selected = dlg.selectedFiles()
    chosen_filter = dlg.selectedNameFilter()
    return (selected[0] if selected else ""), chosen_filter

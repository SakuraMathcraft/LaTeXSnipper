from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PushButton

from runtime.distribution import store_update_uri
from update.dialog_helpers import _apply_app_window_icon, _clear_global, _set_update_dialog, _show_existing_update_dialog
from update.release_types import __version__, _brief_error_message


def _open_store_update_page(parent) -> None:
    try:
        import webbrowser

        webbrowser.open(store_update_uri())
    except Exception as e:
        InfoBar.error(
            title="无法打开 Microsoft Store",
            content=_brief_error_message(e),
            parent=parent,
            duration=3500,
            position=InfoBarPosition.TOP,
        )


def _store_update_dialog(parent=None):
    existing = _show_existing_update_dialog()
    if existing is not None:
        return existing

    dlg = QDialog(parent)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowTitle("检查更新")
    dlg.setWindowFlags(
        (
            dlg.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
    )
    dlg.resize(520, 220)
    dlg.setModal(False)
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    _apply_app_window_icon(dlg)
    _set_update_dialog(dlg)
    dlg.destroyed.connect(_clear_global)

    lay = QVBoxLayout(dlg)
    title = QLabel("版本更新")
    title_font = QFont(title.font())
    title_font.setPointSize(max(title_font.pointSize(), 14))
    title_font.setBold(True)
    title.setFont(title_font)
    lay.addWidget(title)

    lay.addWidget(QLabel(f"当前版本: {__version__}"))
    lay.addWidget(QLabel("当前渠道: Microsoft Store"))
    status = QLabel("此版本由 Microsoft Store 管理更新，不会下载 GitHub Release 安装包。")
    status.setWordWrap(True)
    lay.addWidget(status)

    desc = QLabel("如需更新，请打开 Microsoft Store 的库/下载页面，或等待 Store 自动更新。")
    desc.setWordWrap(True)
    lay.addWidget(desc)
    lay.addStretch()

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_store = PushButton(FluentIcon.LINK, "打开 Microsoft Store")
    btn_close = PushButton(FluentIcon.CLOSE, "关闭")
    for button in (btn_store, btn_close):
        button.setFixedHeight(32)
        btn_row.addWidget(button)
    lay.addLayout(btn_row)

    btn_store.clicked.connect(lambda: _open_store_update_page(dlg))
    btn_close.clicked.connect(dlg.close)

    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg

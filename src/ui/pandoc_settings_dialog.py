"""Pandoc export settings dialog."""

from __future__ import annotations

import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from runtime.pandoc_runtime import (
    DEFAULT_EXPORT_OPTIONS,
    load_pandoc_export_options,
    save_pandoc_export_options,
)
from ui.window_helpers import apply_app_window_icon

_PANDOC_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>"""


def _find_available_engines() -> list[str]:
    engines = []
    for name in ("xelatex", "lualatex", "pdflatex"):
        if shutil.which(name):
            engines.append(name)
    return engines


def show_pandoc_settings_dialog(parent=None) -> bool:
    """Show pandoc export settings dialog. Returns True if saved."""
    opts = load_pandoc_export_options()
    engines = _find_available_engines()

    dlg = QDialog(parent)
    dlg.setWindowTitle("Pandoc 导出设置")
    dlg.setWindowFlags(
        (dlg.windowFlags()
         | Qt.WindowType.CustomizeWindowHint
         | Qt.WindowType.WindowTitleHint
         | Qt.WindowType.WindowCloseButtonHint
         | Qt.WindowType.WindowSystemMenuHint)
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    apply_app_window_icon(dlg)
    try:
        from PyQt6.QtGui import QPixmap
        from PyQt6.QtCore import QByteArray
        pixmap = QPixmap()
        pixmap.loadFromData(QByteArray(_PANDOC_SVG.encode()), "SVG")
        dlg.setWindowIcon(QIcon(pixmap))
    except Exception:
        pass

    layout = QVBoxLayout(dlg)

    # PDF engine
    layout.addWidget(QLabel("PDF 引擎："))
    engine_combo = QComboBox()
    engine_combo.addItem("自动检测（优先 xelatex）", "")
    for eng in engines:
        engine_combo.addItem(eng, eng)
    current_engine = opts.get("pdf_engine", "")
    idx = engine_combo.findData(current_engine)
    if idx >= 0:
        engine_combo.setCurrentIndex(idx)
    layout.addWidget(engine_combo)

    # MathJax URL
    layout.addWidget(QLabel("MathJax URL（HTML/GFM 导出用，留空使用默认）："))
    mathjax_input = QLineEdit()
    mathjax_input.setText(opts.get("mathjax_url", ""))
    mathjax_input.setPlaceholderText("https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js")
    layout.addWidget(mathjax_input)

    # HTML standalone
    layout.addWidget(QLabel("HTML 导出："))
    html_combo = QComboBox()
    html_combo.addItem("完整 HTML 页面（含 MathJax）", "true")
    html_combo.addItem("HTML 片段", "false")
    html_val = str(opts.get("html_standalone", True)).lower()
    idx = html_combo.findData(html_val)
    if idx >= 0:
        html_combo.setCurrentIndex(idx)
    layout.addWidget(html_combo)

    # Info
    info = QLabel(
        "提示：\n"
        "• PDF 引擎推荐使用 xelatex（支持 Unicode 和中文）\n"
        "• MathJax URL 留空将使用 CDN 默认地址\n"
        "• 完整 HTML 页面可在浏览器中直接查看公式渲染效果"
    )
    info.setWordWrap(True)
    info.setStyleSheet("color: #666; font-size: 11px; margin-top: 8px;")
    layout.addWidget(info)

    # Buttons
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        dlg,
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    dlg.setFixedSize(480, 320)
    if dlg.exec() != int(QDialog.DialogCode.Accepted):
        return False

    new_opts = {
        "pdf_engine": engine_combo.currentData() or "",
        "mathjax_url": mathjax_input.text().strip(),
        "html_standalone": html_combo.currentData() == "true",
    }
    save_pandoc_export_options(new_opts)
    return True

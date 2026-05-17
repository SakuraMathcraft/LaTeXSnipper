"""PDF recognition option dialogs."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QInputDialog, QLabel, QSlider, QVBoxLayout

from preview.math_preview import dialog_theme_tokens
from ui.window_helpers import apply_app_window_icon


def _pick_item(parent, title: str, label: str, items: list[str], current: int = 0):
    # Use QInputDialog.getItem() static method -- safer than manual .exec()
    text, ok = QInputDialog.getItem(parent, title, label, items, current, False)
    if not ok:
        return None
    return text


def prompt_pdf_output_options(parent, current_model: str, external_config=None):
    """Prompt for PDF recognition output format and DPI."""
    doc_mode = "document"
    external_provider = external_config.normalized_provider() if external_config is not None else ""

    if current_model == "external_model" and external_provider == "mineru":
        doc_mode = "parse"

    if doc_mode == "parse":
        fmt_key = "markdown"
    else:
        fmt_items = ["Markdown", "LaTeX"]
        fmt = _pick_item(parent, "导出格式", "请选择导出格式：", fmt_items, 0)
        if not fmt:
            return None
        fmt_key = "markdown" if fmt.lower().startswith("markdown") else "latex"

    dlg = QDialog(parent)
    dlg.setWindowTitle("PDF 渲染分辨率")
    dlg.setWindowFlags(
        (
            dlg.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
    apply_app_window_icon(dlg)

    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("请选择 PDF 渲染分辨率（DPI）："))

    dpi_label = QLabel()
    dpi_label.setWordWrap(True)
    layout.addWidget(dpi_label)

    slider = QSlider(Qt.Orientation.Horizontal, dlg)
    slider.setRange(90, 300)
    slider.setSingleStep(10)
    slider.setPageStep(10)
    slider.setTickInterval(10)
    slider.setTickPosition(QSlider.TickPosition.TicksBelow)
    default_dpi = 150 if current_model == "external_model" else 200
    slider.setValue(default_dpi)
    layout.addWidget(slider)

    tip = QLabel("建议根据文档清晰度动态调整：清晰文档可用较低 DPI，普通文档建议 140-170 DPI，模糊文档可适当提高；过高 DPI 可能降低识别稳定性。")
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {dialog_theme_tokens()['muted']}; font-size: 11px;")
    layout.addWidget(tip)

    def _refresh_dpi_label(value: int):
        if value < 120:
            zone = "清晰文档"
        elif 140 <= value <= 170:
            zone = "推荐"
        elif value > 220:
            zone = "高 DPI：模糊文档"
        else:
            zone = "可选"
        dpi_label.setText(f"当前 DPI：{value}（{zone}）")

    slider.valueChanged.connect(_refresh_dpi_label)
    _refresh_dpi_label(default_dpi)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    dlg.setFixedSize(420, 180)
    if dlg.exec() != int(QDialog.DialogCode.Accepted):
        return None
    dpi = int(slider.value())
    return fmt_key, dpi, doc_mode

"""PDF recognition option dialogs."""

from __future__ import annotations

from localization.manager import translate as tr

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from preview.math_preview import dialog_theme_tokens
from ui.window_helpers import apply_app_window_icon


def _pick_item(parent, title: str, label: str, items: list[str], current: int = 0):
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setComboBoxItems(items)
    dlg.setComboBoxEditable(False)
    if 0 <= current < len(items):
        dlg.setTextValue(items[current])
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
    dlg.setFixedSize(dlg.sizeHint())
    apply_app_window_icon(dlg)
    if dlg.exec() != int(QDialog.DialogCode.Accepted):
        return None
    return dlg.textValue()


def prompt_pdf_output_options(
    parent,
    current_model: str,
    external_config=None,
) -> tuple[str, int | None, str] | None:
    """Prompt for PDF recognition output format and DPI."""
    doc_mode = "document"
    external_provider = (
        external_config.normalized_provider() if external_config is not None else ""
    )

    if current_model == "external_model" and external_provider == "mineru":
        doc_mode = "parse"

    if doc_mode == "parse":
        return "markdown", None, doc_mode

    fmt_items = ["Markdown", "LaTeX"]
    fmt = _pick_item(parent, tr("导出格式"), tr("请选择导出格式："), fmt_items, 0)
    if not fmt:
        return None
    fmt_key = "markdown" if fmt.lower().startswith("markdown") else "latex"

    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("PDF 渲染分辨率"))
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
    layout.addWidget(QLabel(tr("请选择 PDF 渲染分辨率：")))

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

    tip = QLabel(
        tr(
            "清晰文字型 PDF 建议 140-170 DPI，扫描件可尝试 200-300 DPI。"
            "提高 DPI 仅在原页面细节不足时有帮助；过高会增加内存和处理时间，"
            "使用外部模型时还可能触发缩放、输入限制或超时。"
        )
    )
    tip.setWordWrap(True)
    tip.setStyleSheet(f"color: {dialog_theme_tokens()['muted']}; font-size: 11px;")
    layout.addWidget(tip)

    def _refresh_dpi_label(value: int):
        if value < 120:
            zone = tr("清晰文档")
        elif 140 <= value <= 170:
            zone = tr("推荐")
        elif value > 220:
            zone = tr("高 DPI：扫描件")
        else:
            zone = tr("可选")
        dpi_label.setText(
            tr("当前 DPI：{value}（{zone}）").format(value=value, zone=zone)
        )

    slider.valueChanged.connect(_refresh_dpi_label)
    _refresh_dpi_label(default_dpi)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    dlg.setFixedSize(460, 210)
    if dlg.exec() != int(QDialog.DialogCode.Accepted):
        return None
    dpi = int(slider.value())
    return fmt_key, dpi, doc_mode

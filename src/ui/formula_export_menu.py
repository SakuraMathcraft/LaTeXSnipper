"""Shared formula export menu and clipboard helpers."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Action

from exporting.formula_export import build_formula_export, get_all_export_format_specs


StatusCallback = Callable[[str], None]


def populate_formula_export_menu(menu, export_callback: Callable[[str], None]) -> None:
    for spec in get_all_export_format_specs():
        if spec.separator_before:
            menu.addSeparator()
            continue
        if spec.key == "_pandoc_header":
            # Pandoc section header (non-clickable)
            header_action = Action(spec.label or spec.key)
            header_action.setEnabled(False)
            menu.addAction(header_action)
            continue
        menu.addAction(Action(spec.label or spec.key, triggered=lambda _checked=False, key=spec.key: export_callback(key)))


def export_formula_to_clipboard(
    format_type: str,
    latex: str,
    *,
    mathml_converter: Callable[[str], str],
    omml_converter: Callable[[str], str],
    svg_converter: Callable[[str], str],
) -> tuple[bool, str]:
    result, format_name = build_formula_export(
        format_type,
        latex,
        mathml_converter=mathml_converter,
        omml_converter=omml_converter,
        svg_converter=svg_converter,
    )
    if not result:
        return False, "复制失败"

    # Handle Pandoc binary formats (docx, odt, epub) – need file save dialog
    if result.startswith("[BINARY:"):
        return _handle_pandoc_binary_export(format_type, latex, format_name)

    # Handle Pandoc error messages
    if result.startswith("[Pandoc ") and ("不可用" in result or "失败" in result):
        return False, result

    try:
        QApplication.clipboard().setText(result)
        return True, f"已复制 {format_name} 格式"
    except Exception:
        try:
            import pyperclip

            pyperclip.copy(result)
            return True, f"已复制 {format_name} 格式"
        except Exception:
            return False, "复制失败"


def _handle_pandoc_binary_export(
    format_key: str, latex: str, format_name: str
) -> tuple[bool, str]:
    """Handle Pandoc binary format export by prompting for file save."""
    from PyQt6.QtWidgets import QFileDialog
    from exporting.pandoc_exporter import PANDOC_FORMAT_MAP, convert_latex_to

    fmt = PANDOC_FORMAT_MAP.get(format_key)
    if fmt is None:
        return False, f"未知的 Pandoc 格式: {format_key}"

    # Prompt for save location
    file_path, _ = QFileDialog.getSaveFileName(
        None,
        f"导出为 {format_name}",
        f"formula{fmt.extension}",
        f"{fmt.label} (*{fmt.extension})",
    )
    if not file_path:
        return False, "已取消导出"

    try:
        data = convert_latex_to(format_key, latex, as_document=True)
        if isinstance(data, bytes):
            from pathlib import Path
            Path(file_path).write_bytes(data)
            return True, f"已导出 {format_name} 到 {file_path}"
        else:
            from pathlib import Path
            Path(file_path).write_text(str(data), encoding="utf-8")
            return True, f"已导出 {format_name} 到 {file_path}"
    except Exception as exc:
        return False, f"导出失败: {exc}"


def show_formula_export_menu(
    *,
    parent,
    menu_cls,
    anchor_widget,
    text_source,
    status_callback: StatusCallback,
    export_callback: Callable[[str, str], None],
    empty_hint: str = "内容为空",
) -> None:
    def _current_text() -> str:
        try:
            if callable(text_source):
                return (text_source() or "").strip()
        except Exception:
            return ""
        return (str(text_source) if text_source is not None else "").strip()

    text = _current_text()
    if not text:
        status_callback(empty_hint)
        return

    def _export_current(format_type: str) -> None:
        current = _current_text()
        if not current:
            status_callback(empty_hint)
            return
        export_callback(format_type, current)

    menu = menu_cls(parent=parent)
    populate_formula_export_menu(menu, _export_current)
    pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft()) if anchor_widget else parent.mapToGlobal(parent.rect().center())
    menu.exec(pos)

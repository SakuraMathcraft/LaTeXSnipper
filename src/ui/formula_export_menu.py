"""Shared formula export menu and clipboard helpers."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Action

from exporting.formula_export import EXPORT_FORMAT_SPECS, build_formula_export


StatusCallback = Callable[[str], None]


def populate_formula_export_menu(menu, export_callback: Callable[[str], None]) -> None:
    for spec in EXPORT_FORMAT_SPECS:
        if spec.separator_before:
            menu.addSeparator()
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

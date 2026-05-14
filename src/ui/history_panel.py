"""History panel UI helpers."""

from __future__ import annotations

import weakref
from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PushButton


def history_display_entries(history: list[str], reverse: bool) -> list[tuple[int, int, str]]:
    entries = list(enumerate(history))
    if reverse:
        entries.reverse()
    return [
        (display_index + 1, history_index, text)
        for display_index, (history_index, text) in enumerate(entries)
    ]


def refresh_history_order_button(button, reverse: bool) -> None:
    if button is None:
        return
    if reverse:
        button.setText("最新在前")
        button.setToolTip("当前按最新记录在前显示，点击切换为最早在前")
    else:
        button.setText("最早在前")
        button.setToolTip("当前按最早记录在前显示，点击切换为最新在前")


def clear_history_rows(history_layout) -> None:
    for i in reversed(range(history_layout.count() - 1)):
        item = history_layout.itemAt(i)
        w = item.widget() if item else None
        if w:
            history_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()


def create_history_row(
    *,
    parent,
    history_container,
    text: str,
    index: int = 0,
    history_index: int | None = None,
    formula_names: dict[str, str],
    apply_row_theme: Callable[[QWidget], None],
    row_is_alive: Callable[[QWidget | None], bool],
    on_load_to_editor: Callable[[QWidget], None],
    on_copy: Callable[[QWidget], None],
    on_context_menu: Callable[[QWidget, object], None],
) -> QWidget:
    row = QWidget(history_container)
    row._latex_text = text
    row._index = index
    row._history_index = history_index
    row._deleted = False
    row._index_label = None
    hl = QHBoxLayout(row)
    hl.setContentsMargins(6, 4, 6, 4)
    hl.setSpacing(6)

    if index > 0:
        num_lbl = QLabel(f"#{index}")
        num_lbl.setFixedWidth(35)
        num_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        row._index_label = num_lbl
        hl.addWidget(num_lbl)

    text_col = QVBoxLayout()
    text_col.setContentsMargins(0, 0, 0, 0)
    text_col.setSpacing(2)

    formula_name = formula_names.get(text, "")
    if formula_name:
        name_lbl = QLabel(f"[{formula_name}]")
        name_lbl.setWordWrap(True)
        name_lbl.setMinimumWidth(0)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_col.addWidget(name_lbl)
        row._name_label = name_lbl
    else:
        row._name_label = None

    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setMinimumWidth(0)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    lbl.setCursor(Qt.CursorShape.PointingHandCursor)
    label_font = QFont("Consolas", 9)
    label_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    lbl.setFont(label_font)
    text_col.addWidget(lbl)
    hl.addLayout(text_col, 1)
    row._content_label = lbl
    apply_row_theme(row)

    row_ref = weakref.ref(row)

    def _load_to_editor(event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        r = row_ref()
        if not row_is_alive(r):
            return
        on_load_to_editor(r)

    lbl.mousePressEvent = _load_to_editor

    def add_btn(text_value, tip, handler, icon):
        b = PushButton(icon, text_value)
        b.setToolTip(tip)
        b.setFixedSize(85, 30)
        b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_ref2 = weakref.ref(row)

        def _wrapped():
            r = row_ref2()
            if not row_is_alive(r):
                return
            handler(r)

        b.clicked.connect(_wrapped)
        hl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        return b

    add_btn("复制", "复制到剪贴板", on_copy, FluentIcon.COPY)
    row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _ctx(pos):
        on_context_menu(row, row.mapToGlobal(pos))

    row.customContextMenuRequested.connect(_ctx)
    return row

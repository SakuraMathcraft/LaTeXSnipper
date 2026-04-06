from __future__ import annotations

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import ComboBox, FluentIcon, PushButton


LATEX_SNIPPETS = {
    "分式  (/)": ("fraction", r"\frac{#?}{#?}"),
    "上标  (Shift+^)": ("superscript", r"x^{#?}"),
    "下标  (Shift+_)": ("subscript", r"x_{#?}"),
    "上下标  (Shift+_ + Shift+^)": ("subsuperscript", r"x_{#?}^{#?}"),
    "根号  (sqrt)": ("sqrt", r"\sqrt{#?}"),
    "求和  (sum)": ("sum", r"\sum_{n=1}^{\infty} #?"),
    "连乘  (prod)": ("product", r"\prod_{n=1}^{\infty} #?"),
    "积分  (int)": ("integral", r"\int_{a}^{b} #?\,dx"),
    "矩阵  (matrix)": ("matrix2", r"\begin{bmatrix}#? & #? \\ #? & #?\end{bmatrix}"),
    "换行  (Shift+Enter)": ("newline", r" \\ "),
}

COMPACT_LATEX_SNIPPETS = {
    "分式": ("fraction", r"\frac{#?}{#?}"),
    "上标": ("superscript", r"x^{#?}"),
    "下标": ("subscript", r"x_{#?}"),
    "上下标": ("subsuperscript", r"x_{#?}^{#?}"),
    "根号": ("sqrt", r"\sqrt{#?}"),
    "求和": ("sum", r"\sum_{n=1}^{\infty} #?"),
    "连乘": ("product", r"\prod_{n=1}^{\infty} #?"),
    "积分": ("integral", r"\int_{a}^{b} #?\,dx"),
    "矩阵": ("matrix2", r"\begin{bmatrix}#? & #? \\ #? & #?\end{bmatrix}"),
    "换行": ("newline", r" \\ "),
}

SNIPPET_TEMPLATES = {key: template for key, template in (value for value in LATEX_SNIPPETS.values())}


def insert_snippet_into_editor(editor, key: str) -> bool:
    template = SNIPPET_TEMPLATES.get(str(key or "").strip())
    if not template or editor is None:
        return False

    cursor = editor.textCursor()
    selected = cursor.selectedText().replace("\u2029", "\n")
    placeholder_count = template.count("#?")

    if placeholder_count == 0:
        cursor.insertText(template)
        editor.setTextCursor(cursor)
        editor.setFocus()
        return True

    if placeholder_count == 1:
        insert_text = template.replace("#?", selected or "")
        cursor.insertText(insert_text)
        editor.setTextCursor(cursor)
        editor.setFocus()
        return True

    first_index = template.find("#?")
    last_index = template.rfind("#?")
    if selected and first_index >= 0:
        template = template[:first_index] + selected + template[first_index + 2:]
        if last_index > first_index:
            last_index -= 2 - len(selected)
    cursor.insertText(template.replace("#?", ""))
    if last_index >= 0:
        start = cursor.position() - (len(template) - last_index)
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor, 0)
    editor.setTextCursor(cursor)
    editor.setFocus()
    return True


class LaTeXSnippetPanel(QWidget):
    def __init__(self, parent=None, *, insert_button_text: str = "插入", on_insert_key=None, compact: bool = False):
        super().__init__(parent)
        self._on_insert_key = on_insert_key
        self._snippet_items = COMPACT_LATEX_SNIPPETS if compact else LATEX_SNIPPETS

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.combo = ComboBox(self)
        self.button = PushButton(FluentIcon.CODE, insert_button_text, self)
        self.combo.setFixedHeight(32)
        self.combo.setMinimumWidth(112)
        self.button.setFixedHeight(30)
        self.button.setMinimumWidth(0)

        for label, (key, _template) in self._snippet_items.items():
            self.combo.addItem(label, userData=key)

        try:
            self.combo.view().setVerticalScrollMode(self.combo.view().ScrollMode.ScrollPerPixel)
        except Exception:
            pass

        layout.addWidget(self.combo)
        layout.addWidget(self.button)

        self.button.clicked.connect(self._emit_insert)

    def current_key(self) -> str:
        return str(self.combo.currentData() or self.combo.currentText().strip())

    def set_on_insert_key(self, callback) -> None:
        self._on_insert_key = callback

    def _emit_insert(self) -> None:
        if callable(self._on_insert_key):
            self._on_insert_key(self.current_key())

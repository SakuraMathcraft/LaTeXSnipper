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

# Typst math syntax snippets (for use inside Typst math mode $...$)
TYPST_SNIPPETS = {
    "分式  (/)": ("fraction", r"#? / #?"),
    "上标  (Shift+^)": ("superscript", r"x^#?"),
    "下标  (Shift+_)": ("subscript", r"x_#?"),
    "上下标  (Shift+_ + Shift+^)": ("subsuperscript", r"x_#?^#?"),
    "根号  (sqrt)": ("sqrt", r"sqrt(#?)"),
    "求和  (sum)": ("sum", r"sum_(n=1)^oo #?"),
    "连乘  (prod)": ("product", r"product_(n=1)^oo #?"),
    "积分  (int)": ("integral", r"integral_a^b #? dif x"),
    "矩阵  (matrix)": ("matrix2", r"mat(#?, #?; #?, #?)"),
    "换行  (Shift+Enter)": ("newline", r"\\ "),
}

COMPACT_TYPST_SNIPPETS = {
    "分式": ("fraction", r"#? / #?"),
    "上标": ("superscript", r"x^#?"),
    "下标": ("subscript", r"x_#?"),
    "上下标": ("subsuperscript", r"x_#?^#?"),
    "根号": ("sqrt", r"sqrt(#?)"),
    "求和": ("sum", r"sum_(n=1)^oo #?"),
    "连乘": ("product", r"product_(n=1)^oo #?"),
    "积分": ("integral", r"integral_a^b #? dif x"),
    "矩阵": ("matrix2", r"mat(#?, #?; #?, #?)"),
    "换行": ("newline", r"\\ "),
}

SNIPPET_TEMPLATES = {key: template for key, template in (value for value in LATEX_SNIPPETS.values())}
# Also merge Typst templates so insert_snippet_into_editor can resolve both.
for _key, _template in TYPST_SNIPPETS.values():
    SNIPPET_TEMPLATES.setdefault(_key, _template)


def _get_snippets_for_mode(compact: bool) -> dict:
    """Return the appropriate snippet dictionary based on current render mode."""
    try:
        from exporting.formula_converters import get_current_render_mode
        if get_current_render_mode() == "typst":
            return COMPACT_TYPST_SNIPPETS if compact else TYPST_SNIPPETS
    except Exception:
        pass
    return COMPACT_LATEX_SNIPPETS if compact else LATEX_SNIPPETS


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
        self._compact = compact
        self._snippet_items = _get_snippets_for_mode(compact)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.combo = ComboBox(self)
        self.button = PushButton(FluentIcon.CODE, insert_button_text, self)
        self.combo.setFixedHeight(32)
        self.combo.setMinimumWidth(112)
        self.button.setFixedHeight(30)
        self.button.setMinimumWidth(0)

        self._rebuild_combo_items()

        try:
            self.combo.view().setVerticalScrollMode(self.combo.view().ScrollMode.ScrollPerPixel)
        except Exception:
            pass

        layout.addWidget(self.combo)
        layout.addWidget(self.button)

        self.button.clicked.connect(self._emit_insert)

    def _rebuild_combo_items(self):
        """Rebuild combo box items from the current snippet set."""
        self.combo.clear()
        for label, (key, _template) in self._snippet_items.items():
            self.combo.addItem(label, userData=key)

    def refresh_snippets(self) -> None:
        """Refresh snippets based on the current render mode."""
        new_items = _get_snippets_for_mode(self._compact)
        if new_items is not self._snippet_items:
            self._snippet_items = new_items
            self._rebuild_combo_items()

    def current_key(self) -> str:
        return str(self.combo.currentData() or self.combo.currentText().strip())

    def set_on_insert_key(self, callback) -> None:
        self._on_insert_key = callback

    def _emit_insert(self) -> None:
        if callable(self._on_insert_key):
            self._on_insert_key(self.current_key())

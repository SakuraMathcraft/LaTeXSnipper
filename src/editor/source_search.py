"""Search commands shared by source-editor windows."""

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtWidgets import QApplication

from localization.manager import translate as tr


class SourceSearchController(QObject):
    def __init__(self, window, *, editor, bar, input_field, status_label):
        super().__init__(window)
        self.window = window
        self.editor = editor
        self.bar = bar
        self.input = input_field
        self.status_label = status_label

    def _window_active(self) -> bool:
        app = QApplication.instance()
        if app is None or not self.window.isVisible():
            return False
        active_window = app.activeWindow()
        focus = app.focusWidget()
        return (
            active_window is self.window
            or focus is self.window
            or (focus is not None and self.window.isAncestorOf(focus))
        )

    def handle_toggle_shortcut(self) -> None:
        if self._window_active():
            self.toggle()

    def toggle(self) -> None:
        if self.bar.isVisible():
            self.hide()
        else:
            self.show()

    def show(self) -> None:
        selected = self.editor.textCursor().selectedText().replace("\u2029", "")
        self.bar.setVisible(True)
        if selected:
            self.input.setText(selected)
        self.input.setFocus()
        self.input.selectAll()
        self.refresh()

    def hide(self) -> None:
        if not self.bar.isVisible():
            return
        self.bar.setVisible(False)
        self.status_label.setText("")
        self.editor.setFocus()

    def handle_close_shortcut(self) -> None:
        if self.bar.isVisible() and self._window_active():
            self.hide()

    def handle_next_shortcut(self) -> None:
        if self.bar.isVisible() and self._window_active():
            self.find_next()

    def handle_previous_shortcut(self) -> None:
        if self.bar.isVisible() and self._window_active():
            self.find_previous()

    def _count_matches(self, needle: str) -> int:
        text = str(needle or "").strip()
        if not text:
            return 0
        document = self.editor.document()
        cursor = document.find(text)
        count = 0
        while not cursor.isNull():
            count += 1
            cursor = document.find(text, cursor)
        return count

    def refresh(self) -> None:
        text = str(self.input.text() or "").strip()
        if not text:
            self.status_label.setText("")
            return
        count = self._count_matches(text)
        self.status_label.setText(
            tr("{count} 项").format(count=count) if count else tr("未找到")
        )

    def _find(self, backward: bool = False) -> None:
        needle = str(self.input.text() or "").strip()
        if not needle:
            self.status_label.setText("")
            return
        flags = (
            QTextDocument.FindFlag.FindBackward
            if backward
            else QTextDocument.FindFlag(0)
        )
        found = self.editor.find(needle, flags)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End
                if backward
                else QTextCursor.MoveOperation.Start
            )
            self.editor.setTextCursor(cursor)
            found = self.editor.find(needle, flags)
        self.status_label.setText(
            tr("{count} 项").format(count=self._count_matches(needle))
            if found
            else tr("未找到")
        )

    def find_next(self) -> None:
        self._find(backward=False)

    def find_previous(self) -> None:
        self._find(backward=True)

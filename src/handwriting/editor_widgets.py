from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QTextFormat, QWheelEvent
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget
from qfluentwidgets import isDarkTheme


class _LineNumberArea(QWidget):
    def __init__(self, editor: "HandwritingPlainTextEdit", parent=None):
        super().__init__(parent or editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_number_area(event)


class HandwritingPlainTextEdit(QPlainTextEdit):
    """Lightweight plain-text editor with line numbers for the handwriting panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_number_area = _LineNumberArea(self)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_number_area_width(0)
        self._highlight_current_line()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomIn(1 if delta > 0 else -1)
                event.accept()
                self._update_line_number_area_width(0)
                return
        super().wheelEvent(event)

    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + QFontMetrics(self.font()).horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def paint_line_number_area(self, event) -> None:
        from PyQt6.QtGui import QPainter

        painter = QPainter(self._line_number_area)
        dark = bool(isDarkTheme())
        painter.fillRect(event.rect(), QColor("#1a2029" if dark else "#f3f4f6"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top()))
        bottom = top + int(round(self.blockBoundingRect(block).height()))
        current_line = self.textCursor().blockNumber()
        text_color = QColor("#7f8a99" if dark else "#8b95a5")
        active_color = QColor("#d7dee8" if dark else "#334155")
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(active_color if block_number == current_line else text_color)
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    int(Qt.AlignmentFlag.AlignRight),
                    str(block_number + 1),
                )
            block = block.next()
            block_number += 1
            top = bottom
            bottom = top + int(round(self.blockBoundingRect(block).height()))

    def _highlight_current_line(self) -> None:
        extra = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            dark = bool(isDarkTheme())
            selection.format.setBackground(QColor(74, 144, 226, 92) if dark else QColor(66, 133, 244, 72))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra.append(selection)
        self.setExtraSelections(extra)

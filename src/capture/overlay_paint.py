"""Paint the screenshot overlay's crosshair and selection feedback."""

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QRegion

_CROSSHAIR_ARM = 9
_CROSSHAIR_OUTER_WIDTH = 3


def draw_crosshair(painter: QPainter, pointer: QPoint) -> None:
    cx, cy = pointer.x(), pointer.y()
    outer_pen = QPen(QColor(0, 0, 0, 255), _CROSSHAIR_OUTER_WIDTH)
    outer_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    painter.setPen(outer_pen)
    painter.drawLine(cx - _CROSSHAIR_ARM, cy, cx + _CROSSHAIR_ARM, cy)
    painter.drawLine(cx, cy - _CROSSHAIR_ARM, cx, cy + _CROSSHAIR_ARM)
    inner_pen = QPen(QColor(255, 255, 255, 255), 1)
    inner_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    painter.setPen(inner_pen)
    painter.drawLine(cx - _CROSSHAIR_ARM, cy, cx + _CROSSHAIR_ARM, cy)
    painter.drawLine(cx, cy - _CROSSHAIR_ARM, cx, cy + _CROSSHAIR_ARM)


def cursor_region(pointer: QPoint, popup_rect: QRect) -> QRegion:
    padding = _CROSSHAIR_ARM + _CROSSHAIR_OUTER_WIDTH + 2
    return QRegion(
        QRect(
            pointer.x() - padding,
            pointer.y() - padding,
            padding * 2 + 1,
            padding * 2 + 1,
        )
    ).united(QRegion(popup_rect.adjusted(-2, -2, 2, 2)))


def selection_edge_region(rect: QRect, width: int) -> QRegion:
    outer = QRegion(rect.adjusted(-4, -4, 4, 4))
    inner_rect = rect.adjusted(4, 4, -4, -4)
    if not inner_rect.isEmpty():
        outer = outer.subtracted(QRegion(inner_rect))

    label_width = min(340, max(1, width - 4))
    label_height = 28
    label_x = max(2, min(rect.left() - 2, width - label_width - 2))
    label_y = rect.top() - label_height - 5
    if label_y < 2:
        label_y = rect.top() + 2
    outer += QRegion(QRect(label_x, label_y, label_width, label_height))
    return outer


def draw_selection(
    painter: QPainter,
    bounds: QRect,
    rect: QRect,
    global_rect: tuple[int, int, int, int],
    popup_rect: QRect | None,
) -> None:
    pen = QPen(QColor(0, 170, 255), 2)
    painter.save()
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if popup_rect is not None:
        avoid_region = QRegion(popup_rect.adjusted(-3, -3, 3, 3))
        draw_region = QRegion(bounds).subtracted(avoid_region)
        painter.setClipRegion(draw_region)

    painter.drawRect(rect)
    painter.restore()

    gx, gy, width, height = global_rect
    if width <= 0 or height <= 0:
        return
    text = f"{width} x {height}  ({gx}, {gy})"
    font = QFont("Segoe UI", 9)
    painter.setFont(font)
    fm = QFontMetrics(font)

    label_padding_x = 7
    label_h = fm.height() + 2
    label_w = fm.horizontalAdvance(text) + label_padding_x * 2

    label_x = rect.left()
    label_y = rect.top() - label_h - 5
    if label_y < 2:
        label_y = rect.top() + 5
    max_x = max(2, bounds.width() - label_w - 2)
    label_x = max(2, min(label_x, max_x))
    max_y = max(2, bounds.height() - label_h - 2)
    label_y = max(2, min(label_y, max_y))

    label_rect = QRect(label_x, label_y, label_w, label_h)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 150, 230, 218))
    painter.drawRoundedRect(label_rect, 3, 3)

    painter.setPen(QColor(255, 255, 255))
    painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

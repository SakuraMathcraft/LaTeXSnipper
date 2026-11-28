"""Sample and paint the screenshot magnifier and manage its color picker."""

from __future__ import annotations

import time
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QPoint, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

from capture.geometry import ScreenSnapshot
from localization.manager import translate as tr

_MAGNIFIER_SOURCE_WIDTH = 18
_MAGNIFIER_SOURCE_HEIGHT = 18
_MAGNIFIER_ZOOM = 7
_MAGNIFIER_PREVIEW_WIDTH = _MAGNIFIER_SOURCE_WIDTH * _MAGNIFIER_ZOOM
_MAGNIFIER_PREVIEW_HEIGHT = _MAGNIFIER_SOURCE_HEIGHT * _MAGNIFIER_ZOOM
_MAGNIFIER_PANEL_HEIGHT = 76
_MAGNIFIER_MARGIN = 14
_MAGNIFIER_RADIUS = 9
_COPY_NOTICE_SECONDS = 1.2


@dataclass(frozen=True)
class _MagnifierSample:
    preview: QImage
    color: QColor
    global_x: int
    global_y: int


def magnifier_popup_rect(pointer: QPoint, screen_bounds: QRect) -> QRect:
    """Place the magnifier beside the pointer, flipping at screen edges."""
    width = _MAGNIFIER_PREVIEW_WIDTH
    height = _MAGNIFIER_PREVIEW_HEIGHT + _MAGNIFIER_PANEL_HEIGHT
    margin = _MAGNIFIER_MARGIN
    x = int(pointer.x()) + margin
    y = int(pointer.y()) + margin
    if x + width - 1 > screen_bounds.right():
        x = int(pointer.x()) - margin - width
    if y + height - 1 > screen_bounds.bottom():
        y = int(pointer.y()) - margin - height

    max_x = screen_bounds.right() - width + 1
    max_y = screen_bounds.bottom() - height + 1
    x = (
        screen_bounds.left()
        if max_x < screen_bounds.left()
        else max(screen_bounds.left(), min(x, max_x))
    )
    y = (
        screen_bounds.top()
        if max_y < screen_bounds.top()
        else max(screen_bounds.top(), min(y, max_y))
    )
    return QRect(x, y, width, height)


def _image_xy_for_global_pos(
    snapshot: ScreenSnapshot, global_pos: QPoint
) -> tuple[int, int]:
    """Map a desktop logical point to the snapshot's device pixels."""
    geo = snapshot.geometry
    image = snapshot.image
    local_x = max(0, int(global_pos.x()) - int(geo.x()))
    local_y = max(0, int(global_pos.y()) - int(geo.y()))
    image_x = int(local_x * snapshot.scale_x)
    image_y = int(local_y * snapshot.scale_y)
    image_x = max(0, min(image_x, image.width() - 1))
    image_y = max(0, min(image_y, image.height() - 1))
    return (image_x, image_y)


def _build_sample(snapshot: ScreenSnapshot, global_pos: QPoint) -> _MagnifierSample:
    image = snapshot.image
    image_x, image_y = _image_xy_for_global_pos(snapshot, global_pos)
    radius_x = _MAGNIFIER_SOURCE_WIDTH // 2
    radius_y = _MAGNIFIER_SOURCE_HEIGHT // 2
    source_rect = QRect(
        image_x - radius_x,
        image_y - radius_y,
        _MAGNIFIER_SOURCE_WIDTH,
        _MAGNIFIER_SOURCE_HEIGHT,
    )
    sample = QImage(
        _MAGNIFIER_SOURCE_WIDTH,
        _MAGNIFIER_SOURCE_HEIGHT,
        QImage.Format.Format_RGB32,
    )
    sample.fill(QColor(255, 255, 255))
    clipped_source = source_rect.intersected(image.rect())
    if not clipped_source.isEmpty():
        target_rect = QRect(
            clipped_source.left() - source_rect.left(),
            clipped_source.top() - source_rect.top(),
            clipped_source.width(),
            clipped_source.height(),
        )
        sample_painter = QPainter(sample)
        sample_painter.drawImage(target_rect, image, clipped_source)
        sample_painter.end()

    preview = sample.scaled(
        _MAGNIFIER_PREVIEW_WIDTH,
        _MAGNIFIER_PREVIEW_HEIGHT,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return _MagnifierSample(
        preview=preview,
        color=QColor(image.pixelColor(image_x, image_y)),
        global_x=int(global_pos.x()),
        global_y=int(global_pos.y()),
    )


def _draw_shadowed_text(
    painter: QPainter,
    rect: QRect,
    flags: Qt.AlignmentFlag,
    text: str,
    color: QColor,
) -> None:
    shadow_rect = QRect(rect)
    shadow_rect.translate(0, 1)
    painter.setPen(QColor(0, 0, 0, 175))
    painter.drawText(shadow_rect, flags, text)
    painter.setPen(color)
    painter.drawText(rect, flags, text)


class CaptureMagnifier(QObject):
    changed = pyqtSignal()

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._hex_color = False
        self._copy_notice_until = 0.0
        self._copy_notice_timer = QTimer(self)
        self._copy_notice_timer.setSingleShot(True)
        self._copy_notice_timer.timeout.connect(self.changed.emit)

    def toggle_color_format(self) -> None:
        self._hex_color = not self._hex_color
        self.changed.emit()

    def _format_color_value(self, color: QColor) -> str:
        if self._hex_color:
            return f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
        return f"{color.red()}, {color.green()}, {color.blue()}"

    def copy_color(self, snapshot: ScreenSnapshot, global_pos: QPoint) -> None:
        image_x, image_y = _image_xy_for_global_pos(snapshot, global_pos)
        color = snapshot.image.pixelColor(image_x, image_y)
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._format_color_value(color))
                self._copy_notice_until = time.monotonic() + _COPY_NOTICE_SECONDS
                self._copy_notice_timer.start(int(_COPY_NOTICE_SECONDS * 1000))
        except Exception:
            pass
        self.changed.emit()

    def paint(
        self,
        painter: QPainter,
        popup_rect: QRect,
        snapshot: ScreenSnapshot,
        global_pos: QPoint,
    ) -> None:
        sample = _build_sample(snapshot, global_pos)
        preview_rect = QRect(
            popup_rect.left(),
            popup_rect.top(),
            _MAGNIFIER_PREVIEW_WIDTH,
            _MAGNIFIER_PREVIEW_HEIGHT,
        )
        panel_rect = QRect(
            popup_rect.left(),
            preview_rect.bottom() + 1,
            _MAGNIFIER_PREVIEW_WIDTH,
            _MAGNIFIER_PANEL_HEIGHT,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        outer_path = QPainterPath()
        outer_path.addRoundedRect(
            QRectF(popup_rect), _MAGNIFIER_RADIUS, _MAGNIFIER_RADIUS
        )
        painter.setClipPath(outer_path)
        painter.fillPath(outer_path, QColor(24, 24, 24, 244))

        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawImage(preview_rect, sample.preview)
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)

        pixel_start_x = (_MAGNIFIER_SOURCE_WIDTH // 2) * _MAGNIFIER_ZOOM
        pixel_start_y = (_MAGNIFIER_SOURCE_HEIGHT // 2) * _MAGNIFIER_ZOOM
        pixel_rect = QRect(
            preview_rect.left() + pixel_start_x,
            preview_rect.top() + pixel_start_y,
            _MAGNIFIER_ZOOM,
            _MAGNIFIER_ZOOM,
        )
        center_x = pixel_rect.left() + pixel_rect.width() // 2
        center_y = pixel_rect.top() + pixel_rect.height() // 2
        painter.save()
        painter.setClipRect(preview_rect.adjusted(1, 1, -1, -1))
        guide_pen = QPen(QColor(0, 174, 255, 225), 1)
        guide_pen.setCosmetic(True)
        guide_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(guide_pen)
        painter.drawLine(
            preview_rect.left() + 1, center_y, preview_rect.right() - 1, center_y
        )
        painter.drawLine(
            center_x, preview_rect.top() + 1, center_x, preview_rect.bottom() - 1
        )
        painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(28, 28, 28, 244))
        painter.drawRect(panel_rect)

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_color = QColor(255, 255, 255, 242)

        coord_rect = QRect(
            panel_rect.left() + 8, panel_rect.top() + 4, panel_rect.width() - 16, 16
        )
        _draw_shadowed_text(
            painter,
            coord_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"({sample.global_x}, {sample.global_y})",
            text_color,
        )

        mode_label = "HEX" if self._hex_color else "RGB"
        value_text = f"{mode_label} {self._format_color_value(sample.color)}"
        swatch_size = 12
        value_w = fm.horizontalAdvance(value_text)
        value_total_w = swatch_size + 7 + value_w
        value_x = panel_rect.left() + max(8, (panel_rect.width() - value_total_w) // 2)
        value_y = panel_rect.top() + 24
        swatch_rect = QRect(value_x, value_y + 2, swatch_size, swatch_size)
        painter.setPen(QPen(QColor(255, 255, 255, 210), 1))
        painter.setBrush(sample.color)
        painter.drawRect(swatch_rect)
        _draw_shadowed_text(
            painter,
            QRect(swatch_rect.right() + 7, value_y - 1, panel_rect.width(), 18),
            Qt.AlignmentFlag.AlignVCenter,
            value_text,
            text_color,
        )

        copy_hint = (
            tr("已复制")
            if time.monotonic() < self._copy_notice_until
            else tr("按 C 复制色值")
        )
        _draw_shadowed_text(
            painter,
            QRect(
                panel_rect.left() + 8,
                panel_rect.top() + 46,
                panel_rect.width() - 16,
                16,
            ),
            Qt.AlignmentFlag.AlignCenter,
            copy_hint,
            QColor(255, 255, 255, 232),
        )
        _draw_shadowed_text(
            painter,
            QRect(
                panel_rect.left() + 8,
                panel_rect.top() + 59,
                panel_rect.width() - 16,
                16,
            ),
            Qt.AlignmentFlag.AlignCenter,
            tr("Shift 切换格式"),
            QColor(255, 255, 255, 232),
        )
        painter.setClipping(False)
        border_pen = QPen(QColor(92, 92, 92, 190), 1)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_rect = QRectF(popup_rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(border_rect, _MAGNIFIER_RADIUS, _MAGNIFIER_RADIUS)
        painter.restore()

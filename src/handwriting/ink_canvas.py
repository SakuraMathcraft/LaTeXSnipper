from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QImage, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QSizePolicy, QWidget

from qfluentwidgets import FluentIcon

from .stroke_store import StrokeStore
from .tools import HandwritingTool
from .types import CanvasExportResult, InkStroke

try:
    from PyQt6.QtGui import QTabletEvent
except Exception:  # pragma: no cover
    QTabletEvent = None


class InkCanvas(QWidget):
    contentChanged = pyqtSignal()
    strokeFinished = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    panRequested = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.store = StrokeStore()
        self.current_tool = HandwritingTool.WRITE
        self.current_stroke: InkStroke | None = None
        self.selection_rect = QRectF()
        self.selection_points: list[QPointF] = []
        self.selection_path = QPainterPath()
        self.pen_width = 4.0
        self.erase_tolerance = 14.0
        self.canvas_margin = 24.0
        self._is_dragging = False
        self._is_panning = False
        self._pan_last_pos = QPoint()
        self._tablet_active = False
        self._logical_width = 3200
        self._logical_height = 2400
        self._zoom = 1.0
        self._min_zoom = 0.3
        self._max_zoom = 2.2
        self._zoom_step = 0.08
        self._is_dark = False
        self._ui_tokens = self._theme_tokens(False)
        self._erase_cursor = None
        self._write_cursor = None
        self._select_cursor = None
        self._apply_display_size()

    def set_tool(self, tool: HandwritingTool) -> None:
        self.current_tool = tool
        self.selection_rect = QRectF()
        self.selection_points = []
        self.selection_path = QPainterPath()
        self._apply_tool_cursor()
        self.update()

    def set_dark_mode(self, enabled: bool) -> None:
        self._is_dark = bool(enabled)
        self._ui_tokens = self._theme_tokens(self._is_dark)
        self.update()

    def _display_width(self) -> int:
        return max(1, int(round(self._logical_width * self._zoom)))

    def _display_height(self) -> int:
        return max(1, int(round(self._logical_height * self._zoom)))

    def zoom_factor(self) -> float:
        return float(self._zoom)

    def _apply_display_size(self) -> None:
        self.setMinimumSize(self._display_width(), self._display_height())
        self.resize(self._display_width(), self._display_height())
        self.updateGeometry()

    def _to_scene_point(self, pos: QPointF) -> QPointF:
        if self._zoom == 1.0:
            return QPointF(pos)
        return QPointF(pos.x() / self._zoom, pos.y() / self._zoom)

    def set_zoom(self, zoom: float) -> bool:
        zoom = max(self._min_zoom, min(self._max_zoom, float(zoom)))
        if abs(zoom - self._zoom) < 1e-6:
            return False
        self._zoom = zoom
        self._apply_display_size()
        self.update()
        return True

    def zoom_in(self) -> bool:
        return self.set_zoom(round(self._zoom + self._zoom_step, 2))

    def zoom_out(self) -> bool:
        return self.set_zoom(round(self._zoom - self._zoom_step, 2))

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                changed = self.zoom_in() if delta > 0 else self.zoom_out()
                if changed:
                    event.accept()
                    return
        super().wheelEvent(event)

    def clear_canvas(self) -> bool:
        changed = self.store.clear()
        if changed:
            self.selection_rect = QRectF()
            self.selection_points = []
            self.selection_path = QPainterPath()
            self.contentChanged.emit()
            self.update()
        return changed

    def undo(self) -> bool:
        changed = self.store.undo()
        if changed:
            self.selection_rect = QRectF()
            self.selection_points = []
            self.selection_path = QPainterPath()
            self.contentChanged.emit()
            self.update()
        return changed

    def redo(self) -> bool:
        changed = self.store.redo()
        if changed:
            self.selection_rect = QRectF()
            self.selection_points = []
            self.selection_path = QPainterPath()
            self.contentChanged.emit()
            self.update()
        return changed

    def content_bounding_rect(self) -> QRectF:
        return self.store.content_bounds()

    def export_image(self) -> CanvasExportResult:
        bounds = self.content_bounding_rect()
        if bounds.isNull() or bounds.isEmpty():
            return CanvasExportResult(image=None, bounds=QRectF(), is_empty=True)
        padded = bounds.adjusted(-self.canvas_margin, -self.canvas_margin, self.canvas_margin, self.canvas_margin)
        width = max(1, int(round(padded.width())))
        height = max(1, int(round(padded.height())))
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(-padded.left(), -padded.top())
        for stroke in self.store.strokes:
            self._paint_stroke(painter, stroke, export_mode=True)
        painter.end()
        return CanvasExportResult(image=image, bounds=padded, is_empty=False)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._start_pan(event)
            return
        pos = self._to_scene_point(event.position())
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._begin_interaction(pos, pressure=None)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.accept()
            return
        if self._is_panning:
            self._continue_pan(event)
            return
        pos = self._to_scene_point(event.position())
        if not self._is_dragging:
            return super().mouseMoveEvent(event)
        self._continue_interaction(pos, pressure=None)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._tablet_active:
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton and self._is_panning:
            self._stop_pan()
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        self._finish_interaction()
        self.update()

    def tabletEvent(self, event):  # pragma: no cover - hardware-dependent
        if QTabletEvent is None:
            return super().tabletEvent(event)
        pos = self._to_scene_point(event.position())
        pressure = max(0.05, float(event.pressure() or 0.0))
        self._tablet_active = event.type() != QTabletEvent.Type.TabletRelease
        if event.type() == QTabletEvent.Type.TabletPress:
            self._begin_interaction(pos, pressure=pressure)
            event.accept()
            return
        if event.type() == QTabletEvent.Type.TabletMove:
            if self._is_dragging:
                self._continue_interaction(pos, pressure=pressure)
            event.accept()
            return
        if event.type() == QTabletEvent.Type.TabletRelease:
            self._finish_interaction()
            self._tablet_active = False
            event.accept()
            return
        super().tabletEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(self._ui_tokens["canvas_bg"]))
        painter.scale(self._zoom, self._zoom)
        self._paint_grid(painter, QRectF(0, 0, self._logical_width, self._logical_height), export_mode=False)
        for stroke in self.store.strokes:
            self._paint_stroke(painter, stroke, export_mode=False)
        if self.current_stroke is not None:
            self._paint_stroke(painter, self.current_stroke, export_mode=False)
        if not self.selection_path.isEmpty():
            pen = QPen(QColor(self._ui_tokens["selection_border"]), 1.6, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QColor(*self._ui_tokens["selection_fill"]))
            painter.drawPath(self.selection_path)
        painter.end()

    def _make_erase_cursor(self) -> QCursor:
        icon = FluentIcon.ERASE_TOOL.icon()
        pixmap = icon.pixmap(22, 22)
        if pixmap.isNull():
            pixmap = QPixmap(22, 22)
            pixmap.fill(Qt.GlobalColor.transparent)
        return QCursor(pixmap, 4, 18)

    def _make_write_cursor(self) -> QCursor:
        icon = FluentIcon.EDIT.icon()
        pixmap = icon.pixmap(22, 22)
        if pixmap.isNull():
            pixmap = QPixmap(22, 22)
            pixmap.fill(Qt.GlobalColor.transparent)
        return QCursor(pixmap, 4, 18)

    def _make_select_cursor(self) -> QCursor:
        icon = FluentIcon.PIN.icon()
        pixmap = icon.pixmap(22, 22)
        if pixmap.isNull():
            pixmap = QPixmap(22, 22)
            pixmap.fill(Qt.GlobalColor.transparent)
        return QCursor(pixmap, 8, 2)

    def _apply_tool_cursor(self) -> None:
        if self._is_panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.current_tool == HandwritingTool.ERASE:
            if self._erase_cursor is None:
                self._erase_cursor = self._make_erase_cursor()
            self.setCursor(self._erase_cursor)
            return
        if self.current_tool == HandwritingTool.WRITE:
            if self._write_cursor is None:
                self._write_cursor = self._make_write_cursor()
            self.setCursor(self._write_cursor)
            return
        if self.current_tool == HandwritingTool.SELECT_CORRECT:
            if self._select_cursor is None:
                self._select_cursor = self._make_select_cursor()
            self.setCursor(self._select_cursor)
            return
        self.unsetCursor()

    def _theme_tokens(self, dark: bool) -> dict:
        if dark:
            return {
                "canvas_bg": "#20262f",
                "grid": "#3a4656",
                "stroke": "#f3f4f6",
                "selection_border": "#7cc4ff",
                "selection_fill": (124, 196, 255, 44),
            }
        return {
            "canvas_bg": "#fff9d7",
            "grid": "#eddc92",
            "stroke": "#111111",
            "selection_border": "#1f6feb",
            "selection_fill": (31, 111, 235, 32),
        }

    def _start_pan(self, event: QMouseEvent) -> None:
        self._is_panning = True
        self._pan_last_pos = event.globalPosition().toPoint()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def _continue_pan(self, event: QMouseEvent) -> None:
        current = event.globalPosition().toPoint()
        delta = current - self._pan_last_pos
        self._pan_last_pos = current
        self.panRequested.emit(-delta.x(), -delta.y())
        event.accept()

    def _stop_pan(self) -> None:
        self._is_panning = False
        self._apply_tool_cursor()

    def _begin_interaction(self, pos: QPointF, pressure: float | None) -> None:
        self._is_dragging = True
        if self.current_tool == HandwritingTool.WRITE:
            self.current_stroke = InkStroke.from_points([QPointF(pos)], width=self._resolve_pen_width(pressure))
            return
        elif self.current_tool == HandwritingTool.ERASE:
            self._erase_at(pos)
        elif self.current_tool == HandwritingTool.SELECT_CORRECT:
            self.selection_points = [QPointF(pos)]
            self.selection_path = QPainterPath(QPointF(pos))
            self.selection_rect = QRectF(pos, pos).normalized()
            self.selectionChanged.emit(True)

    def _continue_interaction(self, pos: QPointF, pressure: float | None) -> None:
        if self.current_tool == HandwritingTool.WRITE and self.current_stroke is not None:
            self.current_stroke.points.append(QPointF(pos))
            self.current_stroke.width = self._resolve_pen_width(pressure)
            self.current_stroke.rebuild_geometry()
            self.update()
            return
        if self.current_tool == HandwritingTool.WRITE and self.current_stroke is None:
            self.current_stroke = InkStroke.from_points([QPointF(pos)], width=self._resolve_pen_width(pressure))
            self.update()
            return
        if self.current_tool == HandwritingTool.ERASE:
            self._erase_at(pos)
            return
        if self.current_tool == HandwritingTool.SELECT_CORRECT:
            self.selection_points.append(QPointF(pos))
            self.selection_rect = self.selection_rect.united(QRectF(pos, pos).normalized())
            self.selection_path = self._build_selection_path(closed=False)
            self.update()
            return

    def _finish_interaction(self) -> None:
        self._is_dragging = False
        if self.current_tool == HandwritingTool.WRITE and self.current_stroke is not None:
            if len(self.current_stroke.points) == 1:
                p = self.current_stroke.points[0]
                self.current_stroke.points.append(QPointF(p.x() + 0.1, p.y() + 0.1))
                self.current_stroke.rebuild_geometry()
            self.store.add_stroke(self.current_stroke)
            self.current_stroke = None
            self.contentChanged.emit()
            self.strokeFinished.emit()
        elif self.current_tool == HandwritingTool.SELECT_CORRECT:
            self._delete_selected_segments()

    def _resolve_pen_width(self, pressure: float | None) -> float:
        if pressure is None:
            return self.pen_width
        return max(2.5, min(7.5, self.pen_width * (0.65 + pressure * 0.75)))

    def _paint_grid(self, painter: QPainter, rect: QRectF, export_mode: bool) -> None:
        painter.save()
        color = QColor("#eadf9d") if export_mode else QColor(self._ui_tokens["grid"])
        painter.setPen(QPen(color, 1))
        step = 32
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        for x in range(left, int(rect.right()) + step, step):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(top, int(rect.bottom()) + step, step):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
        painter.restore()

    def _paint_stroke(self, painter: QPainter, stroke: InkStroke, export_mode: bool) -> None:
        outline = stroke.outline_path
        if outline.isEmpty() and stroke.points:
            stroke.rebuild_geometry()
            outline = stroke.outline_path
        if outline.isEmpty():
            return
        color = QColor("#111111") if export_mode else QColor(self._ui_tokens["stroke"])
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(outline)
        painter.restore()

    def _build_selection_path(self, closed: bool) -> QPainterPath:
        if not self.selection_points:
            return QPainterPath()
        points = [QPointF(p) for p in self.selection_points]
        path = InkStroke.smooth_path_from_points(points)
        if closed and len(points) >= 3:
            path.lineTo(points[0])
            path.closeSubpath()
        return path.simplified()

    def _erase_at(self, pos: QPointF) -> None:
        if self.store.erase_with_circle(pos, self.erase_tolerance):
            self.contentChanged.emit()
            self.update()

    def _delete_selected_segments(self) -> None:
        if len(self.selection_points) < 3:
            self.selection_rect = QRectF()
            self.selection_points = []
            self.selection_path = QPainterPath()
            self.selectionChanged.emit(False)
            return
        self.selection_path = self._build_selection_path(closed=True)
        changed = self.store.erase_with_path(self.selection_path)
        self.selection_rect = QRectF()
        self.selection_points = []
        self.selection_path = QPainterPath()
        self.selectionChanged.emit(False)
        if changed:
            self.contentChanged.emit()
            self.update()

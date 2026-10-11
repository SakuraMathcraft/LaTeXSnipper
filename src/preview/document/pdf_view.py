"""Shared geometry and interaction behavior for PDF preview backends."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QColor, QCursor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QScrollArea

from localization.manager import translate as tr


class PdfView(QScrollArea):
    """PDF view behavior operating on the backend's page geometry and zoom."""

    def _build_magnifier_cursor(self) -> QCursor:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#1c1c1c"), 4))
        painter.drawEllipse(4, 4, 16, 16)
        painter.drawLine(17, 17, 28, 28)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(4, 4, 16, 16)
        painter.drawLine(17, 17, 28, 28)
        painter.end()
        return QCursor(pixmap, 12, 12)

    def _content_pos(self, pos: QPoint) -> QPoint:
        return QPoint(
            pos.x() + self.horizontalScrollBar().value(),
            pos.y() + self.verticalScrollBar().value(),
        )

    def _effective_zoom(self, page_width: float, page_height: float) -> float:
        viewport_w = max(1, self._grid_cell_width())
        viewport_h = max(1, self.viewport().height() - 2 * self._page_margin)
        if self._zoom_mode == "fit_width":
            return max(0.01, viewport_w / max(1.0, page_width))
        if self._zoom_mode == "fit_text_width":
            return max(0.01, viewport_w / max(1.0, page_width * self._text_width_ratio))
        if self._zoom_mode == "fit_window":
            return max(
                0.01,
                min(
                    viewport_w / max(1.0, page_width),
                    viewport_h / max(1.0, page_height),
                ),
            )
        return max(0.01, self._zoom_factor)

    def _grid_cell_width(self) -> int:
        cols = max(1, int(self._page_grid_cols))
        viewport_w = max(1, self.viewport().width())
        gap = self._grid_spacing()
        total_gap = max(0, cols - 1) * gap
        usable = max(1, viewport_w - 2 * self._page_margin - total_gap)
        return max(1, int(usable // cols))

    def _grid_spacing(self) -> int:
        cols = max(1, int(self._page_grid_cols))
        rows = max(1, int(self._page_grid_rows))
        if cols > 1 or rows > 1:
            return max(1, int(self._page_margin))
        return max(1, int(self._page_spacing))

    def _hide_magnifier_cursor(self) -> None:
        self.viewport().setCursor(Qt.CursorShape.BlankCursor)

    def _locate_page_at(self, content_pos: QPoint, allow_outside: bool = False):
        if not allow_outside:
            for index, rect in enumerate(self._page_rects):
                if rect.contains(content_pos):
                    rel_x = (content_pos.x() - rect.x()) / max(1, rect.width())
                    rel_y = (content_pos.y() - rect.y()) / max(1, rect.height())
                    return index, rect, rel_x, rel_y
            return None
        px = int(content_pos.x())
        py = int(content_pos.y())
        best = None
        best_d2 = None
        for index, rect in enumerate(self._page_rects):
            rel_x = (content_pos.x() - rect.x()) / max(1, rect.width())
            rel_y = (content_pos.y() - rect.y()) / max(1, rect.height())
            if rect.left() <= px <= rect.right():
                dx = 0
            elif px < rect.left():
                dx = int(rect.left() - px)
            else:
                dx = int(px - rect.right())
            if rect.top() <= py <= rect.bottom():
                dy = 0
            elif py < rect.top():
                dy = int(rect.top() - py)
            else:
                dy = int(py - rect.bottom())
            d2 = int(dx * dx + dy * dy)
            if best is None or d2 < int(best_d2):
                best = (index, rect, rel_x, rel_y)
                best_d2 = d2
        return best

    def _position_magnifier_label(self, viewport_pos: QPoint) -> None:
        radius = self._magnifier_size // 2
        top_left = QPoint(viewport_pos.x() - radius, viewport_pos.y() - radius)
        # Keep lens centered on cursor; let viewport clipping show partial disk near edges.
        self._magnifier_label.move(top_left)

    def _restore_magnifier_cursor(self) -> None:
        self.viewport().setCursor(self._magnifier_cursor)

    def _show_context_menu(self, viewport_pos: QPoint, global_pos: QPoint) -> None:
        menu = QMenu(self)
        jump_action = QAction(tr("跳转到源"), menu)
        zoom_in_action = QAction(tr("放大"), menu)
        zoom_out_action = QAction(tr("缩小"), menu)
        menu.addAction(jump_action)
        menu.addAction(zoom_in_action)
        menu.addAction(zoom_out_action)
        chosen = menu.exec(global_pos)
        if chosen is jump_action:
            hit = self._locate_page_at(self._content_pos(viewport_pos))
            if hit is None:
                return
            idx, _rect, rel_x, rel_y = hit
            page_w, page_h = self._page_sizes[idx]
            self.syncJumpRequested.emit(
                idx + 1, float(rel_x) * float(page_w), float(rel_y) * float(page_h)
            )
            return
        current = self.zoomFactor()
        if chosen is zoom_in_action:
            self._zoom_at(viewport_pos, current + 0.18)
        elif chosen is zoom_out_action:
            self._zoom_at(viewport_pos, current - 0.18)

    def _zoom_at(self, viewport_pos: QPoint, factor: float) -> None:
        content_before = self._content_pos(viewport_pos)
        hit = self._locate_page_at(content_before)
        self.setZoomFactor(factor)
        if hit is None:
            return
        index, _rect, rel_x, rel_y = hit
        if index >= len(self._page_rects):
            return
        rect = self._page_rects[index]
        target = QPoint(
            int(round(rect.x() + rel_x * rect.width() - viewport_pos.x())),
            int(round(rect.y() + rel_y * rect.height() - viewport_pos.y())),
        )
        self.horizontalScrollBar().setValue(max(0, target.x()))
        self.verticalScrollBar().setValue(max(0, target.y()))

    def zoomFactor(self) -> float:
        return float(self._zoom_factor)

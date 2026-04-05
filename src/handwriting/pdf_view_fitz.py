from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, QRect, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PyQt6.QtGui import QRegion
from PyQt6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene, QLabel, QMenu, QScrollArea, QSizePolicy, QWidget

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None


if fitz is not None:
    class _FitzPdfCanvas(QWidget):
        def __init__(self, owner, parent=None):
            super().__init__(parent)
            self.owner = owner
            self.setMouseTracking(True)

        def paintEvent(self, event) -> None:
            super().paintEvent(event)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.fillRect(self.rect(), QColor("#7d7d7d"))
            for pixmap, rect in zip(self.owner._page_pixmaps, self.owner._page_rects):
                painter.fillRect(rect, QColor("#ffffff"))
                painter.drawImage(rect, pixmap)
            painter.end()

        def mousePressEvent(self, event: QMouseEvent) -> None:
            self.owner._handle_mouse_press(event)

        def mouseMoveEvent(self, event: QMouseEvent) -> None:
            self.owner._handle_mouse_move(event)

        def mouseReleaseEvent(self, event: QMouseEvent) -> None:
            self.owner._handle_mouse_release(event)

        def leaveEvent(self, event) -> None:
            self.owner._handle_leave(event)
            super().leaveEvent(event)


    class FitzPdfView(QScrollArea):
        syncJumpRequested = pyqtSignal(int, float, float)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._doc = None
            self._doc_path = None
            self._page_sources: list[QImage] = []
            self._page_source_scales: list[float] = []
            self._page_pixmaps: list[QImage] = []
            self._page_rects: list[QRect] = []
            self._page_sizes: list[tuple[float, float]] = []
            self._zoom_factor = 1.0
            self._zoom_mode = "fit_width"
            self._page_spacing = 12
            self._page_margin = 2
            self._text_width_ratio = 0.82
            self._page_grid_cols = 1
            self._page_grid_rows = 1
            self._page_render_scale = 3.0
            self._max_source_edge = 2800
            self._magnifier_active = False
            self._magnifier_size = 300
            self._magnifier_zoom = 3.2
            self._magnifier_interactive_interval_ms = 16
            self._magnifier_hq_idle_ms = 70
            self._magnifier_min_move_px = 2
            self._pending_magnifier_pos: QPoint | None = None
            self._magnifier_pending_hq_pos: QPoint | None = None
            self._magnifier_last_viewport_pos: QPoint | None = None
            self._magnifier_last_source_image = QImage()
            self._magnifier_last_presented_pos: QPoint | None = None
            self._magnifier_last_lens_d = self._magnifier_size - 16
            self._magnifier_frame_cache: dict[tuple[int, str], QPixmap] = {}
            self._pan_active = False
            self._pan_dragged = False
            self._pan_start_pos = QPoint()
            self._pan_start_h = 0
            self._pan_start_v = 0
            self._canvas = _FitzPdfCanvas(self, self)
            self._canvas.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setWidget(self._canvas)
            self.setWidgetResizable(False)
            self.setMouseTracking(True)
            self.viewport().setMouseTracking(True)
            self._magnifier_label = QLabel(self.viewport())
            self._magnifier_label.setFixedSize(self._magnifier_size, self._magnifier_size)
            try:
                self._magnifier_label.setMask(QRegion(0, 0, self._magnifier_size, self._magnifier_size, QRegion.RegionType.Ellipse))
            except Exception:
                pass
            self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._magnifier_label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self._magnifier_label.setStyleSheet("background: transparent;")
            self._magnifier_label.hide()
            self._magnifier_cursor = self._build_magnifier_cursor()
            self.viewport().setCursor(self._magnifier_cursor)
            self._magnifier_update_timer = QTimer(self)
            self._magnifier_update_timer.setSingleShot(True)
            self._magnifier_update_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._magnifier_update_timer.setInterval(self._magnifier_interactive_interval_ms)
            self._magnifier_update_timer.timeout.connect(self._flush_magnifier_update)
            self._magnifier_hq_timer = QTimer(self)
            self._magnifier_hq_timer.setSingleShot(True)
            self._magnifier_hq_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._magnifier_hq_timer.setInterval(self._magnifier_hq_idle_ms)
            self._magnifier_hq_timer.timeout.connect(self._flush_magnifier_hq)
            self._deferred_render_timer = QTimer(self)
            self._deferred_render_timer.setSingleShot(True)
            self._deferred_render_timer.setInterval(120)
            self._deferred_render_timer.timeout.connect(self._render_pages)
            self.verticalScrollBar().valueChanged.connect(self._schedule_deferred_render)
            self.horizontalScrollBar().valueChanged.connect(self._schedule_deferred_render)
            self._configure_magnifier_timing_for_display()

        def _configure_magnifier_timing_for_display(self) -> None:
            refresh = 0.0
            try:
                scr = self.screen()
                if scr is not None:
                    refresh = float(scr.refreshRate() or 0.0)
            except Exception:
                refresh = 0.0
            if refresh <= 1.0:
                refresh = 60.0
            interval = max(5, min(16, int(round(1000.0 / refresh))))
            self._magnifier_interactive_interval_ms = int(interval)
            self._magnifier_update_timer.setInterval(self._magnifier_interactive_interval_ms)
            self._magnifier_min_move_px = 1 if self._magnifier_interactive_interval_ms <= 8 else 2

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

        def _hide_magnifier_cursor(self) -> None:
            self.viewport().setCursor(Qt.CursorShape.BlankCursor)

        def _restore_magnifier_cursor(self) -> None:
            self.viewport().setCursor(self._magnifier_cursor)

        def load_document(self, pdf_path: str) -> None:
            self._doc_path = str(pdf_path or "")
            self._doc = fitz.open(self._doc_path) if self._doc_path else None
            self._deferred_render_timer.stop()
            self._magnifier_update_timer.stop()
            self._magnifier_hq_timer.stop()
            self._pending_magnifier_pos = None
            self._magnifier_pending_hq_pos = None
            self._magnifier_last_viewport_pos = None
            self._magnifier_last_source_image = QImage()
            self._magnifier_last_presented_pos = None
            self._render_pages()

        def zoomFactor(self) -> float:
            return float(self._zoom_factor)

        def setZoomFactor(self, factor: float) -> None:
            self._zoom_mode = "custom"
            self._zoom_factor = max(0.25, min(5.0, float(factor)))
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

        def set_actual_size(self) -> None:
            self._zoom_mode = "custom"
            self._zoom_factor = 1.0
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

        def set_fit_window(self) -> None:
            self._zoom_mode = "fit_window"
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

        def set_fit_width(self) -> None:
            self._zoom_mode = "fit_width"
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

        def set_fit_text_width(self) -> None:
            self._zoom_mode = "fit_text_width"
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

        def set_page_grid(self, cols: int, rows: int = 1) -> None:
            self._page_grid_cols = max(1, int(cols or 1))
            self._page_grid_rows = max(1, int(rows or 1))
            self._render_pages(rerender_sources=False)
            self._schedule_deferred_render()

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

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            if self._zoom_mode != "custom":
                QTimer.singleShot(0, lambda: self._render_pages(rerender_sources=False))
                self._schedule_deferred_render()

        def _effective_zoom(self, page_width: float, page_height: float) -> float:
            viewport_w = max(1, self._grid_cell_width())
            viewport_h = max(1, self.viewport().height() - 2 * self._page_margin)
            if self._zoom_mode == "fit_width":
                return max(0.01, viewport_w / max(1.0, page_width))
            if self._zoom_mode == "fit_text_width":
                return max(0.01, viewport_w / max(1.0, page_width * self._text_width_ratio))
            if self._zoom_mode == "fit_window":
                return max(0.01, min(viewport_w / max(1.0, page_width), viewport_h / max(1.0, page_height)))
            return max(0.01, self._zoom_factor)

        def _schedule_deferred_render(self) -> None:
            if self._doc is None:
                return
            self._deferred_render_timer.start()

        def _render_pages(self, rerender_sources: bool = True) -> None:
            if self._doc is None:
                self._page_pixmaps = []
                self._page_sources = []
                self._page_source_scales = []
                self._page_rects = []
                self._page_sizes = []
                self._canvas.resize(10, 10)
                self._canvas.update()
                return
            old_sources = list(self._page_sources)
            old_source_scales = list(self._page_source_scales)
            self._page_pixmaps = []
            self._page_rects = []
            self._page_sizes = []
            y = self._page_margin
            viewport_w = self.viewport().width()
            max_w = viewport_w
            page_count = len(self._doc)
            if len(old_sources) != page_count:
                old_sources = [QImage() for _ in range(page_count)]
            if len(old_source_scales) != page_count:
                old_source_scales = [self._page_render_scale for _ in range(page_count)]
            self._page_sources = list(old_sources)
            self._page_source_scales = list(old_source_scales)
            page_layout: list[tuple[QRect, float, float, float]] = []
            cols = max(1, int(self._page_grid_cols))
            cell_w = self._grid_cell_width()
            gap = self._grid_spacing()
            page_metrics: list[tuple[float, float, float, int, int]] = []
            max_draw_w = 1
            for index in range(page_count):
                page = self._doc[index]
                rect = page.rect
                page_w = float(rect.width)
                page_h = float(rect.height)
                zoom = self._effective_zoom(page_w, page_h)
                draw_w = max(1, int(round(page_w * zoom)))
                draw_h = max(1, int(round(page_h * zoom)))
                page_metrics.append((page_w, page_h, zoom, draw_w, draw_h))
                if draw_w > max_draw_w:
                    max_draw_w = draw_w
            col_w = max(cell_w, int(max_draw_w))
            row_y = self._page_margin
            row_max_h = 0
            for index, (page_w, page_h, zoom, draw_w, draw_h) in enumerate(page_metrics):
                col = index % cols
                if index > 0 and col == 0:
                    row_y += row_max_h + gap
                    row_max_h = 0
                cell_left = self._page_margin + col * (col_w + gap)
                x = cell_left + max(0, (col_w - draw_w) // 2)
                draw_rect = QRect(x, row_y, draw_w, draw_h)
                self._page_rects.append(draw_rect)
                self._page_sizes.append((page_w, page_h))
                page_layout.append((draw_rect, page_w, page_h, zoom))
                row_max_h = max(row_max_h, draw_h)
                max_w = max(max_w, self._page_margin * 2 + cols * col_w + max(0, cols - 1) * gap)
            total_h = row_y + row_max_h + self._page_margin
            visible_rect = QRect(
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value(),
                max(1, self.viewport().width()),
                max(1, self.viewport().height()),
            )
            preload_rect = visible_rect.adjusted(
                -self.viewport().width(),
                -self.viewport().height(),
                self.viewport().width(),
                self.viewport().height(),
            )
            render_indices = {
                index
                for index, (draw_rect, _page_w, _page_h, _zoom) in enumerate(page_layout)
                if draw_rect.intersects(preload_rect)
            }
            for index, (draw_rect, _page_w, _page_h, zoom) in enumerate(page_layout):
                image = self._page_sources[index] if index < len(self._page_sources) else QImage()
                if rerender_sources and index in render_indices:
                    page = self._doc[index]
                    matrix_scale = zoom * self._page_render_scale
                    max_edge = max(page.rect.width * matrix_scale, page.rect.height * matrix_scale)
                    if max_edge > self._max_source_edge:
                        matrix_scale *= self._max_source_edge / max_edge
                    matrix = fitz.Matrix(matrix_scale, matrix_scale)
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    image = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format.Format_RGB888,
                    ).copy()
                    self._page_sources[index] = image
                    self._page_source_scales[index] = max(1.0, matrix_scale / max(zoom, 1e-6))
                display_image = image.scaled(
                    draw_rect.width(),
                    draw_rect.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation if rerender_sources else Qt.TransformationMode.FastTransformation,
                ) if image is not None and not image.isNull() else QImage()
                self._page_pixmaps.append(display_image)
            self._canvas.resize(max_w, max(total_h, self.viewport().height()))
            self._canvas.update()

        def _content_pos(self, pos: QPoint) -> QPoint:
            return QPoint(pos.x() + self.horizontalScrollBar().value(), pos.y() + self.verticalScrollBar().value())

        def _clamp_magnifier_center_to_page(self, viewport_pos: QPoint) -> QPoint:
            hit = self._locate_page_at(self._content_pos(viewport_pos), allow_outside=True)
            if hit is None:
                return QPoint(viewport_pos)
            _idx, rect, _rel_x, _rel_y = hit
            cx = int(min(max(self._content_pos(viewport_pos).x(), rect.left()), rect.right()))
            cy = int(min(max(self._content_pos(viewport_pos).y(), rect.top()), rect.bottom()))
            return QPoint(
                cx - self.horizontalScrollBar().value(),
                cy - self.verticalScrollBar().value(),
            )

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

        def _build_magnifier_frame(self, size: int, quality: str = "hq") -> QPixmap:
            quality_key = "unified"
            key = (int(size), quality_key)
            cached = self._magnifier_frame_cache.get(key)
            if cached is not None and not cached.isNull():
                return cached
            result = QPixmap(size, size)
            result.fill(Qt.GlobalColor.transparent)
            painter = QPainter(result)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            lens_rect = QRectF(8.0, 8.0, float(size) - 16.0, float(size) - 16.0)
            # Gaussian feather ring is rendered once and cached to avoid per-frame blur cost.
            blur_radius = 19.0
            pad = int(round(blur_radius)) + 3
            shadow_side = int(size + pad * 2)
            shadow_src = QPixmap(shadow_side, shadow_side)
            shadow_src.fill(Qt.GlobalColor.transparent)
            shadow_painter = QPainter(shadow_src)
            shadow_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            shadow_rect = QRectF(
                lens_rect.x() + float(pad),
                lens_rect.y() + float(pad),
                lens_rect.width(),
                lens_rect.height(),
            )
            shadow_painter.setPen(QPen(QColor(138, 138, 138, 188), 1.55))
            shadow_painter.setBrush(Qt.BrushStyle.NoBrush)
            shadow_painter.drawEllipse(shadow_rect)
            shadow_painter.setPen(QPen(QColor(145, 145, 145, 120), 1.9))
            shadow_painter.drawEllipse(shadow_rect.adjusted(1.8, 1.8, -1.8, -1.8))
            shadow_painter.end()

            scene = QGraphicsScene()
            item = QGraphicsPixmapItem(shadow_src)
            effect = QGraphicsBlurEffect()
            effect.setBlurRadius(blur_radius)
            effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
            item.setGraphicsEffect(effect)
            scene.addItem(item)
            shadow_blurred = QPixmap(shadow_side, shadow_side)
            shadow_blurred.fill(Qt.GlobalColor.transparent)
            scene_painter = QPainter(shadow_blurred)
            scene.render(
                scene_painter,
                QRectF(0.0, 0.0, float(shadow_side), float(shadow_side)),
                QRectF(0.0, 0.0, float(shadow_side), float(shadow_side)),
            )
            scene_painter.end()
            outside_path = QPainterPath()
            outside_path.addRect(QRectF(0.0, 0.0, float(size), float(size)))
            inner_path = QPainterPath()
            inner_path.addEllipse(lens_rect.adjusted(-0.5, -0.5, 0.5, 0.5))
            painter.save()
            painter.setClipPath(outside_path.subtracted(inner_path))
            painter.drawPixmap(0, 0, shadow_blurred.copy(pad, pad, int(size), int(size)))
            painter.restore()

            # Keep a crisp thin rim above the blurred feather.
            painter.setPen(QPen(QColor(146, 146, 146, 214), 0.55))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(lens_rect)
            painter.end()
            self._magnifier_frame_cache[key] = result
            return result

        def _compose_magnifier_pixmap(self, source_image: QImage, lens_d: int, quality: str) -> QPixmap:
            result = QPixmap(self._magnifier_size, self._magnifier_size)
            result.fill(Qt.GlobalColor.transparent)
            painter = QPainter(result)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            lens_rect = QRect(8, 8, lens_d, lens_d)
            lens_path = QPainterPath()
            lens_path.addEllipse(QRectF(lens_rect))
            painter.setClipPath(lens_path)
            painter.fillPath(lens_path, QColor(232, 232, 232))
            painter.drawImage(QRectF(lens_rect), source_image, QRectF(0.0, 0.0, float(source_image.width()), float(source_image.height())))
            painter.setClipping(False)
            painter.drawPixmap(0, 0, self._build_magnifier_frame(self._magnifier_size, quality=quality))
            painter.end()
            return result

        def _position_magnifier_label(self, viewport_pos: QPoint) -> None:
            radius = self._magnifier_size // 2
            top_left = QPoint(viewport_pos.x() - radius, viewport_pos.y() - radius)
            # Keep lens centered on cursor; let viewport clipping show partial disk near edges.
            self._magnifier_label.move(top_left)

        def _present_magnifier_pixmap(self, pixmap: QPixmap, viewport_pos: QPoint) -> None:
            self._magnifier_label.resize(self._magnifier_size, self._magnifier_size)
            self._magnifier_label.setPixmap(pixmap)
            self._position_magnifier_label(viewport_pos)
            self._magnifier_label.show()
            self._magnifier_label.raise_()

        def _predictive_magnifier_reuse(self, viewport_pos: QPoint) -> None:
            if not self._magnifier_active:
                return
            if self._magnifier_last_presented_pos is None:
                return
            if self._magnifier_last_source_image.isNull():
                return
            delta = QPoint(viewport_pos - self._magnifier_last_presented_pos)
            if delta.manhattanLength() < 1:
                return
            src = self._magnifier_last_source_image
            shifted = QImage(src.size(), QImage.Format.Format_ARGB32_Premultiplied)
            shifted.fill(QColor(232, 232, 232))
            painter = QPainter(shifted)
            painter.drawImage(-delta.x(), -delta.y(), src)
            painter.end()
            pixmap = self._compose_magnifier_pixmap(shifted, self._magnifier_last_lens_d, quality="fast")
            self._present_magnifier_pixmap(pixmap, viewport_pos)
            self._magnifier_last_source_image = shifted
            self._magnifier_last_presented_pos = QPoint(viewport_pos)

        def _update_magnifier(self, viewport_pos: QPoint, quality: str = "hq") -> None:
            content_pos = self._content_pos(viewport_pos)
            hit = self._locate_page_at(content_pos, allow_outside=True)
            if hit is None:
                self._magnifier_label.hide()
                return
            page_index, _rect, rel_x, rel_y = hit
            if page_index >= len(self._page_sources):
                self._magnifier_label.hide()
                return
            source_image = self._page_sources[page_index]
            if source_image.isNull():
                self._magnifier_label.hide()
                return
            lens_d = self._magnifier_size - 16
            source_scale = self._page_source_scales[page_index] if page_index < len(self._page_source_scales) else self._page_render_scale
            img_w = max(1, source_image.width())
            img_h = max(1, source_image.height())
            center_x = int(round(rel_x * img_w))
            center_y = int(round(rel_y * img_h))
            sample_w = max(40, int(round(lens_d * source_scale / max(1.0, self._magnifier_zoom))))
            sample_h = max(40, int(round(lens_d * source_scale / max(1.0, self._magnifier_zoom))))
            sample_rect = QRect(center_x - sample_w // 2, center_y - sample_h // 2, sample_w, sample_h)
            clipped = sample_rect.intersected(QRect(0, 0, img_w, img_h))
            if clipped.width() <= 0 or clipped.height() <= 0:
                self._magnifier_label.hide()
                return
            sampled = QImage(sample_w, sample_h, QImage.Format.Format_ARGB32_Premultiplied)
            sampled.fill(QColor(242, 242, 242))
            paste_x = int(clipped.x() - sample_rect.x())
            paste_y = int(clipped.y() - sample_rect.y())
            sample_painter = QPainter(sampled)
            sample_painter.drawImage(
                paste_x,
                paste_y,
                source_image,
                int(clipped.x()),
                int(clipped.y()),
                int(clipped.width()),
                int(clipped.height()),
            )
            sample_painter.end()
            transform_mode = Qt.TransformationMode.SmoothTransformation if str(quality).lower() == "hq" else Qt.TransformationMode.FastTransformation
            scaled_source = sampled.scaled(
                lens_d,
                lens_d,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                transform_mode,
            )
            pixmap = self._compose_magnifier_pixmap(scaled_source, lens_d, quality=quality)
            self._present_magnifier_pixmap(pixmap, viewport_pos)
            self._magnifier_last_source_image = scaled_source
            self._magnifier_last_lens_d = lens_d
            self._magnifier_last_presented_pos = QPoint(viewport_pos)

        def _queue_magnifier_update(self, viewport_pos: QPoint) -> None:
            viewport_pos = self._clamp_magnifier_center_to_page(viewport_pos)
            if self._magnifier_last_viewport_pos is not None:
                if (viewport_pos - self._magnifier_last_viewport_pos).manhattanLength() < self._magnifier_min_move_px:
                    return
            self._predictive_magnifier_reuse(viewport_pos)
            self._pending_magnifier_pos = QPoint(viewport_pos)
            self._magnifier_pending_hq_pos = None
            self._magnifier_hq_timer.stop()
            if not self._magnifier_update_timer.isActive():
                self._magnifier_update_timer.start()

        def _flush_magnifier_update(self) -> None:
            if self._pending_magnifier_pos is None or not self._magnifier_active:
                return
            pos = QPoint(self._pending_magnifier_pos)
            self._magnifier_last_viewport_pos = QPoint(pos)
            self._update_magnifier(pos, quality="hq")

        def _flush_magnifier_hq(self) -> None:
            return

        def _handle_mouse_press(self, event: QMouseEvent) -> None:
            vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            if event.button() == Qt.MouseButton.LeftButton:
                vp = self._clamp_magnifier_center_to_page(vp)
                self._magnifier_active = True
                self._hide_magnifier_cursor()
                self._pending_magnifier_pos = QPoint(vp)
                self._magnifier_pending_hq_pos = None
                self._update_magnifier(vp, quality="hq")
                self._magnifier_hq_timer.stop()
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self._pan_active = True
                self._pan_dragged = False
                self._pan_start_pos = vp
                self._pan_start_h = self.horizontalScrollBar().value()
                self._pan_start_v = self.verticalScrollBar().value()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                self._magnifier_label.hide()
                event.accept()
                return

        def _show_context_menu(self, viewport_pos: QPoint, global_pos: QPoint) -> None:
            menu = QMenu(self)
            jump_action = QAction("跳转到源", menu)
            zoom_in_action = QAction("放大", menu)
            zoom_out_action = QAction("缩小", menu)
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
                self.syncJumpRequested.emit(idx + 1, float(rel_x) * float(page_w), float(rel_y) * float(page_h))
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

        def _handle_mouse_move(self, event: QMouseEvent) -> None:
            vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            if self._pan_active:
                delta = vp - self._pan_start_pos
                if not self._pan_dragged and delta.manhattanLength() > 4:
                    self._pan_dragged = True
                self.horizontalScrollBar().setValue(self._pan_start_h - delta.x())
                self.verticalScrollBar().setValue(self._pan_start_v - delta.y())
                event.accept()
                return
            if self._magnifier_active:
                self._queue_magnifier_update(vp)
                event.accept()
                return

        def _handle_mouse_release(self, event: QMouseEvent) -> None:
            vp = event.position().toPoint() - QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            if event.button() == Qt.MouseButton.LeftButton and self._magnifier_active:
                self._magnifier_active = False
                self._magnifier_update_timer.stop()
                self._magnifier_hq_timer.stop()
                self._pending_magnifier_pos = None
                self._magnifier_pending_hq_pos = None
                self._magnifier_last_viewport_pos = None
                self._magnifier_last_source_image = QImage()
                self._magnifier_last_presented_pos = None
                self._magnifier_label.hide()
                self._restore_magnifier_cursor()
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton and self._pan_active:
                if not self._pan_dragged:
                    self._show_context_menu(vp, event.globalPosition().toPoint())
                self._pan_active = False
                self._pan_dragged = False
                self._restore_magnifier_cursor()
                event.accept()
                return

        def _handle_leave(self, _event) -> None:
            self._magnifier_active = False
            self._pan_active = False
            self._magnifier_update_timer.stop()
            self._magnifier_hq_timer.stop()
            self._pending_magnifier_pos = None
            self._magnifier_pending_hq_pos = None
            self._magnifier_last_viewport_pos = None
            self._magnifier_last_source_image = QImage()
            self._magnifier_last_presented_pos = None
            self._magnifier_label.hide()
            self._restore_magnifier_cursor()

        def wheelEvent(self, event: QWheelEvent) -> None:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    step = 0.18 if delta > 0 else -0.18
                    self._zoom_at(event.position().toPoint(), self.zoomFactor() + step)
                    event.accept()
                    return
            super().wheelEvent(event)
else:
    FitzPdfView = None

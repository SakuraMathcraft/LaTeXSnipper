"""Scroll and zoom the handwriting canvas in viewport coordinates."""

from __future__ import annotations

from typing import NamedTuple

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QScrollArea, QWidget

from .ink_canvas import InkCanvas


class _ZoomAnchor(NamedTuple):
    scene_x: float
    scene_y: float
    viewport_x: int
    viewport_y: int
    zoom: float


class CanvasViewport(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("handwritingCanvasScroll")
        self.setWidgetResizable(False)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.canvas = InkCanvas(self)
        self.setWidget(self.canvas)
        viewport = self.viewport()
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        assert viewport is not None and hbar is not None and vbar is not None
        self._viewport = viewport
        self._hbar = hbar
        self._vbar = vbar
        self._pending_zoom_anchor: _ZoomAnchor | None = None
        self._active_zoom_anchor: _ZoomAnchor | None = None
        self.canvas.panRequested.connect(self._pan)
        self.canvas.installEventFilter(self)
        viewport.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        if (
            isinstance(event, QWheelEvent)
            and (watched is self.canvas or watched is self._viewport)
            and event.type() == QEvent.Type.Wheel
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            pos = event.position().toPoint()
            if watched is self.canvas:
                pos = self.canvas.mapTo(self._viewport, pos)
            self._zoom_at(pos, event.angleDelta().y())
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _zoom_at(self, viewport_pos: QPoint, delta: int) -> None:
        if not delta:
            return
        old_zoom = self.canvas.zoom_factor()
        scene_x = (self._hbar.value() + viewport_pos.x()) / old_zoom
        scene_y = (self._vbar.value() + viewport_pos.y()) / old_zoom
        changed = self.canvas.zoom_in() if delta > 0 else self.canvas.zoom_out()
        if not changed:
            return
        self._pending_zoom_anchor = _ZoomAnchor(
            scene_x,
            scene_y,
            viewport_pos.x(),
            viewport_pos.y(),
            self.canvas.zoom_factor(),
        )
        # Resize events update the scroll ranges after the canvas zoom changes.
        QTimer.singleShot(0, self._apply_pending_zoom_anchor)

    def _apply_pending_zoom_anchor(self) -> None:
        payload = self._pending_zoom_anchor
        self._pending_zoom_anchor = None
        if payload is None:
            return
        scene_x, scene_y, viewport_x, viewport_y, zoom = payload
        if abs(self.canvas.zoom_factor() - zoom) > 1e-06:
            return
        self._active_zoom_anchor = payload
        hbar = self._hbar
        vbar = self._vbar
        target_x = int(round(scene_x * zoom - viewport_x))
        target_y = int(round(scene_y * zoom - viewport_y))
        hbar.setValue(max(hbar.minimum(), min(target_x, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(target_y, vbar.maximum())))
        QTimer.singleShot(0, self._stabilize_zoom_anchor)

    def _stabilize_zoom_anchor(self) -> None:
        payload = self._active_zoom_anchor
        self._active_zoom_anchor = None
        if payload is None:
            return
        scene_x, scene_y, viewport_x, viewport_y, zoom = payload
        if abs(self.canvas.zoom_factor() - zoom) > 1e-06:
            return
        hbar = self._hbar
        vbar = self._vbar
        actual_scene_x = (hbar.value() + viewport_x) / zoom
        actual_scene_y = (vbar.value() + viewport_y) / zoom
        dx = int(round((scene_x - actual_scene_x) * zoom))
        dy = int(round((scene_y - actual_scene_y) * zoom))
        if not dx and (not dy):
            return
        hbar.setValue(max(hbar.minimum(), min(hbar.value() - dx, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(vbar.value() - dy, vbar.maximum())))

    def _pan(self, dx: int, dy: int) -> None:
        hbar = self._hbar
        vbar = self._vbar
        hbar.setValue(max(hbar.minimum(), min(hbar.value() + dx, hbar.maximum())))
        vbar.setValue(max(vbar.minimum(), min(vbar.value() + dy, vbar.maximum())))

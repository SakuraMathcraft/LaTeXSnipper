from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPainterPathStroker


@dataclass
class InkStroke:
    points: List[QPointF] = field(default_factory=list)
    width: float = 3.0
    outline_path: QPainterPath = field(default_factory=QPainterPath)

    @staticmethod
    def smooth_path_from_points(points: List[QPointF]) -> QPainterPath:
        if not points:
            return QPainterPath()
        if len(points) == 1:
            path = QPainterPath(points[0])
            return path
        path = QPainterPath(points[0])
        if len(points) == 2:
            path.lineTo(points[1])
            return path
        for idx in range(1, len(points) - 1):
            current = points[idx]
            next_point = points[idx + 1]
            mid = QPointF((current.x() + next_point.x()) * 0.5, (current.y() + next_point.y()) * 0.5)
            path.quadTo(current, mid)
        path.lineTo(points[-1])
        return path

    @staticmethod
    def stroked_outline(centerline: QPainterPath, width: float) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(1.0, float(width)))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroker.setMiterLimit(2.0)
        return stroker.createStroke(centerline).simplified()

    @classmethod
    def from_points(cls, points: List[QPointF], width: float) -> "InkStroke":
        stroke = cls(points=[QPointF(p) for p in points], width=width)
        stroke.rebuild_geometry()
        return stroke

    @classmethod
    def from_outline(cls, outline_path: QPainterPath, width: float) -> "InkStroke":
        return cls(points=[], width=width, outline_path=QPainterPath(outline_path))

    def rebuild_geometry(self) -> None:
        if not self.points:
            if self.outline_path.isEmpty():
                self.outline_path = QPainterPath()
            return
        centerline = self.smooth_path_from_points(self.points)
        self.outline_path = self.stroked_outline(centerline, self.width)

    def clone(self) -> "InkStroke":
        return InkStroke(
            points=[QPointF(p) for p in self.points],
            width=self.width,
            outline_path=QPainterPath(self.outline_path),
        )

    def bounding_rect(self) -> QRectF:
        if not self.outline_path.isEmpty():
            return self.outline_path.boundingRect()
        if not self.points:
            return QRectF()
        min_x = min(p.x() for p in self.points)
        min_y = min(p.y() for p in self.points)
        max_x = max(p.x() for p in self.points)
        max_y = max(p.y() for p in self.points)
        pad = self.width * 0.5 + 2.0
        return QRectF(min_x - pad, min_y - pad, (max_x - min_x) + pad * 2, (max_y - min_y) + pad * 2)

    def is_empty(self) -> bool:
        return self.outline_path.isEmpty() and not self.points


@dataclass
class CanvasExportResult:
    image: object | None
    bounds: QRectF
    is_empty: bool = False

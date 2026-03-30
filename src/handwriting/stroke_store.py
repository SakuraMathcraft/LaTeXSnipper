from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath

from .types import InkStroke


class StrokeStore:
    def __init__(self) -> None:
        self._strokes: list[InkStroke] = []
        self._undo_stack: list[tuple[str, list[InkStroke]]] = []
        self._redo_stack: list[tuple[str, list[InkStroke]]] = []

    @property
    def strokes(self) -> list[InkStroke]:
        return self._strokes

    def _snapshot(self) -> list[InkStroke]:
        return [stroke.clone() for stroke in self._strokes]

    def _push_undo(self, action: str) -> None:
        self._undo_stack.append((action, self._snapshot()))
        self._redo_stack.clear()

    def add_stroke(self, stroke: InkStroke) -> None:
        if stroke.is_empty():
            return
        self._push_undo("add")
        self._strokes.append(stroke.clone())

    def erase_with_circle(self, center: QPointF, radius: float) -> bool:
        cutter = QPainterPath()
        cutter.addEllipse(center, radius, radius)
        return self._transform_outlines(cutter, action="erase")

    def erase_with_rect(self, rect: QRectF) -> bool:
        cutter = QPainterPath()
        cutter.addRect(rect.normalized())
        return self._transform_outlines(cutter, action="select_erase")

    def erase_with_path(self, path: QPainterPath) -> bool:
        return self._transform_outlines(path, action="select_erase")

    def _transform_outlines(self, cutter: QPainterPath, action: str) -> bool:
        if cutter.isEmpty():
            return False
        new_strokes: list[InkStroke] = []
        changed = False
        for stroke in self._strokes:
            pieces = self._subtract_outline(stroke, cutter)
            if not self._same_stroke_list([stroke], pieces):
                changed = True
            new_strokes.extend(pieces)
        if not changed:
            return False
        self._push_undo(action)
        self._strokes = new_strokes
        return True

    def _same_stroke_list(self, old: list[InkStroke], new: list[InkStroke]) -> bool:
        if len(old) != len(new):
            return False
        return all(self._same_stroke(a, b) for a, b in zip(old, new))

    def _same_stroke(self, a: InkStroke, b: InkStroke) -> bool:
        if abs(a.width - b.width) > 1e-6:
            return False
        pa = a.outline_path
        pb = b.outline_path
        if pa.elementCount() != pb.elementCount():
            return False
        for idx in range(pa.elementCount()):
            ea = pa.elementAt(idx)
            eb = pb.elementAt(idx)
            if ea.type != eb.type:
                return False
            if abs(ea.x - eb.x) > 1e-6 or abs(ea.y - eb.y) > 1e-6:
                return False
        return True

    def _subtract_outline(self, stroke: InkStroke, cutter: QPainterPath) -> list[InkStroke]:
        outline = stroke.outline_path
        if outline.isEmpty():
            return []
        if not outline.intersects(cutter) and not cutter.contains(outline.boundingRect().center()):
            return [stroke.clone()]
        result = outline.subtracted(cutter).simplified()
        if result.isEmpty():
            return []
        pieces = self._split_into_subpaths(result)
        repaired: list[InkStroke] = []
        for piece in pieces:
            piece = self._repair_fragment(piece)
            if self._should_keep_fragment(piece, stroke.width):
                repaired.append(InkStroke.from_outline(piece, stroke.width))
        return repaired

    def _repair_fragment(self, path: QPainterPath) -> QPainterPath:
        polygons = path.toFillPolygons()
        if not polygons:
            return path.simplified()
        repaired = QPainterPath()
        for poly in polygons:
            pts = [QPointF(p) for p in poly]
            if len(pts) < 4:
                continue
            fragment = QPainterPath(pts[0])
            for point in pts[1:]:
                fragment.lineTo(point)
            fragment.closeSubpath()
            repaired = repaired.united(fragment)
        return repaired.simplified() if not repaired.isEmpty() else path.simplified()

    def _should_keep_fragment(self, path: QPainterPath, width: float) -> bool:
        rect = path.boundingRect()
        if rect.isEmpty():
            return False
        area = self._path_area(path)
        perimeter = self._path_perimeter(path)
        min_area = max(width * width * 0.55, 10.0)
        min_perimeter = max(width * 2.4, 12.0)
        min_side = max(width * 0.45, 2.5)
        if area < min_area:
            return False
        if perimeter < min_perimeter:
            return False
        if rect.width() < min_side and rect.height() < min_side:
            return False
        return True

    def _path_area(self, path: QPainterPath) -> float:
        total = 0.0
        for poly in path.toFillPolygons():
            if len(poly) < 3:
                continue
            area = 0.0
            pts = list(poly)
            for idx, p0 in enumerate(pts):
                p1 = pts[(idx + 1) % len(pts)]
                area += p0.x() * p1.y() - p1.x() * p0.y()
            total += abs(area) * 0.5
        return total

    def _path_perimeter(self, path: QPainterPath) -> float:
        total = 0.0
        for poly in path.toFillPolygons():
            if len(poly) < 2:
                continue
            pts = list(poly)
            for idx, p0 in enumerate(pts):
                p1 = pts[(idx + 1) % len(pts)]
                total += math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
        return total

    def _split_into_subpaths(self, path: QPainterPath) -> list[QPainterPath]:
        polygons = path.toFillPolygons()
        pieces: list[QPainterPath] = []
        for poly in polygons:
            pts = [QPointF(p) for p in poly]
            if len(pts) < 3:
                continue
            current = QPainterPath(pts[0])
            for point in pts[1:]:
                current.lineTo(point)
            current.closeSubpath()
            if not current.boundingRect().isEmpty():
                pieces.append(current)
        return pieces or [QPainterPath(path)]

    def clear(self) -> bool:
        if not self._strokes:
            return False
        self._push_undo("clear")
        self._strokes.clear()
        return True

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(("redo", self._snapshot()))
        _, snapshot = self._undo_stack.pop()
        self._strokes = [stroke.clone() for stroke in snapshot]
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(("undo", self._snapshot()))
        _, snapshot = self._redo_stack.pop()
        self._strokes = [stroke.clone() for stroke in snapshot]
        return True

    def content_bounds(self) -> QRectF:
        rect = QRectF()
        for stroke in self._strokes:
            srect = stroke.bounding_rect()
            if srect.isNull() or srect.isEmpty():
                continue
            rect = srect if rect.isNull() or rect.isEmpty() else rect.united(srect)
        return rect

    def is_empty(self) -> bool:
        return not self._strokes

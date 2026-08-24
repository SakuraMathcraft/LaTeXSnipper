"""Geometry and immutable snapshot values for screen capture."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor, QImage, QPixmap

@dataclass(frozen=True)
class ScreenSnapshot:
    geometry: QRect
    image: QImage
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class MagnifierSample:
    preview: QImage
    color: QColor
    global_x: int
    global_y: int


def _rect_to_tuple(rect: QRect) -> tuple[int, int, int, int]:
    return (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))


def _place_popup_near_pointer(
    pointer: QPoint,
    bounds: QRect,
    width: int,
    height: int,
    margin: int,
) -> QRect:
    """Place a popup below-right of the pointer, flipping only at screen edges."""
    x = int(pointer.x()) + margin
    y = int(pointer.y()) + margin
    if x + width - 1 > bounds.right():
        x = int(pointer.x()) - margin - width
    if y + height - 1 > bounds.bottom():
        y = int(pointer.y()) - margin - height

    max_x = bounds.right() - width + 1
    max_y = bounds.bottom() - height + 1
    x = bounds.left() if max_x < bounds.left() else max(bounds.left(), min(x, max_x))
    y = bounds.top() if max_y < bounds.top() else max(bounds.top(), min(y, max_y))
    return QRect(x, y, width, height)


def choose_screen_index(
    release_global_xy: tuple[int, int],
    screen_geometries: list[tuple[int, int, int, int]],
    mode: str = "auto",
    preferred_index: int | None = None,
) -> int:
    """Choose target screen index using release position or preferred index."""
    if not screen_geometries:
        return -1

    m = (mode or "auto").strip().lower()
    if m == "index" and preferred_index is not None and 0 <= int(preferred_index) < len(screen_geometries):
        return int(preferred_index)

    x, y = int(release_global_xy[0]), int(release_global_xy[1])
    for i, (sx, sy, sw, sh) in enumerate(screen_geometries):
        if sw <= 0 or sh <= 0:
            continue
        if sx <= x < (sx + sw) and sy <= y < (sy + sh):
            return i

    return 0


def map_global_rect_to_screen_capture(
    global_rect: tuple[int, int, int, int],
    screen_geometry: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Map global logical rect to target screen local rect.

    QScreen.grabWindow expects screen-local logical coordinates. Multiplying by
    devicePixelRatio again causes the captured area to drift on HiDPI displays.
    """
    gx, gy, gw, gh = [int(v) for v in global_rect]
    sx, sy, sw, sh = [int(v) for v in screen_geometry]
    if gw <= 0 or gh <= 0 or sw <= 0 or sh <= 0:
        return None

    ix1 = max(gx, sx)
    iy1 = max(gy, sy)
    ix2 = min(gx + gw, sx + sw)
    iy2 = min(gy + gh, sy + sh)
    iw = ix2 - ix1
    ih = iy2 - iy1
    if iw <= 0 or ih <= 0:
        return None

    local_logical = (ix1 - sx, iy1 - sy, iw, ih)
    logical_capture = (
        int(local_logical[0]),
        int(local_logical[1]),
        max(1, int(local_logical[2])),
        max(1, int(local_logical[3])),
    )
    return local_logical, logical_capture


def crop_screen_snapshot(
    snapshot: ScreenSnapshot,
    local_logical_rect: tuple[int, int, int, int],
) -> QPixmap:
    """Crop a pre-overlay screen snapshot using screen-local logical coordinates."""
    lx, ly, lw, lh = [int(v) for v in local_logical_rect]
    image = snapshot.image
    if image.isNull() or lw <= 0 or lh <= 0:
        return QPixmap()

    x1 = int(math.floor(lx * snapshot.scale_x))
    y1 = int(math.floor(ly * snapshot.scale_y))
    x2 = int(math.ceil((lx + lw) * snapshot.scale_x))
    y2 = int(math.ceil((ly + lh) * snapshot.scale_y))

    x1 = max(0, min(x1, image.width()))
    y1 = max(0, min(y1, image.height()))
    x2 = max(x1, min(x2, image.width()))
    y2 = max(y1, min(y2, image.height()))
    if x2 <= x1 or y2 <= y1:
        return QPixmap()

    cropped = image.copy(x1, y1, x2 - x1, y2 - y1)
    pixmap = QPixmap.fromImage(cropped)
    pixmap.setDevicePixelRatio(max(1.0, float(snapshot.scale_x)))
    return pixmap

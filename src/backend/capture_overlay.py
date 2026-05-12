# backend/capture_overlay.py
import math
import os
import time
from dataclasses import dataclass

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QGuiApplication,
    QFont,
    QFontMetrics,
    QCursor,
    QImage,
    QPixmap,
    QRegion,
)

from cross_platform.screenshot_tools import (
    capture_region_with_tools,
    is_image_effectively_black,
    is_wayland,
    wayland_overlay_background,
)

_CROSSHAIR_ARM = 9
_CROSSHAIR_OUTER_WIDTH = 3
_MAGNIFIER_SOURCE_WIDTH = 28
_MAGNIFIER_SOURCE_HEIGHT = 18
_MAGNIFIER_ZOOM = 7
_MAGNIFIER_PREVIEW_WIDTH = _MAGNIFIER_SOURCE_WIDTH * _MAGNIFIER_ZOOM
_MAGNIFIER_PREVIEW_HEIGHT = _MAGNIFIER_SOURCE_HEIGHT * _MAGNIFIER_ZOOM
_MAGNIFIER_PANEL_HEIGHT = 78
_MAGNIFIER_MARGIN = 14
_COPY_NOTICE_SECONDS = 1.2
_MAGNIFIER_GUIDE_WIDTH = 2


@dataclass(frozen=True)
class _ScreenSnapshot:
    geometry: QRect
    image: QImage
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class _MagnifierSample:
    preview: QImage
    color: QColor
    global_x: int
    global_y: int


def _rect_to_tuple(rect: QRect) -> tuple[int, int, int, int]:
    return (int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))


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
    snapshot: _ScreenSnapshot,
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


class ScreenCaptureOverlay(QWidget):
    selection_done = pyqtSignal(object)  # Emits QPixmap or None.

    def __init__(
        self,
        capture_display_mode: str = "auto",
        preferred_screen_index: int | None = None,
        screenshot_tool: str | None = None,
    ):
        super().__init__()
        self.start_pos = None
        self.end_pos = None
        self.current_pos = None
        self.start_global_pos = None
        self.end_global_pos = None
        self.current_global_pos = None
        self.last_capture_failure_message = ""
        self.last_capture_screen_index = None
        self.capture_display_mode = (capture_display_mode or "auto").strip().lower()
        if self.capture_display_mode not in ("auto", "index"):
            self.capture_display_mode = "auto"
        self.preferred_screen_index = preferred_screen_index
        self.screenshot_tool = (screenshot_tool or "").strip() or None
        if self.screenshot_tool:
            print(f"[Overlay] 用户指定截图工具: {self.screenshot_tool}")
        self.color_display_mode = "rgb"
        self._cursor_override_active = False
        self._finished = False
        self._copy_notice_until = 0.0
        self._screen_snapshots: list[_ScreenSnapshot] = []
        self._copy_notice_timer = QTimer(self)
        self._copy_notice_timer.setSingleShot(True)
        self._copy_notice_timer.timeout.connect(self.update)
        self._clear_blank_override_cursors()
        self._screen_snapshots = self._capture_screen_snapshots()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle("Screen Capture Overlay")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Cover all screens (virtual desktop union)
        screens = QGuiApplication.screens()
        union_rect = None
        for s in screens:
            g = s.geometry()
            union_rect = g if union_rect is None else union_rect.united(g)
        if union_rect is None:
            screen = QGuiApplication.primaryScreen()
            union_rect = screen.geometry() if screen else QRect(0, 0, 1, 1)
        self.setGeometry(union_rect)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.BlankCursor))

    def _selection_rect(self) -> QRect | None:
        if not self.start_pos or not self.end_pos:
            return None
        return QRect(self.start_pos, self.end_pos).normalized()

    def _selection_size(self) -> tuple[int, int]:
        if self.start_global_pos and self.end_global_pos:
            width = abs(int(self.end_global_pos.x() - self.start_global_pos.x()))
            height = abs(int(self.end_global_pos.y() - self.start_global_pos.y()))
            return (width, height)
        if not self.start_pos or not self.end_pos:
            return (0, 0)
        width = abs(int(self.end_pos.x() - self.start_pos.x()))
        height = abs(int(self.end_pos.y() - self.start_pos.y()))
        return (width, height)

    def _capture_screen_snapshots(self) -> list[_ScreenSnapshot]:
        snapshots: list[_ScreenSnapshot] = []

        if is_wayland():
            wayland_bg = wayland_overlay_background()
            if wayland_bg is not None and not wayland_bg.isNull():
                for screen in QGuiApplication.screens():
                    geo = QRect(screen.geometry())
                    if geo.width() <= 0 or geo.height() <= 0:
                        continue
                    snapshots.append(
                        _ScreenSnapshot(
                            geometry=geo,
                            image=wayland_bg,
                            scale_x=float(wayland_bg.width()) / max(1, int(geo.width())),
                            scale_y=float(wayland_bg.height()) / max(1, int(geo.height())),
                        )
                    )
                print("[Overlay] Wayland: overlay 背景截图成功")
                return snapshots
            print("[Overlay] Wayland: 所有 overlay 背景截图方式均失败")
            print("[Overlay] 提示：建议安装 grim、gnome-screenshot 或 flameshot 以在 Wayland 上正常显示截图遮罩。")

        for i, screen in enumerate(QGuiApplication.screens()):
            try:
                geo = QRect(screen.geometry())
                if geo.width() <= 0 or geo.height() <= 0:
                    continue
                pixmap = screen.grabWindow(0, 0, 0, geo.width(), geo.height())
                image = pixmap.toImage().copy()
                if image.isNull():
                    print(f"[Overlay] 屏幕 {i} grabWindow(0) 返回空图像")
                    continue
                snapshots.append(
                    _ScreenSnapshot(
                        geometry=geo,
                        image=image,
                        scale_x=float(image.width()) / max(1, int(geo.width())),
                        scale_y=float(image.height()) / max(1, int(geo.height())),
                    )
                )
            except Exception as e:
                print(f"[Overlay] 屏幕 {i} 截图异常: {e}")
                continue

        if not snapshots:
            print("[Overlay] 警告：未能捕获任何屏幕快照，overlay 背景将为纯色遮罩")

        return snapshots

    def _snapshot_for_screen_index(self, screen_index: int) -> _ScreenSnapshot | None:
        screens = QGuiApplication.screens()
        if screen_index < 0 or screen_index >= len(screens):
            return None
        target_geo = QRect(screens[screen_index].geometry())
        for snapshot in self._screen_snapshots:
            if snapshot.geometry == target_geo:
                return snapshot
        return None

    def _update_cursor_position_from_global(self, global_pos: QPoint) -> None:
        self.current_global_pos = global_pos
        self.current_pos = self.mapFromGlobal(global_pos)

    @staticmethod
    def _clear_blank_override_cursors() -> None:
        """Clear stale global blank cursors left by interrupted overlays."""
        try:
            for _ in range(8):
                cursor = QGuiApplication.overrideCursor()
                if cursor is None or cursor.shape() != Qt.CursorShape.BlankCursor:
                    break
                QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

    def _hide_system_cursor(self) -> None:
        try:
            self._clear_blank_override_cursors()
            self.setCursor(QCursor(Qt.CursorShape.BlankCursor))
            if not self._cursor_override_active:
                QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))
                self._cursor_override_active = True
        except Exception:
            pass

    def _restore_system_cursor(self) -> None:
        try:
            if self._cursor_override_active:
                QGuiApplication.restoreOverrideCursor()
                self._cursor_override_active = False
            self.unsetCursor()
            self._clear_blank_override_cursors()
        except Exception:
            pass

    def _finish_capture(self, pixmap) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._restore_system_cursor()
        self.selection_done.emit(pixmap)

    def cancel_capture(self) -> None:
        self.start_pos = None
        self.end_pos = None
        self.current_pos = None
        self.start_global_pos = None
        self.end_global_pos = None
        self.current_global_pos = None
        self._finish_capture(None)
        self.close()

    def _snapshot_at_global_pos(self, global_pos: QPoint | None) -> _ScreenSnapshot | None:
        if global_pos is None:
            return None
        gx = int(global_pos.x())
        gy = int(global_pos.y())
        for snapshot in self._screen_snapshots:
            geo = snapshot.geometry
            if geo.x() <= gx < geo.x() + geo.width() and geo.y() <= gy < geo.y() + geo.height():
                return snapshot
        return None

    def _image_xy_for_global_pos(self, snapshot: _ScreenSnapshot, global_pos: QPoint) -> tuple[int, int]:
        geo = snapshot.geometry
        image = snapshot.image
        local_x = max(0, int(global_pos.x()) - int(geo.x()))
        local_y = max(0, int(global_pos.y()) - int(geo.y()))
        image_x = int(local_x * snapshot.scale_x)
        image_y = int(local_y * snapshot.scale_y)
        image_x = max(0, min(image_x, image.width() - 1))
        image_y = max(0, min(image_y, image.height() - 1))
        return (image_x, image_y)

    def _sample_color_at_current_pos(self) -> QColor | None:
        snapshot = self._snapshot_at_global_pos(self.current_global_pos)
        if snapshot is None or self.current_global_pos is None:
            return None
        image_x, image_y = self._image_xy_for_global_pos(snapshot, self.current_global_pos)
        return QColor(snapshot.image.pixelColor(image_x, image_y))

    def _format_color_value(self, color: QColor) -> str:
        if self.color_display_mode == "hex":
            return f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
        return f"{color.red()}, {color.green()}, {color.blue()}"

    def _copy_current_color_value(self) -> None:
        color = self._sample_color_at_current_pos()
        if color is None:
            return
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._format_color_value(color))
                self._copy_notice_until = time.monotonic() + _COPY_NOTICE_SECONDS
                self._copy_notice_timer.start(int(_COPY_NOTICE_SECONDS * 1000))
        except Exception:
            pass
        self.update()

    def _build_magnifier_sample(self) -> _MagnifierSample | None:
        if self.current_global_pos is None:
            return None
        snapshot = self._snapshot_at_global_pos(self.current_global_pos)
        if snapshot is None:
            return None

        image = snapshot.image
        image_x, image_y = self._image_xy_for_global_pos(snapshot, self.current_global_pos)
        radius_x = _MAGNIFIER_SOURCE_WIDTH // 2
        radius_y = _MAGNIFIER_SOURCE_HEIGHT // 2
        source_rect = QRect(
            image_x - radius_x,
            image_y - radius_y,
            _MAGNIFIER_SOURCE_WIDTH,
            _MAGNIFIER_SOURCE_HEIGHT,
        )
        sample = QImage(_MAGNIFIER_SOURCE_WIDTH, _MAGNIFIER_SOURCE_HEIGHT, QImage.Format.Format_RGB32)
        sample.fill(QColor(255, 255, 255))
        for target_y in range(_MAGNIFIER_SOURCE_HEIGHT):
            source_y = source_rect.top() + target_y
            if not (0 <= source_y < image.height()):
                continue
            for target_x in range(_MAGNIFIER_SOURCE_WIDTH):
                source_x = source_rect.left() + target_x
                if not (0 <= source_x < image.width()):
                    continue
                sample.setPixelColor(target_x, target_y, image.pixelColor(source_x, source_y))

        preview = sample.scaled(
            _MAGNIFIER_PREVIEW_WIDTH,
            _MAGNIFIER_PREVIEW_HEIGHT,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        return _MagnifierSample(
            preview=preview,
            color=QColor(image.pixelColor(image_x, image_y)),
            global_x=int(self.current_global_pos.x()),
            global_y=int(self.current_global_pos.y()),
        )

    def _popup_screen_bounds(self) -> QRect:
        snapshot = self._snapshot_at_global_pos(self.current_global_pos)
        if snapshot is None:
            return QRect(self.rect())
        overlay_geo = self.geometry()
        geo = snapshot.geometry
        return QRect(
            int(geo.x() - overlay_geo.x()),
            int(geo.y() - overlay_geo.y()),
            int(geo.width()),
            int(geo.height()),
        )

    def _rect_contains_rect(self, bounds: QRect, rect: QRect) -> bool:
        return (
            rect.left() >= bounds.left()
            and rect.top() >= bounds.top()
            and rect.right() <= bounds.right()
            and rect.bottom() <= bounds.bottom()
        )

    def _magnifier_popup_rect(self) -> QRect | None:
        if self.current_pos is None:
            return None
        width = _MAGNIFIER_PREVIEW_WIDTH
        height = _MAGNIFIER_PREVIEW_HEIGHT + _MAGNIFIER_PANEL_HEIGHT
        bounds = self._popup_screen_bounds()
        cx = int(self.current_pos.x())
        cy = int(self.current_pos.y())

        h_order = ("right", "left") if bounds.right() - cx >= cx - bounds.left() else ("left", "right")
        v_order = ("bottom", "top") if bounds.bottom() - cy >= cy - bounds.top() else ("top", "bottom")
        order = (
            (h_order[0], v_order[0]),
            (h_order[0], v_order[1]),
            (h_order[1], v_order[0]),
            (h_order[1], v_order[1]),
        )

        candidates = []
        for horizontal, vertical in order:
            x = cx + _MAGNIFIER_MARGIN if horizontal == "right" else cx - _MAGNIFIER_MARGIN - width
            y = cy + _MAGNIFIER_MARGIN if vertical == "bottom" else cy - _MAGNIFIER_MARGIN - height
            candidates.append(QRect(x, y, width, height))

        selection = self._selection_rect()
        avoid_rect = None
        if selection is not None and (selection.width() > 1 or selection.height() > 1):
            avoid_rect = selection.adjusted(-6, -6, 6, 6)

        contained = [rect for rect in candidates if self._rect_contains_rect(bounds, rect)]
        if avoid_rect is not None:
            for rect in contained:
                if not rect.intersects(avoid_rect):
                    return rect
        if contained:
            return contained[0]

        fallback = QRect(candidates[0])
        max_x = bounds.right() - width + 1
        max_y = bounds.bottom() - height + 1
        if max_x >= bounds.left():
            fallback.moveLeft(max(bounds.left(), min(fallback.left(), max_x)))
        else:
            fallback.moveLeft(bounds.left())
        if max_y >= bounds.top():
            fallback.moveTop(max(bounds.top(), min(fallback.top(), max_y)))
        else:
            fallback.moveTop(bounds.top())
        return fallback

    def _draw_shadowed_text(
        self,
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

    def _draw_crosshair(self, painter: QPainter) -> None:
        if self.current_pos is None:
            return
        cx, cy = self.current_pos.x(), self.current_pos.y()
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

    def _draw_magnifier(self, painter: QPainter) -> None:
        sample = self._build_magnifier_sample()
        popup_rect = self._magnifier_popup_rect()
        if sample is None or popup_rect is None:
            return

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
        guide_pen = QPen(QColor(122, 190, 255, 190), _MAGNIFIER_GUIDE_WIDTH)
        guide_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(guide_pen)
        painter.drawLine(preview_rect.left() + 1, center_y, preview_rect.right() - 1, center_y)
        painter.drawLine(center_x, preview_rect.top() + 1, center_x, preview_rect.bottom() - 1)
        painter.restore()
        painter.setPen(QPen(QColor(0, 0, 0, 210), 1))
        painter.drawRect(pixel_rect.adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor(35, 35, 35, 180), 1))
        painter.drawRect(preview_rect.adjusted(0, 0, -1, -1))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(28, 28, 28, 168))
        painter.drawRect(panel_rect)

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_color = QColor(255, 255, 255, 242)

        coord_rect = QRect(panel_rect.left() + 8, panel_rect.top() + 4, panel_rect.width() - 16, 16)
        self._draw_shadowed_text(
            painter,
            coord_rect,
            Qt.AlignmentFlag.AlignCenter,
            f"({sample.global_x}, {sample.global_y})",
            text_color,
        )

        mode_label = "HEX" if self.color_display_mode == "hex" else "RGB"
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
        self._draw_shadowed_text(
            painter,
            QRect(swatch_rect.right() + 7, value_y - 1, panel_rect.width(), 18),
            Qt.AlignmentFlag.AlignVCenter,
            value_text,
            text_color,
        )

        copy_hint = "已复制" if time.monotonic() < self._copy_notice_until else "按 C 复制色值"
        self._draw_shadowed_text(
            painter,
            QRect(panel_rect.left() + 8, panel_rect.top() + 46, panel_rect.width() - 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            copy_hint,
            QColor(255, 255, 255, 232),
        )
        self._draw_shadowed_text(
            painter,
            QRect(panel_rect.left() + 8, panel_rect.top() + 61, panel_rect.width() - 16, 16),
            Qt.AlignmentFlag.AlignCenter,
            "按 Shift 切换 RGB/HEX",
            QColor(255, 255, 255, 232),
        )
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        _has_valid_snapshots = self._screen_snapshots and any(
            not snap.image.isNull() and not is_image_effectively_black(snap.image)
            for snap in self._screen_snapshots
        )
        if is_wayland() and _has_valid_snapshots:
            # Use the pre-captured screenshot as the visible desktop background.
            for snap in self._screen_snapshots:
                if not snap.image.isNull():
                    target_rect = QRect(
                        snap.geometry.x() - self.geometry().x(),
                        snap.geometry.y() - self.geometry().y(),
                        snap.geometry.width(),
                        snap.geometry.height(),
                    )
                    painter.drawImage(target_rect, snap.image)
            # Draw the translucent overlay mask.
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 125))

        rect = self._selection_rect()

        # Keep the selected area clear while dimming the rest of the desktop.
        if rect:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.restore()

        # Draw a visible crosshair over both bright and dark backgrounds.
        self._draw_crosshair(painter)

        if rect:
            pen = QPen(QColor(0, 170, 255), 2)
            painter.save()
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            popup_rect = self._magnifier_popup_rect()
            if popup_rect is not None:
                avoid_region = QRegion(popup_rect.adjusted(-3, -3, 3, 3))
                draw_region = QRegion(self.rect()).subtracted(avoid_region)
                painter.setClipRegion(draw_region)

            painter.drawRect(rect)
            painter.restore()

            # Show logical selection size and global top-left coordinates.
            width, height = self._selection_size()
            if width > 0 and height > 0:
                if self.start_global_pos and self.end_global_pos:
                    gx = min(int(self.start_global_pos.x()), int(self.end_global_pos.x()))
                    gy = min(int(self.start_global_pos.y()), int(self.end_global_pos.y()))
                else:
                    gx = int(self.geometry().x() + rect.left())
                    gy = int(self.geometry().y() + rect.top())
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
                max_x = max(2, self.width() - label_w - 2)
                label_x = max(2, min(label_x, max_x))
                max_y = max(2, self.height() - label_h - 2)
                label_y = max(2, min(label_y, max_y))

                label_rect = QRect(label_x, label_y, label_w, label_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 150, 230, 218))
                painter.drawRoundedRect(label_rect, 3, 3)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

        self._draw_magnifier(painter)

    def mousePressEvent(self, event):
        self.current_pos = event.position().toPoint()
        self.current_global_pos = event.globalPosition().toPoint()
        self.start_pos = self.current_pos
        self.end_pos = self.start_pos
        self.start_global_pos = self.current_global_pos
        self.end_global_pos = self.start_global_pos
        self.update()

    def mouseMoveEvent(self, event):
        self.current_pos = event.position().toPoint()
        self.current_global_pos = event.globalPosition().toPoint()
        if self.start_pos:
            self.end_pos = self.current_pos
            self.end_global_pos = self.current_global_pos
        self.update()

    def mouseReleaseEvent(self, event):
        self.current_pos = event.position().toPoint()
        self.current_global_pos = event.globalPosition().toPoint()
        self.end_pos = self.current_pos
        self.end_global_pos = self.current_global_pos
        self.update()
        self.capture_selection()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C:
            if not event.isAutoRepeat():
                self._copy_current_color_value()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Shift:
            if not event.isAutoRepeat():
                self.color_display_mode = "hex" if self.color_display_mode == "rgb" else "rgb"
                self.update()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._update_cursor_position_from_global(QCursor.pos())
            self._hide_system_cursor()
            self.activateWindow()
            self.raise_()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            self.grabKeyboard()
            self.update()
        except Exception:
            pass

    def hideEvent(self, event):
        self._restore_system_cursor()
        super().hideEvent(event)

    def closeEvent(self, event):
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._restore_system_cursor()
        super().closeEvent(event)

    def _screen_label(self, index: int, screens) -> str:
        if 0 <= int(index) < len(screens):
            try:
                name = str(screens[index].name() or "").strip()
            except Exception:
                name = ""
            if name:
                return f"屏幕 {int(index) + 1}（{name}）"
        return f"屏幕 {int(index) + 1}"

    def _build_screen_mismatch_message(self, target_idx: int, actual_idx: int, screens) -> str:
        target = self._screen_label(target_idx, screens)
        actual = self._screen_label(actual_idx, screens)
        return (
            f"当前截图模式固定为{target}，但你框选的是{actual}。"
            f"请在托盘菜单选择“截图屏幕模式 > {actual}”，"
            "或切换为“自动（按鼠标释放点）”后再截图。"
        )

    def capture_selection(self):
        self.last_capture_failure_message = ""
        self.last_capture_screen_index = None
        if not self.start_pos or not self.end_pos:
            self._finish_capture(None)
            return
        rect = self._selection_rect()
        if rect is None:
            self._finish_capture(None)
            return

        if self.start_global_pos and self.end_global_pos:
            global_x = min(int(self.start_global_pos.x()), int(self.end_global_pos.x()))
            global_y = min(int(self.start_global_pos.y()), int(self.end_global_pos.y()))
            width = abs(int(self.end_global_pos.x() - self.start_global_pos.x()))
            height = abs(int(self.end_global_pos.y() - self.start_global_pos.y()))
            global_release_x = int((self.current_global_pos or self.end_global_pos).x())
            global_release_y = int((self.current_global_pos or self.end_global_pos).y())
        else:
            x1, y1 = int(rect.left()), int(rect.top())
            width, height = self._selection_size()
            overlay_geo = self.geometry()
            global_x = int(overlay_geo.x() + x1)
            global_y = int(overlay_geo.y() + y1)
            global_release_x = int(overlay_geo.x() + self.current_pos.x())
            global_release_y = int(overlay_geo.y() + self.current_pos.y())

        if width <= 0 or height <= 0:
            self._finish_capture(None)
            return

        screens = QGuiApplication.screens()
        screen_geos = [_rect_to_tuple(s.geometry()) for s in screens]
        actual_idx = choose_screen_index(
            (global_release_x, global_release_y),
            screen_geos,
            mode="auto",
        )
        target_idx = choose_screen_index(
            (global_release_x, global_release_y),
            screen_geos,
            mode=self.capture_display_mode,
            preferred_index=self.preferred_screen_index,
        )

        if target_idx < 0 or target_idx >= len(screens):
            screen = QGuiApplication.primaryScreen()
            target_idx = 0
        else:
            screen = screens[target_idx]

        if screen is None:
            self._finish_capture(None)
            return

        mapped = map_global_rect_to_screen_capture(
            (global_x, global_y, width, height),
            _rect_to_tuple(screen.geometry()),
        )
        if mapped is None:
            if self.capture_display_mode == "index" and actual_idx != target_idx and 0 <= actual_idx < len(screens):
                self.last_capture_failure_message = self._build_screen_mismatch_message(target_idx, actual_idx, screens)
            self._finish_capture(None)
            return

        logical_rect, native_rect = mapped
        snapshot = self._snapshot_for_screen_index(int(target_idx))
        pixmap = crop_screen_snapshot(snapshot, logical_rect) if snapshot is not None else QPixmap()

        _is_wayland = is_wayland()

        # Wayland: grabWindow(0) can return an all-black snapshot; the crop is also black but .isNull() is False,
        # which blocks CLI/portal fallback. Explicitly detect all-black pixels and discard them.
        if _is_wayland and not pixmap.isNull() and is_image_effectively_black(pixmap.toImage()):
            print("[Overlay] Wayland: 预截图裁剪结果为全黑（grabWindow 无效），跳过并尝试 CLI/portal")
            pixmap = QPixmap()

        if pixmap.isNull():
            print("[Overlay] 预截图裁剪失败，尝试其他方式...")

        if pixmap.isNull() and _is_wayland:
            image, source = capture_region_with_tools(
                global_x,
                global_y,
                width,
                height,
                preferred_tool=self.screenshot_tool,
                screen_geometry=_rect_to_tuple(screen.geometry()),
            )
            if image is not None and not image.isNull():
                pixmap = QPixmap.fromImage(image)
                print(f"[Overlay] Wayland: 使用 {source} 截图")
            else:
                print("[Overlay] Wayland CLI/portal 截图均失败")

        # X11 or non-Wayland: traditional grabWindow fallback.
        if pixmap.isNull() and not _is_wayland:
            nx, ny, nw, nh = native_rect
            if os.name != "nt":
                try:
                    self.hide()
                    QGuiApplication.processEvents()
                    time.sleep(0.05)
                except Exception:
                    pass
            try:
                pixmap = screen.grabWindow(0, nx, ny, nw, nh)
                if not pixmap.isNull():
                    pass
                else:
                    print("[Overlay] grabWindow(0)（隐藏overlay后）返回空")
            finally:
                if os.name != "nt":
                    try:
                        self.show()
                    except Exception:
                        pass

        # Generic X11 CLI fallback.
        if pixmap.isNull() and not _is_wayland and os.name != "nt":
            image, source = capture_region_with_tools(
                global_x,
                global_y,
                width,
                height,
                preferred_tool=self.screenshot_tool,
            )
            if image is not None and not image.isNull():
                pixmap = QPixmap.fromImage(image)
                print(f"[Overlay] Linux: 使用 {source} 截图")
            else:
                print("[Overlay] Linux CLI 截图也失败")

        if pixmap.isNull():
            print("[Overlay] 所有截图方式均失败！pixmap 为空")
        self.last_capture_screen_index = int(target_idx)
        print(f"[Overlay] Captured pixmap size: {pixmap.width()}x{pixmap.height()} screen={target_idx} dpr={screen.devicePixelRatio():.2f}")

        self._finish_capture(pixmap)

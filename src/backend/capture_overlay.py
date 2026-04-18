# backend/capture_overlay.py
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication, QFont, QFontMetrics


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
    dpr: float,
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

class ScreenCaptureOverlay(QWidget):
    selection_done = pyqtSignal(object)  # Emits QPixmap or None.

    def __init__(
        self,
        capture_display_mode: str = "auto",
        preferred_screen_index: int | None = None,
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 95))
        rect = self._selection_rect()

        # Keep the selected area clear while dimming the rest of the desktop.
        if rect:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.restore()

        # Draw a visible crosshair over both bright and dark backgrounds.
        if self.current_pos:
            # 双层准星：外黑内白，兼顾深/浅背景可见性
            arm = 12
            cx, cy = self.current_pos.x(), self.current_pos.y()
            painter.setPen(QPen(QColor(0, 0, 0, 220), 3))
            painter.drawLine(cx - arm, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy + arm)
            painter.setPen(QPen(QColor(255, 255, 255, 235), 1))
            painter.drawLine(cx - arm, cy, cx + arm, cy)
            painter.drawLine(cx, cy - arm, cx, cy + arm)

        if rect:
            pen = QPen(QColor(0, 170, 255), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

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
                font = QFont("Segoe UI", 10)
                painter.setFont(font)
                fm = QFontMetrics(font)

                label_padding_x = 8
                label_h = fm.height() + 6
                label_w = fm.horizontalAdvance(text) + label_padding_x * 2

                label_x = rect.left()
                label_y = rect.top() - label_h - 6
                if label_y < 2:
                    label_y = rect.top() + 6
                max_x = max(2, self.width() - label_w - 2)
                label_x = max(2, min(label_x, max_x))
                max_y = max(2, self.height() - label_h - 2)
                label_y = max(2, min(label_y, max_y))

                label_rect = QRect(label_x, label_y, label_w, label_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 170, 255, 230))
                painter.drawRoundedRect(label_rect, 4, 4)

                painter.setPen(QColor(255, 255, 255))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)

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
        if event.key() == Qt.Key.Key_Escape:
            self.start_pos = None
            self.end_pos = None
            self.current_pos = None
            self.start_global_pos = None
            self.end_global_pos = None
            self.current_global_pos = None
            try:
                self.releaseKeyboard()
            except Exception:
                pass
            self.selection_done.emit(None)
            self.close()
            return
        super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self.activateWindow()
            self.raise_()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            self.grabKeyboard()
        except Exception:
            pass

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
            self.selection_done.emit(None)
            return
        rect = self._selection_rect()
        if rect is None:
            self.selection_done.emit(None)
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
            self.selection_done.emit(None)
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
            self.selection_done.emit(None)
            return

        mapped = map_global_rect_to_screen_capture(
            (global_x, global_y, width, height),
            _rect_to_tuple(screen.geometry()),
            float(screen.devicePixelRatio() or 1.0),
        )
        if mapped is None:
            if self.capture_display_mode == "index" and actual_idx != target_idx and 0 <= actual_idx < len(screens):
                self.last_capture_failure_message = self._build_screen_mismatch_message(target_idx, actual_idx, screens)
            self.selection_done.emit(None)
            return

        _logical_rect, native_rect = mapped
        nx, ny, nw, nh = native_rect
        pixmap = screen.grabWindow(0, nx, ny, nw, nh)
        self.last_capture_screen_index = int(target_idx)
        print(f"[Overlay] Captured pixmap size: {pixmap.width()}x{pixmap.height()} screen={target_idx} dpr={screen.devicePixelRatio():.2f}")

        self.selection_done.emit(pixmap)


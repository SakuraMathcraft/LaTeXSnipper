"""Cross-platform screen capture overlay."""

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import NamedTuple, cast

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QCloseEvent,
    QColor,
    QCursor,
    QGuiApplication,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QRegion,
    QScreen,
    QShowEvent,
)
from PyQt6.QtWidgets import QWidget

from capture.backends import capture_screen_snapshots, is_wayland
from capture.geometry import (
    ScreenSnapshot,
    _rect_to_tuple,
    choose_screen_index,
    crop_screen_snapshot,
    map_global_rect_to_screen_capture,
)
from capture.magnifier import CaptureMagnifier, magnifier_popup_rect
from capture.overlay_paint import (
    cursor_region,
    draw_crosshair,
    draw_selection,
    selection_edge_region,
)
from localization.manager import translate as tr

logger = logging.getLogger(f"latexsnipper.{__name__}")


_NS_WINDOW_STYLE_MASK_NONACTIVATING_PANEL = 1 << 7


def _capture_window_flags() -> Qt.WindowType:
    """Keep the capture surface out of task switchers as a transient tool."""
    return (
        Qt.WindowType.Tool
        | Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
    )


def macos_make_nonactivating_panel(widget: QWidget) -> bool:
    """Mark the native macOS panel so showing it never activates the application.

    A Qt.Tool window is an NSPanel on macOS. Adding the non-activating style
    mask lets the panel become key and receive mouse and keyboard input while
    the owning application stays in the background, which is what a global
    screenshot hotkey needs: the capture surface must appear without pulling
    the main window forward.

    An NSPanel also hides whenever its application is inactive. A
    non-activating panel keeps the application inactive, so the panel must
    stop hiding on deactivation or it is never drawn on screen.
    """
    if sys.platform != "darwin":
        return False
    # winId is an NSView only on the cocoa platform plugin; messaging the
    # handle another plugin returns (offscreen, minimal) crashes the process.
    if QGuiApplication.platformName() != "cocoa":
        return False
    try:
        import ctypes
        import ctypes.util

        library = ctypes.util.find_library("objc")
        if not library:
            return False
        objc = ctypes.CDLL(library)

        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.object_getClassName.restype = ctypes.c_char_p
        objc.object_getClassName.argtypes = [ctypes.c_void_p]

        def selector(name: bytes) -> int:
            return int(objc.sel_registerName(name) or 0)

        # objc_msgSend has no fixed signature; give each call shape its own
        # prototype instead of mutating the shared function pointer.
        address = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        if not address:
            return False
        send = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
            address
        )
        send_mask = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong
        )(address)
        send_bool = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool
        )(address)

        view = int(widget.winId())
        if not view:
            return False
        window = int(send(view, selector(b"window")) or 0)
        if not window:
            return False
        class_name = (objc.object_getClassName(window) or b"").decode(
            "ascii", "replace"
        )
        send_bool(window, selector(b"setHidesOnDeactivate:"), False)
        mask = int(send(window, selector(b"styleMask")) or 0)
        target = mask | _NS_WINDOW_STYLE_MASK_NONACTIVATING_PANEL
        if target == mask:
            return True
        send_mask(window, selector(b"setStyleMask:"), target)
        logger.debug(
            "macOS 截图面板设为非激活样式: class=%s mask=%s", class_name, target
        )
        return True
    except Exception:
        logger.debug("macOS 非激活面板设置失败", exc_info=True)
        return False


class _PointerPosition(NamedTuple):
    local: QPoint
    global_pos: QPoint


@dataclass(slots=True)
class _DragSelection:
    start: _PointerPosition
    end: _PointerPosition

    def local_rect(self) -> QRect:
        return QRect(self.start.local, self.end.local).normalized()

    def global_extent(self) -> tuple[int, int, int, int]:
        """Return the logical drag extent, excluding the painted border pixel."""
        start = self.start.global_pos
        end = self.end.global_pos
        return (
            min(start.x(), end.x()),
            min(start.y(), end.y()),
            abs(end.x() - start.x()),
            abs(end.y() - start.y()),
        )


class ScreenCaptureOverlay(QWidget):
    macos_permission_preflight_state: str = "unknown"
    selection_done = pyqtSignal(object)  # Emits QPixmap or None.

    def __init__(
        self,
        capture_display_mode: str = "auto",
        preferred_screen_index: int | None = None,
    ) -> None:
        super().__init__()
        self._pointer: _PointerPosition | None = None
        self._selection: _DragSelection | None = None
        self.last_capture_failure_message = ""
        self.last_capture_screen_index: int | None = None
        self.capture_display_mode = (capture_display_mode or "auto").strip().lower()
        if self.capture_display_mode not in ("auto", "index"):
            self.capture_display_mode = "auto"
        self.preferred_screen_index = preferred_screen_index
        self._cursor_override_active = False
        self._finished = False
        self._magnifier = CaptureMagnifier(self)
        self._magnifier.changed.connect(self.update)
        self._clear_blank_override_cursors()
        self._use_snapshot_background = is_wayland()
        self._screen_snapshots = capture_screen_snapshots(self._use_snapshot_background)
        self.setWindowFlags(_capture_window_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowTitle(tr("LaTeXSnipper 截图识别"))
        app = cast("QGuiApplication | None", QGuiApplication.instance())
        if app is not None:
            self.setWindowIcon(app.windowIcon())
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

    def _record_pointer(self, event: QMouseEvent) -> _PointerPosition:
        pointer = _PointerPosition(
            event.position().toPoint(), event.globalPosition().toPoint()
        )
        self._pointer = pointer
        return pointer

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

    def _finish_capture(self, pixmap: QPixmap | None) -> None:
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
        self._selection = None
        self._pointer = None
        self._finish_capture(None)
        self.close()

    def _snapshot_at(self, global_pos: QPoint) -> ScreenSnapshot | None:
        for snapshot in self._screen_snapshots:
            if snapshot.geometry.contains(global_pos):
                return snapshot
        return None

    def _popup_rect(
        self, pointer: _PointerPosition, snapshot: ScreenSnapshot | None, offset: QPoint
    ) -> QRect:
        bounds = (
            snapshot.geometry.translated(offset)
            if snapshot is not None
            else self.rect()
        )
        return magnifier_popup_rect(pointer.local, bounds)

    def _cursor_region(
        self, pointer: _PointerPosition | None, offset: QPoint
    ) -> QRegion:
        if pointer is None:
            return QRegion()
        popup_rect = self._popup_rect(
            pointer, self._snapshot_at(pointer.global_pos), offset
        )
        return cursor_region(pointer.local, popup_rect)

    def paintEvent(self, event: QPaintEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        offset = -self.geometry().topLeft()
        if self._use_snapshot_background:
            for snapshot in self._screen_snapshots:
                if not snapshot.image.isNull():
                    painter.drawImage(
                        snapshot.geometry.translated(offset), snapshot.image
                    )
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 125))

        selection = self._selection
        rect = selection.local_rect() if selection is not None else None
        if rect is not None:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.restore()

        pointer = self._pointer
        snapshot = None
        popup_rect = None
        if pointer is not None:
            snapshot = self._snapshot_at(pointer.global_pos)
            popup_rect = self._popup_rect(pointer, snapshot, offset)
            draw_crosshair(painter, pointer.local)

        if selection is not None and rect is not None:
            draw_selection(
                painter, self.rect(), rect, selection.global_extent(), popup_rect
            )
        if popup_rect is not None and snapshot is not None and pointer is not None:
            self._magnifier.paint(painter, popup_rect, snapshot, pointer.global_pos)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        pointer = self._record_pointer(event)
        self._selection = _DragSelection(pointer, pointer)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        offset = -self.geometry().topLeft()
        previous_visual_region = self._cursor_region(self._pointer, offset)
        pointer = self._record_pointer(event)
        dirty_region = previous_visual_region.united(
            self._cursor_region(pointer, offset)
        )
        selection = self._selection
        if selection is not None:
            previous_selection = selection.local_rect()
            selection.end = pointer
            current_selection = selection.local_rect()
            dirty_region += QRegion(previous_selection).xored(
                QRegion(current_selection)
            )
            width = self.width()
            dirty_region += selection_edge_region(previous_selection, width)
            dirty_region += selection_edge_region(current_selection, width)
        self.update(dirty_region)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        pointer = self._record_pointer(event)
        if self._selection is not None:
            self._selection.end = pointer
        self.update()
        self._capture_selection()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        if event.key() == Qt.Key.Key_C:
            pointer = self._pointer
            if not event.isAutoRepeat() and pointer is not None:
                snapshot = self._snapshot_at(pointer.global_pos)
                if snapshot is not None:
                    self._magnifier.copy_color(snapshot, pointer.global_pos)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Shift:
            if not event.isAutoRepeat():
                self._magnifier.toggle_color_format()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        super().keyPressEvent(event)

    def _show_without_activation(self) -> bool:
        """Report whether the overlay must appear without activating the application."""
        if sys.platform != "darwin":
            return False
        state = QGuiApplication.applicationState()
        return state != Qt.ApplicationState.ApplicationActive

    def prepare_background_presentation(self) -> bool:
        """Apply the non-activating style before the panel is ordered front.

        Setting the style mask inside showEvent is too late: macOS already
        activated the application while ordering the panel onto the screen.
        """
        if not self._show_without_activation():
            return False
        return macos_make_nonactivating_panel(self)

    def showEvent(self, event: QShowEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        super().showEvent(event)
        try:
            global_pos = QCursor.pos()
            self._pointer = _PointerPosition(self.mapFromGlobal(global_pos), global_pos)
            self._hide_system_cursor()
            if not self._show_without_activation():
                self.activateWindow()
                self.raise_()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            self.grabKeyboard()
            self.update()
        except Exception:
            pass

    def hideEvent(self, event: QHideEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._restore_system_cursor()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        self._restore_system_cursor()
        super().closeEvent(event)

    @staticmethod
    def _screen_label(index: int, screens: list[QScreen]) -> str:
        if 0 <= int(index) < len(screens):
            try:
                name = str(screens[index].name() or "").strip()
            except Exception:
                name = ""
            if name:
                return tr("屏幕 {number}（{name}）").format(
                    number=int(index) + 1, name=name
                )
        return tr("屏幕 {number}").format(number=int(index) + 1)

    def _build_screen_mismatch_message(
        self, target_idx: int, actual_idx: int, screens: list[QScreen]
    ) -> str:
        target = self._screen_label(target_idx, screens)
        actual = self._screen_label(actual_idx, screens)
        return tr(
            "当前截图模式固定为{target}，但你框选的是{actual}。"
            "请在托盘菜单选择“识别屏幕 > {actual}”，或切换为“自动”后再截图。"
        ).format(target=target, actual=actual)

    def _capture_selection(self) -> None:
        self.last_capture_failure_message = ""
        self.last_capture_screen_index = None
        selection = self._selection
        if selection is None:
            self._finish_capture(None)
            return
        global_rect = selection.global_extent()
        if global_rect[2] <= 0 or global_rect[3] <= 0:
            self._finish_capture(None)
            return

        release = selection.end.global_pos
        release_xy = (release.x(), release.y())
        screens = QGuiApplication.screens()
        screen_geos = [_rect_to_tuple(screen.geometry()) for screen in screens]
        target_idx = choose_screen_index(
            release_xy,
            screen_geos,
            self.capture_display_mode,
            self.preferred_screen_index,
        )
        if target_idx < 0:
            screen = QGuiApplication.primaryScreen()
            target_idx = 0
        else:
            screen = screens[target_idx]
        if screen is None:
            self._finish_capture(None)
            return

        geometry = screen.geometry()
        mapped = map_global_rect_to_screen_capture(
            global_rect, _rect_to_tuple(geometry)
        )
        if mapped is None:
            if self.capture_display_mode == "index":
                actual_idx = choose_screen_index(release_xy, screen_geos)
                if actual_idx != target_idx and 0 <= actual_idx < len(screens):
                    self.last_capture_failure_message = (
                        self._build_screen_mismatch_message(
                            target_idx, actual_idx, screens
                        )
                    )
            self._finish_capture(None)
            return

        logical_rect, grab_rect = mapped
        snapshot = next(
            (item for item in self._screen_snapshots if item.geometry == geometry), None
        )
        pixmap = (
            crop_screen_snapshot(snapshot, logical_rect)
            if snapshot is not None
            else QPixmap()
        )
        if pixmap.isNull() and not self._use_snapshot_background:
            pixmap = self._grab_selection(screen, grab_rect)
        if pixmap.isNull():
            self.last_capture_failure_message = self._capture_failure_message()
            logger.error("截图接口返回空图像")
        self.last_capture_screen_index = target_idx
        logger.debug(
            "截图 pixmap: size=%sx%s screen=%s dpr=%s",
            pixmap.width(),
            pixmap.height(),
            target_idx,
            f"{screen.devicePixelRatio():.2f}",
        )
        self._finish_capture(pixmap)

    def _grab_selection(
        self, screen: QScreen, rect: tuple[int, int, int, int]
    ) -> QPixmap:
        # On macOS and X11 the native grab can include the overlay itself.
        hide_overlay = os.name != "nt"
        if hide_overlay:
            try:
                self.hide()
                QGuiApplication.processEvents()
                time.sleep(0.05)
            except Exception:
                pass
        x, y, width, height = rect
        try:
            pixmap = screen.grabWindow(x=x, y=y, width=width, height=height)
            if pixmap.isNull():
                logger.warning("grabWindow(0) 返回空")
            return pixmap
        finally:
            if hide_overlay:
                try:
                    self.show()
                except Exception:
                    pass

    def _capture_failure_message(self) -> str:
        if sys.platform != "darwin":
            return tr("未能获取截图，请检查桌面截图权限和应用日志。")
        if self.macos_permission_preflight_state == "allowed":
            return tr(
                "屏幕录制权限已通过预检，但 Qt 截图没有返回图像。"
                "请检查截图区域、显示器连接和应用日志后重试。"
            )
        return tr(
            "无法确认当前进程的屏幕录制权限，且截图接口没有返回图像。"
            "请检查应用日志，并在系统设置中确认授权的是当前运行副本后重试。"
        )

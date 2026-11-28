from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QMouseEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from capture.backends import capture_screen_snapshots  # noqa: E402
from capture.geometry import (  # noqa: E402
    ScreenSnapshot,
    choose_screen_index,
    crop_screen_snapshot,
    map_global_rect_to_screen_capture,
    split_desktop_snapshot,
)
from capture.magnifier import magnifier_popup_rect  # noqa: E402
from capture.overlay import (  # noqa: E402
    ScreenCaptureOverlay,
    _capture_window_flags,
)


class CaptureOverlayMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_choose_screen_index_handles_extended_screen_right(self):
        screens = [
            (0, 0, 1920, 1080),
            (1920, 0, 2560, 1440),
        ]

        self.assertEqual(choose_screen_index((3000, 900), screens), 1)
        self.assertEqual(choose_screen_index((1919, 500), screens), 0)
        self.assertEqual(choose_screen_index((1920, 500), screens), 1)

    def test_capture_overlay_uses_tool_window_semantics(self):
        flags = _capture_window_flags()

        self.assertTrue(flags & Qt.WindowType.Tool)
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)

    def test_choose_screen_index_handles_extended_screen_left(self):
        screens = [
            (0, 0, 1920, 1080),
            (-1280, 0, 1280, 1024),
        ]

        self.assertEqual(choose_screen_index((-10, 500), screens), 1)
        self.assertEqual(choose_screen_index((0, 500), screens), 0)

    def test_map_global_rect_clips_to_target_screen(self):
        mapped = map_global_rect_to_screen_capture(
            (1800, 100, 300, 120),
            (1920, 0, 2560, 1440),
        )

        self.assertEqual(mapped, ((0, 100, 180, 120), (0, 100, 180, 120)))

    def test_crop_screen_snapshot_uses_clean_hidpi_snapshot_pixels(self):
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        for y in range(6, 10):
            for x in range(4, 10):
                image.setPixelColor(x, y, QColor(10, 20, 30))
        snapshot = ScreenSnapshot(
            geometry=QRect(100, 200, 10, 10),
            image=image,
            scale_x=2.0,
            scale_y=2.0,
        )

        pixmap = crop_screen_snapshot(snapshot, (2, 3, 3, 2))
        cropped = pixmap.toImage()

        self.assertFalse(pixmap.isNull())
        self.assertEqual((cropped.width(), cropped.height()), (6, 4))
        self.assertEqual(cropped.pixelColor(0, 0), QColor(10, 20, 30))
        self.assertEqual(cropped.pixelColor(5, 3), QColor(10, 20, 30))

    def test_crop_screen_snapshot_clamps_bottom_right_edge(self):
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        snapshot = ScreenSnapshot(
            geometry=QRect(0, 0, 10, 10),
            image=image,
            scale_x=2.0,
            scale_y=2.0,
        )

        pixmap = crop_screen_snapshot(snapshot, (8, 8, 5, 5))

        self.assertFalse(pixmap.isNull())
        self.assertEqual((pixmap.width(), pixmap.height()), (4, 4))

    def test_portal_desktop_snapshot_preserves_monitor_offsets_and_scale(self):
        image = QImage(200, 50, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))
        image.setPixelColor(125, 20, QColor("white"))
        geometries = [QRect(-50, -25, 50, 25), QRect(0, -25, 50, 25)]
        snapshots = split_desktop_snapshot(image, geometries)
        self.assertEqual([item.geometry for item in snapshots], geometries)
        self.assertEqual(
            [(item.scale_x, item.scale_y) for item in snapshots],
            [(2.0, 2.0), (2.0, 2.0)],
        )
        self.assertEqual(snapshots[0].image.pixelColor(25, 20), QColor("black"))
        self.assertEqual(snapshots[1].image.pixelColor(25, 20), QColor("white"))
        crop = crop_screen_snapshot(snapshots[1], (10, 5, 10, 10)).toImage()
        self.assertEqual((crop.width(), crop.height()), (20, 20))
        self.assertEqual(crop.pixelColor(5, 10), QColor("white"))

    def test_wayland_overlay_keeps_authorized_black_desktop_image(self):
        image = QImage(100, 50, QImage.Format.Format_RGB32)
        image.fill(QColor("black"))
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 100, 50))
        with (
            patch(
                "capture.backends.wayland_screenshot_via_portal", return_value=image
            ) as portal,
            patch("capture.backends.QGuiApplication.screens", return_value=[screen]),
        ):
            snapshots = capture_screen_snapshots(use_portal=True)
        self.assertEqual(portal.call_count, 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].image.pixelColor(30, 20), QColor("black"))

    def test_wayland_overlay_reports_unavailable_portal_capture(self):
        with (
            patch("capture.backends.wayland_screenshot_via_portal", return_value=None),
            self.assertRaisesRegex(RuntimeError, "Screenshot Portal"),
        ):
            capture_screen_snapshots(use_portal=True)

    def _create_overlay(self):
        geometry = self._app.screens()[0].geometry()
        image = QImage(geometry.size() * 2, QImage.Format.Format_RGB32)
        image.fill(QColor(10, 20, 30))
        image.setPixelColor(0, 0, QColor(123, 45, 67))
        snapshot = ScreenSnapshot(geometry, image, 2.0, 2.0)
        with (
            patch("capture.overlay.is_wayland", return_value=True),
            patch("capture.overlay.capture_screen_snapshots", return_value=[snapshot]),
        ):
            overlay = ScreenCaptureOverlay()
        self.addCleanup(overlay.close)
        return overlay

    def _send_mouse(self, overlay, event_type, point, button, buttons):
        event = QMouseEvent(
            event_type,
            QPointF(point),
            QPointF(overlay.mapToGlobal(point)),
            button,
            buttons,
            Qt.KeyboardModifier.NoModifier,
        )
        self._app.sendEvent(overlay, event)

    def test_drag_from_origin_crops_hidpi_snapshot(self):
        overlay = self._create_overlay()
        results = []
        overlay.selection_done.connect(results.append)
        left = Qt.MouseButton.LeftButton
        self._send_mouse(
            overlay, QEvent.Type.MouseButtonPress, QPoint(0, 0), left, left
        )
        self._send_mouse(
            overlay,
            QEvent.Type.MouseMove,
            QPoint(120, 80),
            Qt.MouseButton.NoButton,
            left,
        )
        self._send_mouse(
            overlay,
            QEvent.Type.MouseButtonRelease,
            QPoint(120, 80),
            left,
            Qt.MouseButton.NoButton,
        )

        self.assertEqual(len(results), 1)
        pixmap = results[0]
        self.assertEqual((pixmap.width(), pixmap.height()), (240, 160))
        self.assertEqual(pixmap.devicePixelRatio(), 2.0)
        self.assertEqual(pixmap.toImage().pixelColor(0, 0), QColor(123, 45, 67))
        self.assertEqual(overlay.last_capture_screen_index, 0)

    def test_color_picker_uses_snapshot_pixels_and_escape_cancels(self):
        overlay = self._create_overlay()
        results = []
        overlay.selection_done.connect(results.append)
        no_button = Qt.MouseButton.NoButton
        self._send_mouse(
            overlay, QEvent.Type.MouseMove, QPoint(0, 0), no_button, no_button
        )
        popup = magnifier_popup_rect(QPoint(0, 0), overlay.rect())
        rendered = overlay.grab()
        image = rendered.toImage()
        dpr = rendered.devicePixelRatio()
        center = (popup.topLeft() + QPoint(64, 64)) * dpr
        padding = (popup.topLeft() + QPoint(10, 10)) * dpr
        self.assertEqual(image.pixelColor(center), QColor(123, 45, 67))
        self.assertEqual(image.pixelColor(padding), QColor("white"))

        clipboard = self._app.clipboard()
        old_text = clipboard.text()
        self.addCleanup(clipboard.setText, old_text)

        QTest.keyClick(overlay, Qt.Key.Key_C)
        self.assertEqual(clipboard.text(), "123, 45, 67")
        QTest.keyClick(overlay, Qt.Key.Key_Shift)
        QTest.keyClick(overlay, Qt.Key.Key_C)
        self.assertEqual(clipboard.text(), "#7B2D43")
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        self.assertEqual(results, [None])

    def test_magnifier_position_does_not_flip_at_screen_center(self):
        bounds = QRect(0, 0, 1920, 1080)

        left_of_center = magnifier_popup_rect(QPoint(959, 400), bounds)
        right_of_center = magnifier_popup_rect(QPoint(961, 400), bounds)

        self.assertGreater(left_of_center.left(), 959)
        self.assertGreater(right_of_center.left(), 961)
        self.assertGreater(left_of_center.top(), 400)
        self.assertGreater(right_of_center.top(), 400)

    def test_magnifier_position_flips_only_to_stay_inside_screen(self):
        bounds = QRect(-1280, 0, 1280, 1024)
        pointer = QPoint(-20, 1000)

        popup = magnifier_popup_rect(pointer, bounds)

        self.assertLess(popup.left(), pointer.x())
        self.assertLess(popup.top(), pointer.y())
        self.assertGreaterEqual(popup.left(), bounds.left())
        self.assertLessEqual(popup.right(), bounds.right())
        self.assertGreaterEqual(popup.top(), bounds.top())
        self.assertLessEqual(popup.bottom(), bounds.bottom())

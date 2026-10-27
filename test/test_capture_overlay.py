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

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402

from capture.geometry import (  # noqa: E402
    ScreenSnapshot,
    _place_popup_near_pointer,
    choose_screen_index,
    crop_screen_snapshot,
    map_global_rect_to_screen_capture,
    split_desktop_snapshot,
)
from capture.overlay import (  # noqa: E402
    ScreenCaptureOverlay,
    _capture_window_flags,
)


class CaptureOverlayMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QGuiApplication.instance() or QGuiApplication([])

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
            patch("capture.overlay.is_wayland", return_value=True),
            patch(
                "capture.overlay.wayland_screenshot_via_portal", return_value=image
            ) as portal,
            patch("capture.overlay.QGuiApplication.screens", return_value=[screen]),
        ):
            snapshots = ScreenCaptureOverlay._capture_screen_snapshots(
                SimpleNamespace()
            )
        self.assertEqual(portal.call_count, 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].image.pixelColor(30, 20), QColor("black"))

    def test_wayland_overlay_reports_unavailable_portal_capture(self):
        with (
            patch("capture.overlay.is_wayland", return_value=True),
            patch("capture.overlay.wayland_screenshot_via_portal", return_value=None),
            self.assertRaisesRegex(RuntimeError, "Screenshot Portal"),
        ):
            ScreenCaptureOverlay._capture_screen_snapshots(SimpleNamespace())

    def test_selection_accepts_overlay_top_left_origin(self):
        overlay = SimpleNamespace(
            start_pos=QPoint(0, 0),
            end_pos=QPoint(120, 80),
            start_global_pos=QPoint(0, 0),
            end_global_pos=QPoint(120, 80),
        )

        rect = ScreenCaptureOverlay._selection_rect(overlay)

        self.assertIsNotNone(rect)
        self.assertEqual((rect.x(), rect.y()), (0, 0))
        self.assertEqual(ScreenCaptureOverlay._selection_size(overlay), (120, 80))

    def test_magnifier_position_does_not_flip_at_screen_center(self):
        bounds = QRect(0, 0, 1920, 1080)

        left_of_center = _place_popup_near_pointer(
            QPoint(959, 400), bounds, 126, 202, 14
        )
        right_of_center = _place_popup_near_pointer(
            QPoint(961, 400), bounds, 126, 202, 14
        )

        self.assertGreater(left_of_center.left(), 959)
        self.assertGreater(right_of_center.left(), 961)
        self.assertGreater(left_of_center.top(), 400)
        self.assertGreater(right_of_center.top(), 400)

    def test_magnifier_position_flips_only_to_stay_inside_screen(self):
        bounds = QRect(-1280, 0, 1280, 1024)
        pointer = QPoint(-20, 1000)

        popup = _place_popup_near_pointer(pointer, bounds, 126, 202, 14)

        self.assertLess(popup.left(), pointer.x())
        self.assertLess(popup.top(), pointer.y())
        self.assertGreaterEqual(popup.left(), bounds.left())
        self.assertLessEqual(popup.right(), bounds.right())
        self.assertGreaterEqual(popup.top(), bounds.top())
        self.assertLessEqual(popup.bottom(), bounds.bottom())

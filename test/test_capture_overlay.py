from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# In the Windows GPU dependency environment, importing Qt before onnxruntime can
# make ORT's native extension fail DLL initialization later in the same process.
try:
    importlib.import_module("onnxruntime")
except Exception:
    pass

from PyQt6.QtGui import QColor, QGuiApplication, QImage  # noqa: E402
from PyQt6.QtCore import QRect  # noqa: E402

from backend.capture_overlay import (  # noqa: E402  # type: ignore[reportMissingImports]
    _ScreenSnapshot,
    choose_screen_index,
    crop_screen_snapshot,
    map_global_rect_to_screen_capture,
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
        snapshot = _ScreenSnapshot(
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
        snapshot = _ScreenSnapshot(
            geometry=QRect(0, 0, 10, 10),
            image=image,
            scale_x=2.0,
            scale_y=2.0,
        )

        pixmap = crop_screen_snapshot(snapshot, (8, 8, 5, 5))

        self.assertFalse(pixmap.isNull())
        self.assertEqual((pixmap.width(), pixmap.height()), (4, 4))


if __name__ == "__main__":
    unittest.main()

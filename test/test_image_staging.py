from __future__ import annotations

from pathlib import Path

from PIL import Image

from ui.image_staging import ImageStagingMixin


class FakeImageStagingWindow(ImageStagingMixin):
    def __init__(self) -> None:
        self._staged_image_path: Path | None = None
        self.refreshed: list[Path | None] = []
        self.recognized: list[Path] = []
        self.statuses: list[str] = []

    def _drop_file_kind(self, path: Path) -> str | None:
        return "image" if path.suffix.lower() == ".png" else None

    def _refresh_staged_image_controls(self) -> None:
        self.refreshed.append(self._staged_image_path)

    def _show_staged_image_warning(self, _content: str) -> None:
        raise AssertionError("a valid test image should not show a warning")

    def _set_staged_image_status(self, message: str) -> None:
        self.statuses.append(message)

    def _recognize_image_file(self, path: Path) -> None:
        self.recognized.append(path)


def _write_png(path: Path) -> Path:
    Image.new("RGB", (16, 10), "white").save(path)
    return path


def test_staging_an_image_replaces_the_current_image(tmp_path: Path) -> None:
    window = FakeImageStagingWindow()
    first = _write_png(tmp_path / "first.png")
    second = _write_png(tmp_path / "second.png")

    assert window._stage_image_file(first)
    assert window._stage_image_file(second)

    assert window._staged_image_path == second
    assert window.refreshed == [first, second]
    assert window.recognized == []


def test_explicit_recognition_uses_the_staged_image(tmp_path: Path) -> None:
    window = FakeImageStagingWindow()
    image = _write_png(tmp_path / "formula.png")
    window._stage_image_file(image)

    assert window._recognize_staged_image()

    assert window.recognized == [image]


def test_clearing_a_staged_image_removes_the_selection(tmp_path: Path) -> None:
    window = FakeImageStagingWindow()
    image = _write_png(tmp_path / "formula.png")
    window._stage_image_file(image)

    window._clear_staged_image()

    assert window._staged_image_path is None
    assert window.refreshed[-1] is None

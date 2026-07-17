from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_image_entry_routes_directly_to_existing_recognition_pipeline() -> None:
    recognition = (ROOT / "src" / "recognition" / "recognition_controller.py").read_text(encoding="utf-8")
    file_drop = (ROOT / "src" / "ui" / "file_drop.py").read_text(encoding="utf-8")
    setup = (ROOT / "src" / "ui" / "main_window_setup.py").read_text(encoding="utf-8")

    assert "self._recognize_image_file(Path(file_path))" in recognition
    assert "self._recognize_image_file(path)" in file_drop
    assert 'PushButton(FluentIcon.PHOTO, "图片识别")' in setup


def test_latex_editor_viewport_intercepts_image_file_drops() -> None:
    setup = (ROOT / "src" / "ui" / "main_window_setup.py").read_text(encoding="utf-8")

    assert "self.latex_editor.viewport()," in setup

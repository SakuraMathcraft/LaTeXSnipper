"""Session-scoped staging for a source image before recognition."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


class ImageStagingMixin:
    """Keep one user-selected image ready for explicit recognition."""

    def _stage_image_file(self, file_path: str | Path) -> bool:
        path = Path(file_path)
        if not path.is_file():
            self._show_staged_image_warning(f"图片文件不存在: {path}")
            return False
        if self._drop_file_kind(path) != "image":
            self._show_staged_image_warning("请选择受支持的图片文件。")
            return False
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            self._show_staged_image_warning(f"图片加载失败: {exc}")
            return False

        self._staged_image_path = path
        self._refresh_staged_image_controls()
        self._set_staged_image_status(f"已添加图片：{path.name}")
        return True

    def _clear_staged_image(self) -> None:
        self._staged_image_path = None
        self._refresh_staged_image_controls()
        self._set_staged_image_status("已移除待识别图片")

    def _recognize_staged_image(self) -> bool:
        path = getattr(self, "_staged_image_path", None)
        if path is None or not Path(path).is_file():
            self._show_staged_image_warning("请先添加一张图片。")
            return False
        self._recognize_image_file(Path(path))
        return True

    def _set_staged_image_status(self, message: str) -> None:
        setter = getattr(self, "set_action_status", None)
        if callable(setter):
            setter(message, auto_clear_ms=2200)

    def _show_staged_image_warning(self, content: str) -> None:
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition

            InfoBar.warning(
                title="无法添加图片",
                content=content,
                parent=self,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
            return
        except Exception:
            pass
        try:
            from bootstrap.deps_bootstrap import custom_warning_dialog

            custom_warning_dialog("提示", content, self)
        except Exception:
            pass

    def _refresh_staged_image_controls(self) -> None:
        bar = getattr(self, "staged_image_bar", None)
        if bar is None:
            return
        path = getattr(self, "_staged_image_path", None)
        if path is None or not Path(path).is_file():
            bar.hide()
            return

        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap

        thumbnail = getattr(self, "staged_image_thumbnail", None)
        filename_label = getattr(self, "staged_image_filename", None)
        if thumbnail is not None:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                thumbnail.clear()
            else:
                thumbnail.setPixmap(
                    pixmap.scaled(
                        thumbnail.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        if filename_label is not None:
            filename_label.setText(Path(path).name)
            filename_label.setToolTip(str(path))
        bar.show()

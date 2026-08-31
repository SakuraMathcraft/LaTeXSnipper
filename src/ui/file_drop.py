"""File drag-and-drop helpers and MainWindow mixin."""

from __future__ import annotations

from pathlib import Path

from localization.manager import translate as tr
from PyQt6.QtGui import QGuiApplication, QKeySequence
from qfluentwidgets import InfoBar, InfoBarPosition

from recognition.image_contracts import SUPPORTED_IMAGE_EXTENSIONS
from recognition.image_input import image_from_qimage


class FileDropMixin:
    def _handle_clipboard_image_paste(self, event=None) -> bool:
        if event is not None:
            try:
                if not event.matches(QKeySequence.StandardKey.Paste):
                    return False
            except Exception:
                return False

        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData() if clipboard is not None else None
        if mime is None:
            return False

        if mime.hasImage():
            image = clipboard.image()
            if image.isNull():
                return False
            self._next_predict_result_screen_index = None
            self._start_predict_with_pil(image_from_qimage(image))
            return True

        if mime.hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).is_file()
            ]
            if len(paths) == 1 and self._drop_file_kind(paths[0]) == "image":
                self._recognize_image_file(paths[0])
                return True
        return False

    def keyPressEvent(self, event):
        if self._handle_clipboard_image_paste(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def _get_supported_image_patterns(self):
        """Return image file dialog filter patterns."""
        return [f"*.{extension}" for extension in SUPPORTED_IMAGE_EXTENSIONS]

    def _get_supported_image_extensions(self):
        """Return readable image extensions for prompts."""
        return [
            p.replace("*.", "").upper() for p in self._get_supported_image_patterns()
        ]

    def _get_supported_image_suffixes(self) -> set[str]:
        return {
            p.replace("*", "").lower()
            for p in self._get_supported_image_patterns()
            if p.startswith("*.")
        }

    def _local_drop_paths(self, event) -> list[Path]:
        try:
            mime = event.mimeData()
            if mime is None or not mime.hasUrls():
                return []
            paths: list[Path] = []
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                path = Path(url.toLocalFile())
                if path.is_file():
                    paths.append(path)
            return paths
        except Exception:
            return []

    def _drop_file_kind(self, path: Path) -> str | None:
        suffix = str(path.suffix or "").lower()
        if suffix == ".pdf":
            return "pdf"
        return "image"

    def _drag_contains_local_file(self, event) -> bool:
        return bool(self._local_drop_paths(event))

    def _show_drop_file_warning(self, content: str) -> None:
        try:
            InfoBar.warning(
                title=tr("无法处理拖入文件"),
                content=content,
                parent=self,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
        except Exception as exc:
            print(f"[WARN] 无法显示拖入文件提示: {exc}")

    def _enable_file_drop_target(self, widget) -> None:
        if widget is None:
            return
        try:
            widget.setAcceptDrops(True)
        except Exception:
            pass
        try:
            widget.installEventFilter(self)
        except Exception:
            pass

    def dragEnterEvent(self, event):
        if self._drag_contains_local_file(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_contains_local_file(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._local_drop_paths(event)
        if len(paths) != 1:
            if paths:
                self._show_drop_file_warning(tr("请一次只拖入一个图片或 PDF 文件。"))
                event.acceptProposedAction()
            else:
                img_exts = ", ".join(self._get_supported_image_extensions())
                self._show_drop_file_warning(
                    tr("请拖入单个图片或 PDF 文件。支持图片格式：{formats}。").format(
                        formats=img_exts
                    )
                )
                event.ignore()
            return

        path = paths[0]
        kind = self._drop_file_kind(path)
        if not kind:
            img_exts = ", ".join(self._get_supported_image_extensions())
            self._show_drop_file_warning(
                tr("请拖入单个图片或 PDF 文件。支持图片格式：{formats}。").format(
                    formats=img_exts
                )
            )
            event.ignore()
            return

        event.acceptProposedAction()
        if kind == "image":
            self._recognize_image_file(path)
        elif kind == "pdf":
            self._recognize_pdf_file(path)

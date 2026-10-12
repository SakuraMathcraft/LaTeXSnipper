"""FileInputController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.controllers.pdf import PdfRecognitionController
    from ui.controllers.recognition import ImageRecognitionController
    from ui.main_window import MainWindow
import logging
from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QGuiApplication, QKeySequence
from qfluentwidgets import InfoBar, InfoBarPosition

from localization.manager import translate as tr
from recognition.image_contracts import SUPPORTED_IMAGE_EXTENSIONS
from recognition.image_input import image_from_qimage

logger = logging.getLogger(f"latexsnipper.{__name__}")


class FileInputController(QObject):
    def __init__(
        self,
        view: MainWindow,
        pdf: PdfRecognitionController,
        recognition: ImageRecognitionController,
    ):
        super().__init__(view)
        self.view = view
        self.pdf = pdf
        self.recognition = recognition

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
            self.recognition.recognize_image(image_from_qimage(image))
            return True
        if mime.hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in mime.urls()
                if url.isLocalFile() and Path(url.toLocalFile()).is_file()
            ]
            if len(paths) == 1 and file_kind(paths[0]) == "image":
                self.recognition.recognize_file(paths[0])
                return True
        return False

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

    def _drag_contains_local_file(self, event) -> bool:
        return bool(self._local_drop_paths(event))

    def _show_drop_file_warning(self, content: str) -> None:
        try:
            InfoBar.warning(
                title=tr("无法处理拖入文件"),
                content=content,
                parent=self.view,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
        except Exception as exc:
            logger.warning("无法显示拖入文件提示: %s", exc)

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

    def dropEvent(self, event):
        paths = self._local_drop_paths(event)
        if len(paths) != 1:
            if paths:
                self._show_drop_file_warning(tr("请一次只拖入一个图片或 PDF 文件。"))
                event.acceptProposedAction()
            else:
                img_exts = ", ".join(image_extensions())
                self._show_drop_file_warning(
                    tr("请拖入单个图片或 PDF 文件。支持图片格式：{formats}。").format(
                        formats=img_exts
                    )
                )
                event.ignore()
            return
        path = paths[0]
        kind = file_kind(path)
        if not kind:
            img_exts = ", ".join(image_extensions())
            self._show_drop_file_warning(
                tr("请拖入单个图片或 PDF 文件。支持图片格式：{formats}。").format(
                    formats=img_exts
                )
            )
            event.ignore()
            return
        event.acceptProposedAction()
        if kind == "image":
            self.recognition.recognize_file(path)
        elif kind == "pdf":
            self.pdf.recognize_file(path)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if event.type() == QEvent.Type.KeyPress and self._handle_clipboard_image_paste(
            event
        ):
            event.accept()
            return True
        if event.type() in (
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
        ) and self._drag_contains_local_file(event):
            event.acceptProposedAction()
            return True
        if event.type() == QEvent.Type.Drop and self._local_drop_paths(event):
            self.dropEvent(event)
            return True
        return False


def image_patterns():
    return [f"*.{extension}" for extension in SUPPORTED_IMAGE_EXTENSIONS]


def image_extensions():
    return [extension.upper() for extension in SUPPORTED_IMAGE_EXTENSIONS]


def image_suffixes():
    return {f".{extension.lower()}" for extension in SUPPORTED_IMAGE_EXTENSIONS}


def file_kind(path):
    suffix = Path(path).suffix.lower()
    return "pdf" if suffix == ".pdf" else "image" if suffix in image_suffixes() else ""

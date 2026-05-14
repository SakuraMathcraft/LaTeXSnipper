"""File drag-and-drop helpers and MainWindow mixin."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from qfluentwidgets import InfoBar, InfoBarPosition


class FileDropMixin:
    def _get_supported_image_patterns(self):
        """Return image file dialog filter patterns."""
        try:
            exts = sorted({ext.lower().lstrip(".") for ext in Image.registered_extensions().keys()})
            common = {"png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp"}
            exts = [e for e in exts if e in common] or exts
            patterns = [f"*.{e}" for e in exts if e]
            if patterns:
                return patterns
        except Exception:
            pass
        return ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tif", "*.tiff", "*.webp"]

    def _get_supported_image_extensions(self):
        """Return readable image extensions for prompts."""
        return [p.replace("*.", "").upper() for p in self._get_supported_image_patterns()]

    def _get_supported_image_suffixes(self) -> set[str]:
        return {p.replace("*", "").lower() for p in self._get_supported_image_patterns() if p.startswith("*.")}

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
        if suffix in self._get_supported_image_suffixes():
            return "image"
        return None

    def _drag_contains_local_file(self, event) -> bool:
        return bool(self._local_drop_paths(event))

    def _show_drop_file_warning(self, content: str) -> None:
        try:
            InfoBar.warning(
                title="无法处理拖入文件",
                content=content,
                parent=self,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            try:
                from bootstrap.deps_bootstrap import custom_warning_dialog

                custom_warning_dialog("提示", content, self)
            except Exception:
                pass

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
                self._show_drop_file_warning("请一次只拖入一个图片或 PDF 文件。")
                event.acceptProposedAction()
            else:
                img_exts = ", ".join(self._get_supported_image_extensions())
                self._show_drop_file_warning(f"请拖入单个图片或 PDF 文件。支持图片格式：{img_exts}。")
                event.ignore()
            return

        path = paths[0]
        kind = self._drop_file_kind(path)
        if not kind:
            img_exts = ", ".join(self._get_supported_image_extensions())
            self._show_drop_file_warning(f"请拖入单个图片或 PDF 文件。支持图片格式：{img_exts}。")
            event.ignore()
            return

        event.acceptProposedAction()
        if kind == "image":
            self._recognize_image_file(path)
        elif kind == "pdf":
            self._recognize_pdf_file(path)

"""PDF recognition result window."""

from __future__ import annotations

import base64
import pathlib
import re
import shutil
from typing import Callable

import pyperclip
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, FluentIcon, InfoBar, InfoBarPosition, PushButton


class PdfResultWindow(QMainWindow):
    """Standalone PDF recognition result window; non-modal to avoid blocking the main window."""

    def __init__(
        self,
        status_cb: Callable | None = None,
        window_icon: QIcon | None = None,
        select_save_file: Callable | None = None,
        warning_dialog: Callable | None = None,
        is_dark_ui: Callable[[], bool] | None = None,
    ):
        super().__init__(None)
        self._status_cb = status_cb
        self._select_save_file = select_save_file
        self._warning_dialog = warning_dialog
        self._is_dark_ui = is_dark_ui
        self._fmt_key = "markdown"
        self._preference_label = ""
        self._theme_is_dark_cached = None
        self._structured_result = None

        self.setWindowTitle("PDF 识别结果")
        if window_icon is not None:
            try:
                self.setWindowIcon(window_icon)
            except Exception:
                pass
        self.resize(780, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        container = QWidget(self)
        lay = QVBoxLayout(container)
        lay.addWidget(BodyLabel("识别结果（可编辑/复制/保存）："))
        self.editor = QPlainTextEdit(self)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        self.btn_copy = PushButton(FluentIcon.COPY, "复制")
        self.btn_save = PushButton(FluentIcon.SAVE, "保存")
        self.btn_close = PushButton(FluentIcon.CLOSE, "关闭")
        for button in (self.btn_copy, self.btn_save, self.btn_close):
            button.setFixedHeight(34)
            btn_row.addWidget(button)
        lay.addLayout(btn_row)
        self.setCentralWidget(container)

        self.btn_copy.clicked.connect(self._do_copy)
        self.btn_save.clicked.connect(self._do_save)
        self.btn_close.clicked.connect(self.close)
        self._apply_theme_styles(force=True)

    def set_content(self, text: str, fmt_key: str, preference_label: str = "", structured_result: dict | None = None):
        self._fmt_key = fmt_key
        self._preference_label = str(preference_label or "").strip()
        self._structured_result = structured_result if isinstance(structured_result, dict) else None
        mode = str((self._structured_result or {}).get("mode", "") or "").strip().lower()
        title = "PDF 文档解析结果" if mode == "parse" else "PDF 识别结果"
        if self._preference_label:
            title = f"{title} - {self._preference_label}"
        self.setWindowTitle(title)
        self.editor.setPlainText(text or "")

    def _apply_theme_styles(self, force: bool = False):
        dark = False
        if callable(self._is_dark_ui):
            try:
                dark = bool(self._is_dark_ui())
            except Exception:
                dark = False
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark

    def event(self, event):
        result = super().event(event)
        try:
            if event.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def _show_local_status(self, msg: str):
        InfoBar.success(
            title="提示",
            content=msg,
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
        )

    def _emit_status(self, msg: str):
        try:
            if callable(self._status_cb):
                try:
                    self._status_cb(msg, parent=self)
                    return
                except TypeError:
                    pass
            self._show_local_status(msg)
        except Exception:
            self._show_local_status(msg)

    def _warn(self, title: str, content: str):
        if callable(self._warning_dialog):
            try:
                self._warning_dialog(title, content, self)
                return
            except Exception:
                pass
        InfoBar.warning(
            title=title,
            content=content,
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500,
        )

    def _do_copy(self):
        try:
            pyperclip.copy(self.editor.toPlainText())
            self._emit_status("已复制文档")
        except Exception as exc:
            self._warn("错误", f"复制失败: {exc}")

    def _do_save(self):
        suffix = "md" if self._fmt_key == "markdown" else "tex"
        filter_ = "Markdown (*.md)" if self._fmt_key == "markdown" else "LaTeX (*.tex)"
        if not callable(self._select_save_file):
            self._warn("错误", "保存对话框不可用")
            return
        path, _ = self._select_save_file(
            self,
            "保存识别结果",
            f"识别结果.{suffix}",
            filter_,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(self.editor.toPlainText())
            self._export_structured_assets(path)
            self._emit_status("已保存文档")
        except Exception as exc:
            self._warn("错误", f"保存失败: {exc}")

    def _export_structured_assets(self, document_path: str):
        payload = self._structured_result if isinstance(self._structured_result, dict) else {}
        assets_root = str(payload.get("assets_root", "") or "").strip()
        assets = payload.get("assets") or []
        inline_images = payload.get("inline_images") or {}
        if self._fmt_key != "markdown":
            return

        base_dir = pathlib.Path(document_path).parent
        copied = 0

        if assets_root and isinstance(assets, list) and assets:
            for item in assets:
                if not isinstance(item, dict):
                    continue
                src = pathlib.Path(str(item.get("abs_path", "") or "").strip())
                rel = str(item.get("rel_path", "") or "").strip()
                if not rel and src.name:
                    rel = f"assets/{src.name}"
                if not rel or not src.exists():
                    continue
                dst = base_dir / pathlib.Path(rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                copied += 1

        text = self.editor.toPlainText() if hasattr(self, "editor") else ""
        img_refs = re.findall(r"(?:!|！)\s*\[[^\]]*\]\s*\(([^)]+)\)", text or "")
        if not img_refs:
            return

        candidate_dirs: set[pathlib.Path] = set()
        if assets_root:
            root = pathlib.Path(assets_root)
            if root.exists() and root.is_dir():
                candidate_dirs.add(root)
                candidate_dirs.add(root.parent)
        self._collect_candidate_dirs(payload, candidate_dirs)

        for ref in img_refs:
            rel = str(ref or "").strip().strip('"').strip("'")
            if not self._looks_local_rel_path(rel):
                continue
            rel_path = pathlib.Path(rel)
            dst = base_dir / rel_path
            if dst.exists():
                continue

            found_src = self._find_referenced_image(candidate_dirs, rel_path)
            if found_src is not None:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(found_src, dst)
                copied += 1
                continue

            if self._materialize_inline_image(inline_images, rel_path, dst):
                copied += 1

    @staticmethod
    def _looks_local_rel_path(path_text: str) -> bool:
        text = str(path_text or "").strip()
        if not text:
            return False
        low = text.lower()
        return not (low.startswith("http://") or low.startswith("https://") or low.startswith("data:"))

    @classmethod
    def _collect_candidate_dirs(cls, node, acc: set[pathlib.Path]):
        if isinstance(node, dict):
            for value in node.values():
                cls._collect_candidate_dirs(value, acc)
            return
        if isinstance(node, list):
            for value in node:
                cls._collect_candidate_dirs(value, acc)
            return
        if not isinstance(node, str):
            return
        text = node.strip()
        if not text:
            return
        path = pathlib.Path(text)
        try:
            if path.exists():
                if path.is_dir():
                    acc.add(path)
                elif path.is_file():
                    acc.add(path.parent)
        except Exception:
            pass

    @staticmethod
    def _find_referenced_image(candidate_dirs: set[pathlib.Path], rel_path: pathlib.Path) -> pathlib.Path | None:
        for directory in candidate_dirs:
            src = directory / rel_path
            if src.exists() and src.is_file():
                return src
        return None

    @staticmethod
    def _materialize_inline_image(inline_images, rel_path: pathlib.Path, dst: pathlib.Path) -> bool:
        if not isinstance(inline_images, dict):
            return False
        key = rel_path.name
        data_uri = str(inline_images.get(key, "") or "").strip()
        if data_uri.startswith("data:") and "," in data_uri:
            payload_b64 = data_uri.split(",", 1)[1]
        else:
            payload_b64 = data_uri
        if not payload_b64:
            return False
        try:
            raw = base64.b64decode(payload_b64, validate=False)
            if not raw:
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
            return True
        except Exception:
            return False

    def closeEvent(self, event):
        try:
            doc = self.editor.document()
            doc.setUndoRedoEnabled(False)
            doc.clearUndoRedoStacks()
            self.editor.blockSignals(True)
        except Exception:
            pass
        print("[DEBUG] PDF 结果窗口关闭")
        return super().closeEvent(event)

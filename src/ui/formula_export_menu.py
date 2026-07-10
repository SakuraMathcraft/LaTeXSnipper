"""Shared formula export menu and clipboard helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import Action

from exporting.formula_export import build_formula_export, get_all_export_format_specs


StatusCallback = Callable[[str, str], None]
_active_export_threads: list[QThread] = []
_active_export_tasks: list[QObject] = []


class _PandocFileExportWorker(QObject):
    finished = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(self, format_key: str, latex: str, file_path: str, format_name: str):
        super().__init__()
        self._format_key = format_key
        self._latex = latex
        self._file_path = file_path
        self._format_name = format_name

    @pyqtSlot()
    def run(self) -> None:
        try:
            from exporting.document_assets import prepare_pandoc_document, supports_document_assets
            from exporting.pandoc_exporter import convert_latex_to

            output_path = Path(self._file_path)
            prepared = None
            source = self._latex
            input_format = None
            if supports_document_assets(self._format_key):
                prepared = prepare_pandoc_document(source, output_path)
                source = prepared.text
                if prepared.assets or prepared.skipped_svg_count:
                    input_format = "markdown+tex_math_dollars"

            data = convert_latex_to(
                self._format_key,
                source,
                as_document=True,
                input_format=input_format,
            )
            if isinstance(data, bytes):
                output_path.write_bytes(data)
            else:
                output_path.write_text(str(data), encoding="utf-8")
            message = f"已导出 {self._format_name} 到 {self._file_path}"
            level = "success"
            if prepared is not None and prepared.assets and prepared.asset_dir is not None:
                message += f"；图像资源 {len(prepared.assets)} 个：{prepared.asset_dir}"
            if prepared is not None and prepared.skipped_svg_count:
                message += f"；已跳过 {prepared.skipped_svg_count} 个无效或不完整 SVG"
                level = "warning"
            self.finished.emit(message, level)
        except Exception as exc:
            self.failed.emit(f"导出失败: {exc}")


class _PandocExportTask(QObject):
    def __init__(
        self,
        thread: QThread,
        worker: _PandocFileExportWorker,
        status_callback: StatusCallback | None,
    ):
        super().__init__()
        self._thread = thread
        self._worker = worker
        self._status_callback = status_callback

    @pyqtSlot(str, str)
    def report_finished(self, message: str, level: str) -> None:
        if self._status_callback is not None:
            self._status_callback(message, level)

    @pyqtSlot(str)
    def report_failed(self, message: str) -> None:
        if self._status_callback is not None:
            self._status_callback(message, "error")

    @pyqtSlot()
    def release(self) -> None:
        try:
            _active_export_threads.remove(self._thread)
        except ValueError:
            pass
        try:
            _active_export_tasks.remove(self)
        except ValueError:
            pass
        self._worker = None
        self._thread.deleteLater()
        self.deleteLater()


def populate_formula_export_menu(menu, export_callback: Callable[[str], None]) -> None:
    for spec in get_all_export_format_specs():
        if spec.separator_before:
            menu.addSeparator()
            continue
        if spec.key == "_pandoc_header":
            header_action = Action(spec.label or spec.key)
            header_action.setEnabled(False)
            menu.addAction(header_action)
            continue
        menu.addAction(Action(spec.label or spec.key, triggered=lambda _checked=False, key=spec.key: export_callback(key)))


def export_formula_to_clipboard(
    format_type: str,
    latex: str,
    *,
    mathml_converter: Callable[[str], str],
    omml_converter: Callable[[str], str],
    svg_converter: Callable[[str], str],
    parent=None,
    status_callback: StatusCallback | None = None,
) -> tuple[bool, str]:
    result, format_name = build_formula_export(
        format_type,
        latex,
        mathml_converter=mathml_converter,
        omml_converter=omml_converter,
        svg_converter=svg_converter,
    )
    if not result:
        return False, "复制失败"

    if result.startswith("[BINARY:"):
        return _handle_pandoc_file_export(
            format_type,
            latex,
            format_name,
            parent=parent,
            status_callback=status_callback,
        )

    if result.startswith("[Pandoc ") and ("不可用" in result or "失败" in result):
        return False, result

    try:
        QApplication.clipboard().setText(result)
        return True, f"已复制 {format_name} 格式"
    except Exception:
        try:
            import pyperclip

            pyperclip.copy(result)
            return True, f"已复制 {format_name} 格式"
        except Exception:
            return False, "复制失败"


def _handle_pandoc_file_export(
    format_key: str,
    latex: str,
    format_name: str,
    *,
    parent=None,
    status_callback: StatusCallback | None = None,
) -> tuple[bool, str]:
    from PyQt6.QtWidgets import QFileDialog
    from exporting.pandoc_exporter import PANDOC_FORMAT_MAP

    fmt = PANDOC_FORMAT_MAP.get(format_key)
    if fmt is None:
        return False, f"未知的 Pandoc 格式: {format_key}"

    file_path, _ = QFileDialog.getSaveFileName(
        parent,
        f"导出为 {format_name}",
        f"formula{fmt.extension}",
        f"{fmt.label} (*{fmt.extension})",
    )
    if not file_path:
        return False, "已取消导出"

    thread = QThread()
    worker = _PandocFileExportWorker(format_key, latex, file_path, format_name)
    worker.moveToThread(thread)
    task = _PandocExportTask(thread, worker, status_callback)

    worker.finished.connect(task.report_finished)
    worker.failed.connect(task.report_failed)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(task.release)
    thread.started.connect(worker.run)
    _active_export_threads.append(thread)
    _active_export_tasks.append(task)
    thread.start()
    return True, f"正在导出 {format_name}..."


def show_formula_export_menu(
    *,
    parent,
    menu_cls,
    anchor_widget,
    text_source,
    status_callback: StatusCallback,
    export_callback: Callable[[str, str], None],
    empty_hint: str = "内容为空",
) -> None:
    def current_text() -> str:
        try:
            if callable(text_source):
                return (text_source() or "").strip()
        except Exception:
            return ""
        return (str(text_source) if text_source is not None else "").strip()

    text = current_text()
    if not text:
        status_callback(empty_hint, "warning")
        return

    def export_current(format_type: str) -> None:
        current = current_text()
        if not current:
            status_callback(empty_hint, "warning")
            return
        export_callback(format_type, current)

    menu = menu_cls(parent=parent)
    populate_formula_export_menu(menu, export_current)
    pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft()) if anchor_widget else parent.mapToGlobal(parent.rect().center())
    menu.exec(pos)

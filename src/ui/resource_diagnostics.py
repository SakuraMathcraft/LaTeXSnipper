"""Report installation metadata and observed worker errors without integrity scans."""

import json
import logging
import sys
import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

from localization.manager import translate as tr
from runtime.installed_resources import installed_resources

logger = logging.getLogger(f"latexsnipper.{__name__}")


class ResourceDiagnosticsDialog(QDialog):
    checked = pyqtSignal(object)

    def __init__(self, models, parent=None):
        super().__init__(parent)
        self._models = models
        self._report = None
        self._checking = False
        self.setWindowTitle(tr("应用诊断"))
        self.resize(720, 480)
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setPlainText(tr("正在读取运行信息，请稍候。"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.output)
        self.checked.connect(self._show_report)
        models.status_changed.connect(self._render_report)
        models.selection_changed.connect(self._render_report)
        if models.model is not None:
            models.model.status_signal.connect(self._render_report)
        self._inspect_resources()

    def _inspect_resources(self) -> None:
        if self._checking:
            return
        self._checking = True

        def inspect():
            try:
                resources = installed_resources()
                if resources is None:
                    report = {"mode": "development", "python": sys.executable}
                else:
                    report = {
                        "version": resources.manifest.version,
                        "target": resources.manifest.target,
                        "root": str(resources.root),
                        "base_id": resources.manifest.base_id,
                        "python": str(resources.python),
                    }
            except Exception as exc:
                logger.exception("安装资源诊断失败")
                report = {"error": str(exc)}
            try:
                self.checked.emit(report)
            except RuntimeError:
                pass

        threading.Thread(
            target=inspect, name="resource-diagnostics", daemon=True
        ).start()

    def _show_report(self, report: dict) -> None:
        self._checking = False
        self._report = report
        self._render_report()

    def _render_report(self, *_args) -> None:
        if self._report is None:
            return
        model = self._models.model
        failure = model.get_failure_info() if model is not None else {}
        status = (
            "warming-up"
            if self._models.warming_up
            else "failed"
            if failure
            else "ready"
            if model is not None and model.is_ready()
            else "idle"
        )
        runtime = {
            "status": status,
            "worker": dict(model.runtime_info) if model is not None else {},
            "provider": dict(model.provider_info) if model is not None else {},
            "failure": failure,
        }
        self.output.setPlainText(
            json.dumps({**self._report, **runtime}, ensure_ascii=False, indent=2)
        )

    def showEvent(self, event) -> None:
        self._render_report()
        self._inspect_resources()
        super().showEvent(event)

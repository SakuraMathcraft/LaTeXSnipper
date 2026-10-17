"""StatusController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.main_window import MainWindow
from typing import Literal

from PyQt6.QtCore import QObject, pyqtSignal
from qfluentwidgets import InfoBar, InfoBarPosition

from localization.manager import translate as tr

ActionStatusLevel = Literal["success", "info", "warning", "error"]


class StatusController(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        view: MainWindow,
        models: ModelRuntimeController,
        notification_parent: Callable[[], QWidget],
    ):
        super().__init__(view)
        self.view = view
        self.models = models
        self.notification_parent = notification_parent
        self.model_status = tr("未加载")

    def _get_status_model_display_name(self) -> str:
        current = str(getattr(self.models, "current_model", "") or "").strip()
        if current != "external_model":
            return current
        try:
            cfg = self.models.external_config()
            if cfg.normalized_provider() == "mineru":
                return "MinerU Local"
            model_name = cfg.normalized_model_name()
            if model_name:
                return model_name
        except Exception:
            pass
        return current

    def sync_model_status(self) -> None:
        preferred = self.models.current_model
        if preferred == "external_model":
            self.set_model_status(self.models.external_status())
            return
        if not getattr(self.models, "model", None):
            self.set_model_status(tr("待识别时加载"))
            return
        if self.models.model.is_model_ready(preferred):
            self.set_model_status(tr("已加载"))
        elif preferred.startswith("mathcraft") and getattr(
            self.models.model, "_import_failed", False
        ):
            self.set_model_status(tr("加载失败"))
        else:
            self.set_model_status(tr("待识别时加载"))

    def refresh_status_label(self):
        model_display = self._get_status_model_display_name()
        base = tr("当前模型: {model} | 状态: {status}").format(
            model=model_display, status=self.model_status
        )
        lbl = getattr(self.view, "status_label", None)
        if lbl is None:
            return
        lbl.setText(base)

    def set_model_status(self, msg: str):
        self.model_status = msg
        self.refresh_status_label()
        self.changed.emit()

    def set_action_status(self, msg: str, auto_clear_ms: int = 2500, parent=None):
        self.show_action_status(
            msg, level="success", auto_clear_ms=auto_clear_ms, parent=parent
        )

    def show_action_status(
        self,
        msg: str,
        *,
        level: ActionStatusLevel = "info",
        auto_clear_ms: int = 2500,
        parent=None,
        position=InfoBarPosition.TOP_RIGHT,
    ) -> None:
        text = str(msg or "").strip()
        if not text:
            return
        infobar = {
            "success": InfoBar.success,
            "info": InfoBar.info,
            "warning": InfoBar.warning,
            "error": InfoBar.error,
        }.get(level, InfoBar.info)
        infobar(
            title=tr("提示"),
            content=text,
            parent=parent or self.view,
            position=position,
            duration=auto_clear_ms,
        )

    def show_status_message(self, msg: str):
        text = str(msg or "").strip()
        if not text:
            return
        if text.startswith("[INFO] MathCraft model cache:"):
            self.models._show_mathcraft_cache_repair_infobar(
                text.split(":", 1)[-1].strip()
            )
            return
        if text.startswith("["):
            return
        self.set_model_status(text)

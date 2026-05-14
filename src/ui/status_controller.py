"""Status label and model notice mixin."""

from __future__ import annotations

from qfluentwidgets import InfoBar, InfoBarPosition


class StatusControllerMixin:
    def _get_status_model_display_name(self) -> str:
        current = str(getattr(self, "current_model", "") or "").strip()
        if current != "external_model":
            return current
        try:
            cfg = self._get_external_model_config()
            if cfg.normalized_provider() == "mineru":
                return "MinerU"
            model_name = cfg.normalized_model_name()
            if model_name:
                return model_name
        except Exception:
            pass
        return current

    def _sync_current_model_status_from_preference(self) -> None:
        preferred = str(self._get_preferred_model_for_predict() or getattr(self, "current_model", "mathcraft") or "mathcraft").strip()
        self.current_model = preferred
        try:
            self.cfg.set("default_model", preferred)
        except Exception:
            pass
        if preferred == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            return
        if not getattr(self, "model", None):
            self.set_model_status(f"待识别时加载 ({preferred})")
            return
        if self.model.is_model_ready(preferred):
            self.set_model_status("已加载")
        elif preferred.startswith("mathcraft") and getattr(self.model, "_import_failed", False):
            self.set_model_status(f"加载失败 ({preferred})")
        else:
            self.set_model_status(f"待识别时加载 ({preferred})")

    def refresh_status_label(self):
        model_display = self._get_status_model_display_name()
        base = f"当前模型: {model_display} | 状态: {self.model_status}"
        lbl = getattr(self, "status_label", None)
        if lbl is None:
            return
        lbl.setText(base)

    def set_model_status(self, msg: str):
        self.model_status = msg
        self.refresh_status_label()

    def set_action_status(self, msg: str, auto_clear_ms: int = 2500, parent=None):
        InfoBar.success(
            title="提示",
            content=msg,
            parent=parent or self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=auto_clear_ms
        )

    def show_status_message(self, msg: str):

        text = str(msg or "").strip()
        if not text:
            return
        if text.startswith("[INFO] MathCraft model cache:"):
            self._show_mathcraft_cache_repair_infobar(text.split(":", 1)[-1].strip())
            return

        if text.startswith("["):
            return
        self.set_model_status(text)

    def _should_show_mathcraft_warmup_started_infobar(self, model_name: str | None) -> bool:
        if self._mathcraft_required_models_incomplete(model_name):
            return True
        return not bool(self.cfg.get("mathcraft_warmup_notice_done", False))

    def _show_mathcraft_warmup_started_infobar(self) -> None:
        if self._model_warmup_notice_shown:
            return
        self._model_warmup_notice_shown = True
        try:
            InfoBar.info(
                title="MathCraft OCR 正在预热",
                content="首次预热可能需要下载或初始化模型权重，网速较慢时耗时会更长，请稍候。",
                parent=self._get_infobar_parent(),
                duration=5200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def _show_mathcraft_cache_repair_infobar(self, detail: str = "") -> None:
        if self._model_cache_repair_notice_shown:
            return
        self._model_cache_repair_notice_shown = True
        content = "检测到 MathCraft 模型权重缺失或不完整，正在自动补全。"
        if detail:
            content = f"{content}\n{detail[:180]}"
        try:
            InfoBar.warning(
                title="正在修复模型缓存",
                content=content,
                parent=self._get_infobar_parent(),
                duration=6500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

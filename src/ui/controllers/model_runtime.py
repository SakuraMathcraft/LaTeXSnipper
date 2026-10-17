"""ModelRuntimeController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from runtime.config_manager import ConfigManager
    from ui.controllers.tasks import RecognitionTaskController
    from ui.main_window import MainWindow
import logging
import threading

from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from qfluentwidgets import InfoBar, InfoBarPosition

from backend.external_model import load_config_from_mapping
from backend.mathcraft.diagnostics import classify_mathcraft_failure
from localization.manager import translate as tr
from recognition.error_messages import translate_mathcraft_diagnostic
from ui.controllers.theme import normalize_theme_mode

logger = logging.getLogger(f"latexsnipper.{__name__}")


class ModelRuntimeController(QObject):
    status_changed = pyqtSignal(str)
    selection_changed = pyqtSignal()
    settings_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    _model_warmup_result_signal = pyqtSignal(object)

    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        tasks: RecognitionTaskController,
        notice: Callable[..., None],
        notification_parent: Callable[[], QWidget],
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.tasks = tasks
        self.notice = notice
        self.notification_parent = notification_parent
        self.model = None
        self._model_warmup_in_progress = False
        self._model_warmup_cancelled = False
        self._model_warmup_notice_shown = False
        self._model_warmup_callbacks = []
        self._sanitize_model_config()
        self._model_warmup_result_signal.connect(self._apply_model_warmup_result)
        from backend.mathcraft.model import ModelWrapper

        self.model = ModelWrapper(auto_warmup=False)
        self._warmup_thread = None

    def _sanitize_model_config(self):
        """Validate and normalize the supported model configuration."""
        try:
            backend = (
                str(self.cfg.get("recognition_backend", "mathcraft") or "")
                .strip()
                .lower()
            )
            if backend not in {"mathcraft", "external_model"}:
                backend = "mathcraft"
            mode = str(self.cfg.get("mathcraft_mode", "formula") or "").strip().lower()
            if mode not in ("formula", "mixed", "text"):
                mode = "formula"
            values = {"recognition_backend": backend, "mathcraft_mode": mode}
            theme_mode = normalize_theme_mode(self.cfg.get("theme_mode", "auto"))
            if self.cfg.get("theme_mode", "auto") != theme_mode:
                values["theme_mode"] = theme_mode
            external_defaults = load_config_from_mapping(self.cfg).to_mapping()
            for key, default in external_defaults.items():
                if self.cfg.get(key) is None:
                    values[key] = default
            changes = {
                key: value
                for key, value in values.items()
                if self.cfg.get(key) != value
            }
            if changes:
                self.cfg.set_many(changes)
                logger.debug("已校正当前模型配置")
        except Exception as e:
            logger.warning("模型配置校验失败: %s", e)

    @property
    def current_model(self) -> str:
        if self.recognition_backend == "external_model":
            return "external_model"
        mode = (self.cfg.get("mathcraft_mode", "formula") or "formula").lower()
        mode_map = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mode_map.get(mode, "mathcraft")

    def external_config(self):
        return load_config_from_mapping(self.cfg)

    def external_display_name(self, config=None, result=None) -> str:
        try:
            model_name = str(getattr(result, "model_name", "") or "").strip()
            if model_name:
                return model_name
        except Exception:
            pass
        try:
            if config is None:
                config = self.external_config()
            model_name = str(
                getattr(config, "normalized_model_name", lambda: "")() or ""
            ).strip()
            if model_name:
                return model_name
            provider = str(
                getattr(config, "normalized_provider", lambda: "external_model")() or ""
            ).strip()
            return provider or "external_model"
        except Exception:
            return "external_model"

    def external_configured(self) -> bool:
        cfg = self.external_config()
        if not cfg.normalized_base_url():
            return False
        if cfg.normalized_provider() == "mineru":
            return bool(cfg.normalized_mineru_endpoint())
        return bool(cfg.normalized_model_name())

    def _get_external_model_required_fields_hint(self) -> str:
        cfg = self.external_config()
        if cfg.normalized_provider() == "mineru":
            return tr("请先在设置页填写 Base URL 和 MinerU Local 解析接口路径。")
        return tr("请先在设置页填写 Base URL 和模型名。")

    def external_status(self) -> str:
        if self.external_configured():
            return tr("外部模型已配置")
        return tr("外部模型未配置")

    def show_external_configuration(self) -> None:
        """Open external-model settings and attach guidance to that visible window."""
        self.status_changed.emit(tr("外部模型未配置"))
        self.settings_requested.emit()
        parent = self.notification_parent()
        if parent is None or not parent.isVisible():
            parent = self.view
        self.notice(
            self._get_external_model_required_fields_hint(),
            level="warning",
            auto_clear_ms=5200,
            parent=parent,
            position=InfoBarPosition.TOP,
        )

    def warmup_selected(self):
        if not self.model:
            return
        preferred = self.current_model
        if not preferred:
            return
        if preferred == "external_model":
            self.status_changed.emit(self.external_status())
            return
        self.ensure_warmup(
            preferred_model=preferred,
            announce_success=True,
            success_message=tr("MathCraft OCR 预热完成，可直接识别"),
        )

    def ensure_warmup(
        self,
        preferred_model: str | None = None,
        on_ready=None,
        on_fail=None,
        announce_success: bool = False,
        success_message: str = "",
    ):
        if self._model_warmup_cancelled or not self.model:
            return
        preferred = (preferred_model or self.current_model).lower()
        if self.model.is_model_ready(preferred):
            self.status_changed.emit(tr("已加载"))
            if callable(on_ready):
                QTimer.singleShot(0, on_ready)
            return
        if callable(on_ready) or callable(on_fail):
            self._model_warmup_callbacks.append((on_ready, on_fail))
        if self._model_warmup_in_progress:
            self.status_changed.emit(tr("预热中"))
            return
        self._model_warmup_in_progress = True
        self._model_warmup_notice_shown = False
        self.status_changed.emit(tr("预热中"))
        if self._should_show_mathcraft_warmup_started_infobar(preferred):
            self._show_mathcraft_warmup_started_infobar()

        def worker():
            ok = False
            err = ""
            failure_info = {}
            try:
                if self._model_warmup_cancelled:
                    return
                ok = bool(self.model.warmup(preferred))
                if not ok:
                    failure_info = self.model.get_failure_info()
                if not ok and (not err):
                    getter = getattr(self.model, "get_error", None)
                    if callable(getter):
                        err = str(getter() or "")
            except Exception as e:
                ok = False
                err = str(e)
            try:
                if self._model_warmup_cancelled or sip.isdeleted(self):
                    return
                data = {
                    "ok": ok,
                    "err": err,
                    "failure_info": failure_info,
                    "announce_success": bool(announce_success),
                    "success_message": str(success_message or ""),
                    "on_ready": on_ready,
                    "on_fail": on_fail,
                    "preferred": preferred,
                }
                self._model_warmup_result_signal.emit(data)
            except RuntimeError as e:
                logger.debug("退出期间忽略模型预热回调: %s", e)

        self._warmup_thread = threading.Thread(target=worker, daemon=True)
        self._warmup_thread.start()

    def _apply_model_warmup_result(self, data):
        if self._model_warmup_cancelled:
            return
        if not isinstance(data, dict):
            return
        ok = bool(data.get("ok"))
        err = str(data.get("err", "") or "")
        announce_success = (
            bool(data.get("announce_success"))
            and data.get("preferred") == self.current_model
        )
        success_message = str(data.get("success_message", "") or "")
        direct_on_ready = data.get("on_ready")
        direct_on_fail = data.get("on_fail")
        self._model_warmup_in_progress = False
        callbacks = list(self._model_warmup_callbacks)
        self._model_warmup_callbacks.clear()
        if ok:
            if self.model.is_model_ready(self.current_model):
                self.status_changed.emit(tr("已加载"))
            if not bool(self.cfg.get("mathcraft_warmup_notice_done", False)):
                self.cfg.set("mathcraft_warmup_notice_done", True)
            self.selection_changed.emit()
            if announce_success:
                InfoBar.success(
                    title=tr("模型预热完成"),
                    content=success_message or tr("MathCraft OCR 已就绪"),
                    parent=self.notification_parent(),
                    duration=2500,
                    position=InfoBarPosition.TOP,
                )
            for cb_ok, _ in callbacks:
                if callable(cb_ok):
                    try:
                        cb_ok()
                    except Exception:
                        pass
            if callable(direct_on_ready) and (not callbacks):
                try:
                    direct_on_ready()
                except Exception:
                    pass
            return
        if data.get("preferred") == self.current_model:
            self.status_changed.emit(tr("未就绪"))
        fail_info = data.get("failure_info") or classify_mathcraft_failure(err)
        if announce_success:
            InfoBar.warning(
                title=translate_mathcraft_diagnostic(
                    fail_info["title"] or "模型预热未完成"
                ),
                content=translate_mathcraft_diagnostic(
                    fail_info["user_message"]
                    or "MathCraft OCR 预热失败，将在首次识别时重试"
                ),
                parent=self.notification_parent(),
                duration=4200,
                position=InfoBarPosition.TOP,
            )
        fail_msg = translate_mathcraft_diagnostic(
            fail_info["user_message"] or err or "MathCraft OCR 模型未部署或加载失败。"
        )
        for _, cb_fail in callbacks:
            if callable(cb_fail):
                try:
                    cb_fail(fail_msg)
                except Exception:
                    pass
        if callable(direct_on_fail) and (not callbacks):
            try:
                direct_on_fail(fail_msg)
            except Exception:
                pass

    def select_model(self, model_name: str):
        info_parent = self.notification_parent()
        m = (model_name or "").lower()
        valid_modes = (
            "mathcraft",
            "mathcraft_text",
            "mathcraft_mixed",
            "external_model",
        )
        if m not in valid_modes:
            m = "mathcraft"
        prev_model = self.current_model
        if m != prev_model and self.tasks.is_busy(source="mode_switch"):
            self.cancel_requested.emit()
        if m == prev_model:
            if m == "external_model":
                self.status_changed.emit(self.external_status())
            elif self.model and self.model.is_model_ready(m):
                self.status_changed.emit(tr("已加载"))
            else:
                self.status_changed.emit(tr("待识别时加载"))
            return
        mode_names = {
            "mathcraft": tr("MathCraft 公式识别"),
            "mathcraft_text": tr("MathCraft 纯文字识别"),
            "mathcraft_mixed": tr("MathCraft 混合识别"),
            "external_model": tr("外部模型"),
        }
        mode_display = mode_names.get(m, m)
        InfoBar.success(
            title=tr("模式切换成功"),
            content=tr("已切换到 {mode}").format(mode=mode_display),
            parent=info_parent,
            duration=3000,
            position=InfoBarPosition.TOP,
        )
        values = {
            "recognition_backend": "external_model"
            if m == "external_model"
            else "mathcraft"
        }
        if m.startswith("mathcraft"):
            mode_map = {
                "mathcraft": "formula",
                "mathcraft_mixed": "mixed",
                "mathcraft_text": "text",
            }
            values["mathcraft_mode"] = mode_map[m]
        self.cfg.set_many(values)
        if m == "external_model":
            self.status_changed.emit(self.external_status())
        elif self.model and self.model.is_model_ready(m):
            self.status_changed.emit(tr("已加载"))
        else:
            self.status_changed.emit(tr("待识别时加载"))
        self.selection_changed.emit()

    def _mathcraft_profile_for_model(self, model_name: str | None) -> str:
        model = str(model_name or "mathcraft").strip().lower()
        if model == "mathcraft_text":
            return "text"
        if model == "mathcraft_mixed":
            return "mixed"
        return "formula"

    def needs_models(self, model_name: str | None) -> bool:
        try:
            from mathcraft_ocr.cache import inspect_model_cache
            from mathcraft_ocr.profiles import PROFILE_MODEL_IDS

            profile = self._mathcraft_profile_for_model(model_name)
            from runtime.installed_resources import installed_resources
            from runtime.model_resources import desktop_model_resources

            resources = desktop_model_resources(installed_resources())
            manifest = resources.manifest
            for model_id in PROFILE_MODEL_IDS.get(profile, ()):
                spec = manifest.models.get(model_id)
                if spec is None:
                    return True
                if not inspect_model_cache(resources.root, spec).complete:
                    return True
            return False
        except Exception:
            return False

    def _should_show_mathcraft_warmup_started_infobar(
        self, model_name: str | None
    ) -> bool:
        if self.needs_models(model_name):
            return True
        return not bool(self.cfg.get("mathcraft_warmup_notice_done", False))

    def _show_mathcraft_warmup_started_infobar(self) -> None:
        if self._model_warmup_notice_shown:
            return
        self._model_warmup_notice_shown = True
        try:
            InfoBar.info(
                title=tr("MathCraft OCR 正在预热"),
                content=tr("正在初始化模型，请稍候。"),
                parent=self.notification_parent(),
                duration=5200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def _show_mathcraft_cache_repair_infobar(self, detail: str = "") -> None:
        if self._model_cache_repair_notice_shown:
            return
        self._model_cache_repair_notice_shown = True
        content = tr("检测到 MathCraft 模型权重缺失或不完整，正在自动补全。")
        if detail:
            content = f"{content}\n{detail[:180]}"
        try:
            InfoBar.warning(
                title=tr("正在修复模型缓存"),
                content=content,
                parent=self.notification_parent(),
                duration=6500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def cancel_warmup(self):
        self._model_warmup_cancelled = True
        self._model_warmup_callbacks.clear()

    def stop_worker(self):
        if self.model is not None:
            self.model.stop()

    def shutdown(self):
        self.cancel_warmup()
        self.stop_worker()
        thread = self._warmup_thread
        if thread is not None:
            thread.join()
        self._model_warmup_in_progress = False

    @property
    def recognition_backend(self) -> str:
        return self.cfg.get("recognition_backend", "mathcraft")

    @property
    def warming_up(self):
        return self._model_warmup_in_progress

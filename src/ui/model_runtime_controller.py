"""MathCraft and external model runtime mixin."""

from __future__ import annotations

import threading
import os
import sys

from PyQt6.QtCore import QTimer
from qfluentwidgets import InfoBar, InfoBarPosition

from backend.external_model import load_config_from_mapping
from backend.model import classify_mathcraft_failure
from ui.theme_controller import normalize_theme_mode


class ModelRuntimeControllerMixin:
    def _sanitize_model_config(self):
        """Validate and normalize the supported model configuration."""
        try:
            valid_models = {"mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model"}
            default_model = (self.cfg.get("default_model", "") or "").lower()
            desired_model = (self.cfg.get("desired_model", "") or "").lower()
            changed = False
            if default_model not in valid_models:
                self.cfg.set("default_model", "mathcraft")
                changed = True
            if desired_model not in valid_models:
                self.cfg.set("desired_model", "mathcraft")
                changed = True
            mode = (self.cfg.get("mathcraft_mode", "formula") or "formula").lower()
            if mode not in ("formula", "mixed", "text"):
                self.cfg.set("mathcraft_mode", "formula")
                changed = True
            theme_mode = normalize_theme_mode(self.cfg.get("theme_mode", "auto"))
            if self.cfg.get("theme_mode", "auto") != theme_mode:
                self.cfg.set("theme_mode", theme_mode)
                changed = True
            external_defaults = load_config_from_mapping(self.cfg).to_mapping()
            for key, default in external_defaults.items():
                current = self.cfg.get(key, None)
                if current is None:
                    self.cfg.set(key, default)
                    changed = True
            if changed:
                print("[INFO] 已校正当前模型配置。")
        except Exception as e:
            print(f"[WARN] 模型配置校验失败: {e}")

    def _get_preferred_model_for_predict(self) -> str:
        desired = (self.cfg.get("desired_model", "mathcraft") or "mathcraft").lower()
        if desired == "external_model":
            return "external_model"
        mode = (self.cfg.get("mathcraft_mode", "formula") or "formula").lower()
        mode_map = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mode_map.get(mode, "mathcraft")

    def _get_external_model_config(self):
        return load_config_from_mapping(self.cfg)

    def _get_external_model_display_name(self, config=None, result=None) -> str:
        try:
            model_name = str(getattr(result, "model_name", "") or "").strip()
            if model_name:
                return model_name
        except Exception:
            pass
        try:
            if config is None:
                config = self._get_external_model_config()
            model_name = str(getattr(config, "normalized_model_name", lambda: "")() or "").strip()
            if model_name:
                return model_name
            provider = str(getattr(config, "normalized_provider", lambda: "external_model")() or "").strip()
            return provider or "external_model"
        except Exception:
            return "external_model"

    def _is_external_model_configured(self) -> bool:
        cfg = self._get_external_model_config()
        if not cfg.normalized_base_url():
            return False
        if cfg.normalized_provider() == "mineru":
            return bool(cfg.normalized_mineru_endpoint())
        return bool(cfg.normalized_model_name())

    def _get_external_model_required_fields_hint(self) -> str:
        cfg = self._get_external_model_config()
        if cfg.normalized_provider() == "mineru":
            return "请先在设置页填写 Base URL、MinerU 解析接口路径，并点击“测试连接”。"
        return "请先在设置页填写 Base URL、模型名，并点击“测试连接”。"

    def _get_external_model_status_text(self) -> str:
        config = self._get_external_model_config()
        if self._is_external_model_configured():
            model_name = "" if config.normalized_provider() == "mineru" else config.normalized_model_name()
            sig = (
                f"{config.normalized_provider()}|{config.normalized_base_url()}|"
                f"{model_name}|{config.normalized_mineru_endpoint()}"
            )
            tested_sig = str(self.cfg.get("external_model_last_test_signature", "") or "")
            tested_ok = bool(self.cfg.get("external_model_last_test_ok", False))
            if tested_ok and sig == tested_sig:
                return "已连接"
            return "外部模型待连接"
        return "外部模型未配置"

    def _warmup_desired_model(self):
        if not self.model:
            return
        preferred = self._get_preferred_model_for_predict()
        if not preferred:
            return
        if preferred == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            self._report_startup_progress("外部模型模式已启用，跳过 MathCraft 预热")
            return
        self._report_startup_progress("正在后台预热 MathCraft OCR...")
        self._ensure_model_warmup_async(
            preferred_model=preferred,
            announce_success=True,
            success_message="MathCraft OCR 预热完成，可直接识别",
        )

    def _ensure_model_warmup_async(
        self,
        preferred_model: str | None = None,
        on_ready=None,
        on_fail=None,
        announce_success: bool = False,
        success_message: str = "",
    ):
        if not self.model:
            return
        preferred = (preferred_model or self._get_preferred_model_for_predict() or "mathcraft").lower()
        if self.model.is_model_ready(preferred):
            self.current_model = preferred
            self.cfg.set("default_model", preferred)
            self.set_model_status("已加载")
            if callable(on_ready):
                QTimer.singleShot(0, on_ready)
            return

        if callable(on_ready) or callable(on_fail):
            self._model_warmup_callbacks.append((on_ready, on_fail))

        if self._model_warmup_in_progress:
            self.set_model_status(f"预热中 ({preferred})")
            self._report_startup_progress("正在预热 MathCraft OCR...")
            return

        self._model_warmup_in_progress = True
        self._model_warmup_notice_shown = False
        self._model_cache_repair_notice_shown = False
        self.current_model = preferred
        self.cfg.set("default_model", preferred)
        self.desired_model = "mathcraft"
        self.cfg.set("desired_model", "mathcraft")
        try:
            if hasattr(self.model, "set_default_model"):
                self.model.set_default_model(preferred)
        except Exception:
            pass
        self.set_model_status(f"预热中 ({preferred})")
        self._report_startup_progress("正在预热 MathCraft OCR...")
        if self._should_show_mathcraft_warmup_started_infobar(preferred):
            self._show_mathcraft_warmup_started_infobar()

        def worker():
            ok = False
            err = ""
            try:
                self._apply_mathcraft_env()
                ok = bool(self.model._lazy_load_mathcraft())
                if (not ok) and not err:
                    getter = getattr(self.model, "get_error", None)
                    if callable(getter):
                        err = str(getter() or "")
            except Exception as e:
                ok = False
                err = str(e)
            self._pending_model_warmup_result = {
                "ok": ok,
                "err": err,
                "preferred": preferred,
                "announce_success": bool(announce_success),
                "success_message": str(success_message or ""),
                "on_ready": on_ready,
                "on_fail": on_fail,
            }
            self._model_warmup_result_signal.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _apply_model_warmup_result(self):
        data = getattr(self, "_pending_model_warmup_result", None)
        self._pending_model_warmup_result = None
        if not isinstance(data, dict):
            return

        ok = bool(data.get("ok"))
        err = str(data.get("err", "") or "")
        preferred = str(data.get("preferred", self.current_model) or self.current_model)
        announce_success = bool(data.get("announce_success"))
        success_message = str(data.get("success_message", "") or "")
        direct_on_ready = data.get("on_ready")
        direct_on_fail = data.get("on_fail")

        self._model_warmup_in_progress = False
        callbacks = list(self._model_warmup_callbacks)
        self._model_warmup_callbacks.clear()

        if ok:
            self._report_startup_progress("MathCraft OCR 预热完成")
            self.set_model_status("已加载")
            if not bool(self.cfg.get("mathcraft_warmup_notice_done", False)):
                self.cfg.set("mathcraft_warmup_notice_done", True)
            if self.settings_window:
                self.settings_window.update_model_selection()
            if announce_success:
                InfoBar.success(
                    title="模型预热完成",
                    content=success_message or "MathCraft OCR 已就绪",
                    parent=self._get_infobar_parent(),
                    duration=2500,
                    position=InfoBarPosition.TOP,
                )
            for cb_ok, _ in callbacks:
                if callable(cb_ok):
                    try:
                        cb_ok()
                    except Exception:
                        pass
            if callable(direct_on_ready) and not callbacks:
                try:
                    direct_on_ready()
                except Exception:
                    pass
            return

        self._report_startup_progress("模型预热未完成，首次识别时重试")
        self.set_model_status(f"未就绪 ({preferred})")
        fail_info = classify_mathcraft_failure(err)
        if announce_success:
            InfoBar.warning(
                title=fail_info["title"] or "模型预热未完成",
                content=fail_info["user_message"] or "MathCraft OCR 预热失败，将在首次识别时重试",
                parent=self._get_infobar_parent(),
                duration=4200,
                position=InfoBarPosition.TOP,
            )
        fail_msg = fail_info["user_message"] or err or "MathCraft OCR 模型未部署或加载失败。"
        for _, cb_fail in callbacks:
            if callable(cb_fail):
                try:
                    cb_fail(fail_msg)
                except Exception:
                    pass
        if callable(direct_on_fail) and not callbacks:
            try:
                direct_on_fail(fail_msg)
            except Exception:
                pass

    def on_model_changed(self, model_name: str):
        info_parent = self._get_infobar_parent()
        m = (model_name or "").lower()
        valid_modes = ("mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model")
        if m not in valid_modes:
            m = "mathcraft"
        prev_model = str(getattr(self, "current_model", "") or "")
        prev_desired = str(getattr(self, "desired_model", "") or "")
        if m != prev_model and self.is_recognition_busy(source="mode_switch"):
            self._cancel_active_recognition_for_mode_switch()

        if m == prev_model:
            if m == "external_model" and prev_desired == "external_model":
                self.set_model_status(self._get_external_model_status_text())
                return
            if m.startswith("mathcraft") and prev_desired == "mathcraft":
                if self.model and self.model.is_model_ready(m):
                    self.set_model_status("已加载")
                else:
                    self.set_model_status(f"待识别时加载 ({m})")
                return

        mode_names = {
            "mathcraft": "MathCraft 公式识别",
            "mathcraft_text": "MathCraft 纯文字识别",
            "mathcraft_mixed": "MathCraft 混合识别",
            "external_model": "外部模型",
        }
        mode_display = mode_names.get(m, m)
        InfoBar.success(
            title="模式切换成功",
            content=f"已切换到 {mode_display}",
            parent=info_parent,
            duration=3000,
            position=InfoBarPosition.TOP,
        )

        self.current_model = m
        self.cfg.set("default_model", m)
        self.desired_model = "external_model" if m == "external_model" else "mathcraft"
        self.cfg.set("desired_model", self.desired_model)
        if m.startswith("mathcraft"):
            mode_map = {
                "mathcraft": "formula",
                "mathcraft_mixed": "mixed",
                "mathcraft_text": "text",
            }
            self.cfg.set("mathcraft_mode", mode_map.get(m, "formula"))

        if m == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            if self.settings_window:
                self.settings_window.update_model_selection()
            if not self._is_external_model_configured():
                InfoBar.warning(
                    title="外部模型未配置",
                    content=self._get_external_model_required_fields_hint(),
                    parent=info_parent,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                )
            return

        if self.model:
            if self.model.is_model_ready(m):
                self.set_model_status("已加载")
            else:
                self.set_model_status(f"预热中 ({m})")
        else:
            self.set_model_status(f"预热中 ({m})")

        if self.settings_window:
            self.settings_window.update_model_selection()

        if m.startswith("mathcraft"):
            if self.model and self.model.is_model_ready(m):
                self.set_model_status("已加载")
            else:
                self.set_model_status(f"待识别时加载 ({m})")
            return

    def _mathcraft_profile_for_model(self, model_name: str | None) -> str:
        model = str(model_name or "mathcraft").strip().lower()
        if model == "mathcraft_text":
            return "text"
        if model == "mathcraft_mixed":
            return "mixed"
        return "formula"

    def _mathcraft_required_models_incomplete(self, model_name: str | None) -> bool:
        try:
            from mathcraft_ocr.cache import inspect_model_roots, resolve_model_roots
            from mathcraft_ocr.manifest import load_manifest
            from mathcraft_ocr.profiles import PROFILE_MODEL_IDS

            profile = self._mathcraft_profile_for_model(model_name)
            manifest = load_manifest()
            roots = resolve_model_roots()
            for model_id in PROFILE_MODEL_IDS.get(profile, ()):
                spec = manifest.models.get(model_id)
                if spec is None:
                    return True
                if not inspect_model_roots(roots, spec).complete:
                    return True
            return False
        except Exception:
            return False

    def _apply_mathcraft_env(self):
        env_pyexe = ""
        try:

            pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
            if not pyexe or not os.path.exists(pyexe):
                pyexe = sys.executable
            if pyexe and os.path.exists(pyexe):
                env_pyexe = pyexe
        except Exception:
            pass
        try:
            os.environ.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        except Exception:
            pass
        try:
            new_state = (
                (env_pyexe or os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip(),
            )
            old_state = getattr(self, "_mathcraft_env_state", None)
            self._mathcraft_env_state = new_state
            old_key = old_state
            new_key = new_state
            if old_state is not None and old_key != new_key:
                self._restart_mathcraft_worker("环境切换")
        except Exception:
            pass

    def _restart_mathcraft_worker(self, reason: str = "环境更新"):
        m = getattr(self, "model", None)
        if not m:
            return
        try:
            if hasattr(m, "_stop_mathcraft_worker"):
                m._stop_mathcraft_worker()
        except Exception:
            pass
        try:
            m._ready = False
            m._import_failed = False
        except Exception:
            pass
        try:
            print(f"[INFO] MathCraft OCR 运行进程已重启: {reason}")
        except Exception:
            pass

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QLineEdit
from qfluentwidgets import ComboBox

from backend.external_model import ExternalModelConnectionWorker, get_preset, load_config_from_mapping
from ui.settings_external_help import ExternalModelHelpWindow


class SettingsExternalModelMixin:

    def _set_combo_value(self, combo: ComboBox, value: str):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                prev = combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(prev)
                return

    def _set_lineedit_value(self, widget: QLineEdit, value: str):
        prev = widget.blockSignals(True)
        widget.setText(str(value or ""))
        widget.blockSignals(prev)

    def _get_external_combo_value(self, combo: ComboBox, default: str) -> str:
        idx = combo.currentIndex()
        if idx >= 0:
            value = combo.itemData(idx)
            if value is not None:
                return str(value)
        return default

    def _init_external_model_config(self):
        cfg = None
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                cfg = self.parent().cfg
        except Exception:
            cfg = None
        config = load_config_from_mapping(cfg or {})
        data = config.to_mapping()
        self._set_combo_value(self.external_provider_combo, data["external_model_provider"])
        self._set_combo_value(self.external_output_combo, data["external_model_output_mode"])
        self._set_combo_value(self.external_prompt_combo, data["external_model_prompt_template"])
        self._set_combo_value(self.external_preset_combo, data["external_model_preset"])
        self._set_lineedit_value(self.external_base_url_input, data["external_model_base_url"])
        self._set_lineedit_value(self.external_model_name_input, data["external_model_model_name"])
        self._set_lineedit_value(self.external_api_key_input, data["external_model_api_key"])
        self._set_lineedit_value(self.external_timeout_input, str(data["external_model_timeout_sec"]))
        self._set_lineedit_value(self.external_custom_prompt_input, data["external_model_custom_prompt"])
        self._set_lineedit_value(self.external_mineru_endpoint_input, data["external_model_mineru_endpoint"])
        self._set_lineedit_value(self.external_mineru_test_endpoint_input, data["external_model_mineru_test_endpoint"])
        self._on_external_preset_changed()
        self._update_external_provider_visibility()
        self._update_external_model_status()

    def _collect_external_model_config(self):
        config = load_config_from_mapping({})
        config.provider = self._get_external_combo_value(self.external_provider_combo, "openai_compatible")
        config.base_url = self.external_base_url_input.text().strip()
        config.model_name = self.external_model_name_input.text().strip()
        config.api_key = self.external_api_key_input.text().strip()
        config.output_mode = self._get_external_combo_value(self.external_output_combo, "latex")
        config.prompt_template = self._get_external_combo_value(self.external_prompt_combo, "ocr_formula_v1")
        config.custom_prompt = self.external_custom_prompt_input.text().strip()
        config.preset = self._get_external_combo_value(self.external_preset_combo, "")
        config.mineru_endpoint = self.external_mineru_endpoint_input.text().strip()
        config.mineru_test_endpoint = self.external_mineru_test_endpoint_input.text().strip()
        try:
            config.timeout_sec = int((self.external_timeout_input.text() or "60").strip())
        except Exception:
            config.timeout_sec = 60
        return config

    def _external_config_signature(self, config) -> str:
        provider = config.normalized_provider()
        base_url = config.normalized_base_url()
        model_name = config.normalized_model_name()
        mineru_endpoint = config.normalized_mineru_endpoint()
        return f"{provider}|{base_url}|{model_name}|{mineru_endpoint}"

    def _is_external_required_fields_ready(self, config) -> bool:
        provider = config.normalized_provider()
        if not config.normalized_base_url():
            return False
        if provider == "mineru":
            return bool(config.normalized_mineru_endpoint())
        return bool(config.normalized_model_name())

    def _update_external_provider_visibility(self):
        config = self._collect_external_model_config()
        is_mineru = config.normalized_provider() == "mineru"
        self.external_mineru_endpoint_input.setVisible(is_mineru)
        self.external_mineru_test_endpoint_input.setVisible(is_mineru)
        if is_mineru:
            self.external_model_name_input.setPlaceholderText("可选：模型名（MinerU 原生接口通常可留空）")
        else:
            self.external_model_name_input.setPlaceholderText("必填：模型名，例如 qwen2.5vl:7b；必须与服务中的真实名称一致")

    def _on_external_provider_changed(self, *_args):
        self._update_external_provider_visibility()

    def _notify_parent_external_status_changed(self):
        parent = self.parent()
        if parent is None:
            return
        try:
            preferred = ""
            if hasattr(parent, "_get_preferred_model_for_predict"):
                preferred = str(parent._get_preferred_model_for_predict() or "").strip().lower()
            current = str(getattr(parent, "current_model", "") or "").strip().lower()
            if current == "external_model" or preferred == "external_model":
                if hasattr(parent, "set_model_status") and hasattr(parent, "_get_external_model_status_text"):
                    parent.set_model_status(parent._get_external_model_status_text())
                elif hasattr(parent, "refresh_status_label"):
                    parent.refresh_status_label()
        except Exception:
            pass

    def _save_external_model_config(self):
        config = self._collect_external_model_config()
        try:
            parent_cfg = getattr(self.parent(), "cfg", None)
            if parent_cfg is not None:
                for key, value in config.to_mapping().items():
                    parent_cfg.set(key, value)
                current_sig = self._external_config_signature(config)
                tested_sig = str(parent_cfg.get("external_model_last_test_signature", "") or "")
                if tested_sig != current_sig:
                    parent_cfg.set("external_model_last_test_ok", False)
                    parent_cfg.set("external_model_last_test_message", "")
        except Exception:
            pass
        self._update_external_provider_visibility()
        self._update_external_model_status()
        self._notify_parent_external_status_changed()

    def _on_external_config_changed(self, *_args):
        self._save_external_model_config()

    def _on_external_preset_changed(self, *_args):
        preset = get_preset(self._get_external_combo_value(self.external_preset_combo, ""))
        if preset:
            self.external_hint.setText(str(preset.get("hint") or ""))
        else:
            self.external_hint.setText("必填项只有协议、Base URL、模型名。若测试提示 model not found / unknown model，通常就是模型名填写不正确。")
        self._save_external_model_config()

    def _apply_external_preset(self):
        preset = get_preset(self._get_external_combo_value(self.external_preset_combo, ""))
        if not preset:
            self._show_info("未选择预设", "请选择一个推荐预设后再应用。", "warning")
            return
        self._set_combo_value(self.external_provider_combo, str(preset.get("provider") or "openai_compatible"))
        self._set_lineedit_value(self.external_base_url_input, str(preset.get("base_url") or ""))
        self._set_lineedit_value(self.external_model_name_input, str(preset.get("model_name") or ""))
        self._set_combo_value(self.external_output_combo, str(preset.get("output_mode") or "latex"))
        self._set_combo_value(self.external_prompt_combo, str(preset.get("prompt_template") or "ocr_formula_v1"))
        self._set_lineedit_value(self.external_mineru_endpoint_input, str(preset.get("mineru_endpoint") or "/file_parse"))
        self._set_lineedit_value(self.external_mineru_test_endpoint_input, str(preset.get("mineru_test_endpoint") or "/health"))
        self.external_hint.setText(str(preset.get("hint") or ""))
        self._save_external_model_config()
        self._show_info("预设已应用", "已填入推荐配置，请按你的本地服务实际情况检查模型名。", "success")

    def _test_external_model_connection(self):
        if self._external_test_thread and self._external_test_thread.isRunning():
            self._show_info("测试进行中", "当前已有一个测试连接任务在后台运行。", "warning")
            return
        config = self._collect_external_model_config()
        self._save_external_model_config()
        self.external_test_btn.setEnabled(False)
        self.external_test_btn.setText("测试中...")
        self._update_external_model_status(test_message="正在后台测试连接，请稍候...")

        self._external_test_thread = QThread(self)
        self._external_test_worker = ExternalModelConnectionWorker(config)
        self._external_test_worker.moveToThread(self._external_test_thread)

        def _cleanup():
            try:
                self.external_test_btn.setEnabled(True)
                self.external_test_btn.setText("测试连接")
            except Exception:
                pass
            if self._external_test_worker:
                self._external_test_worker.deleteLater()
                self._external_test_worker = None
            if self._external_test_thread:
                self._external_test_thread.deleteLater()
                self._external_test_thread = None

        def _on_ok(ok: bool, message: str):
            cfg = getattr(self.parent(), "cfg", None)
            if cfg is not None:
                try:
                    cfg.set("external_model_last_test_ok", bool(ok))
                    cfg.set("external_model_last_test_signature", self._external_config_signature(config))
                    cfg.set("external_model_last_test_message", str(message or ""))
                except Exception:
                    pass
            self._update_external_model_status(test_message=message if ok else "测试未通过")
            self._show_info("测试成功", message or "连接成功，本地服务可访问。", "success")
            self._notify_parent_external_status_changed()

        def _on_fail(message: str):
            pretty = self._format_external_test_error(message)
            cfg = getattr(self.parent(), "cfg", None)
            if cfg is not None:
                try:
                    cfg.set("external_model_last_test_ok", False)
                    cfg.set("external_model_last_test_signature", self._external_config_signature(config))
                    cfg.set("external_model_last_test_message", str(pretty or ""))
                except Exception:
                    pass
            self._update_external_model_status(test_message=pretty)
            self._show_info("测试失败", pretty, "error")
            self._notify_parent_external_status_changed()

        self._external_test_thread.started.connect(self._external_test_worker.run)
        self._external_test_worker.finished.connect(_on_ok)
        self._external_test_worker.failed.connect(_on_fail)
        self._external_test_worker.finished.connect(self._external_test_thread.quit)
        self._external_test_worker.failed.connect(self._external_test_thread.quit)
        self._external_test_thread.finished.connect(_cleanup)
        self._external_test_thread.start()

    def _format_external_test_error(self, message: str) -> str:
        text = str(message or "").strip()
        low = text.lower()
        if "model not found" in low or "unknown model" in low or '"error":"model' in low:
            return f"{text}\n提示：模型名填写错误或该模型未在服务中加载。"
        if "401" in low or "unauthorized" in low or "invalid api key" in low:
            return f"{text}\n提示：请检查 API Key 是否必填、是否填写正确。"
        if "404" in low:
            return f"{text}\n提示：请检查 Base URL、协议类型以及服务端路由是否正确。"
        if "timeout" in low:
            return f"{text}\n提示：服务响应较慢，可提高超时或先确认模型是否已完成加载。"
        return text

    def _show_external_model_help(self):
        if self._external_help_window is None:
            self._external_help_window = ExternalModelHelpWindow(self)
            self._external_help_window.destroyed.connect(lambda: setattr(self, "_external_help_window", None))
        self._external_help_window.show()
        self._external_help_window.raise_()
        self._external_help_window.activateWindow()

    def _update_external_model_status(self, test_message: str = ""):
        config = self._collect_external_model_config()
        provider = config.normalized_provider()
        base_url = config.normalized_base_url()
        model_name = config.normalized_model_name()
        cfg = getattr(self.parent(), "cfg", None)
        current_sig = self._external_config_signature(config)
        tested_ok = False
        tested_sig = ""
        saved_message = ""
        if cfg is not None:
            try:
                tested_ok = bool(cfg.get("external_model_last_test_ok", False))
                tested_sig = str(cfg.get("external_model_last_test_signature", "") or "")
                saved_message = str(cfg.get("external_model_last_test_message", "") or "")
            except Exception:
                tested_ok = False
                tested_sig = ""
                saved_message = ""
        if not base_url:
            status = "状态：未配置。必填项缺少 Base URL。"
        elif provider != "mineru" and not model_name:
            status = "状态：未配置。必填项缺少模型名。"
        else:
            provider_label = "MinerU" if provider == "mineru" else ("Ollama" if provider == "ollama" else "OpenAI-compatible")
            if tested_sig == current_sig:
                state_text = "已连接" if tested_ok else "连接失败"
            else:
                state_text = "已配置，尚未测试连接"
            if provider == "mineru":
                status = (
                    f"状态：{state_text}。协议 {provider_label}，路径 {config.normalized_mineru_endpoint()}，"
                    "原生解析"
                )
            else:
                status = f"状态：{state_text}。协议 {provider_label}，模型 {model_name}"
        if test_message:
            status = f"{status}\n最近一次测试：{test_message}"
        elif saved_message and tested_sig == current_sig:
            status = f"{status}\n最近一次测试：{saved_message}"
        self.external_status.setText(status)

from localization.manager import translate as tr


class SettingsMathCraftMixin:
    def _init_model_combo(self):
        current = self.context.models.desired_model
        if not current:
            current = self.context.models.current_model
        if current and str(current).startswith("mathcraft"):
            current_key = "mathcraft"
        else:
            current_key = current
        for i, (key, _) in enumerate(self._model_options):
            if key == current_key:
                self.model_combo.setCurrentIndex(i)
                break
        self._init_mathcraft_mode()
        self._init_external_model_config()
        self._update_mathcraft_visibility()

    def _on_model_combo_changed(self, index: int):
        if getattr(self, "_model_selection_syncing", False):
            return
        if index < 0 or index >= len(self._model_options):
            return
        key, _ = self._model_options[index]
        if key == "external_model":
            self.select_model("external_model")
        else:
            mode_key = self._get_mathcraft_mode_key()
            self.select_model(self._mathcraft_mode_to_model(mode_key))
        self._update_model_desc()
        self._update_mathcraft_visibility()

    def _init_mathcraft_mode(self):
        mode = "formula"
        mode = self.context.cfg.get("mathcraft_mode", "formula")
        if mode not in {"formula", "mixed", "text"}:
            mode = "formula"
        for i in range(self.mathcraft_mode_combo.count()):
            if self.mathcraft_mode_combo.itemData(i) == mode:
                prev = self.mathcraft_mode_combo.blockSignals(True)
                self.mathcraft_mode_combo.setCurrentIndex(i)
                self.mathcraft_mode_combo.blockSignals(prev)
                break

    def _mathcraft_mode_to_model(self, mode_key: str) -> str:
        mapping = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mapping.get(mode_key, "mathcraft")

    def _get_mathcraft_mode_key(self) -> str:
        idx = self.mathcraft_mode_combo.currentIndex()
        if idx >= 0:
            key = self.mathcraft_mode_combo.itemData(idx)
            if key:
                return key
        return "formula"

    def _is_mathcraft_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "mathcraft"
        return False

    def _is_external_model_selected(self) -> bool:
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
            return key == "external_model"
        return False

    def _on_mathcraft_mode_changed(self, index: int):
        if index < 0:
            return
        mode_key = self.mathcraft_mode_combo.itemData(index)
        self.context.cfg.set("mathcraft_mode", mode_key)
        if not self._is_mathcraft_selected():
            return
        self.select_model(self._mathcraft_mode_to_model(mode_key))

    def _update_mathcraft_visibility(self):
        key = None
        idx = self.model_combo.currentIndex()
        if idx >= 0 and idx < len(self._model_options):
            key, _ = self._model_options[idx]
        visible = key == "mathcraft"
        external_visible = key == "external_model"
        try:
            self.mathcraft_mode_widget.setVisible(visible)
            self.external_model_widget.setVisible(external_visible)
            self.lbl_compute_mode.setVisible(visible)
        except Exception:
            pass

    def select_model(self, model_name: str):
        self.model_changed.emit(model_name)
        self._update_compute_mode_label()

    def _set_compute_mode_text(self, text: str, state: str) -> None:
        self.lbl_compute_mode.setText(text)
        self._compute_mode_state = state
        self.apply_theme_styles(force=True)

    def _apply_compute_mode_from_info(self, info: dict) -> bool:
        if not isinstance(info, dict) or not info:
            return False
        if not info.get("present"):
            self._set_compute_mode_text(tr("⚪ 计算模式未知"), "unknown")
            return True
        gpu_active = str(info.get("device") or "").strip().lower() == "gpu"
        device_name = (
            str(info.get("device_name") or "").strip()
            if bool(info.get("device_verified"))
            else ""
        )
        if gpu_active:
            if device_name:
                self._set_compute_mode_text(
                    tr("🟢 GPU 模式: {device}").format(device=device_name), "gpu"
                )
            else:
                self._set_compute_mode_text(tr("🟢 GPU 模式"), "gpu")
            return True
        if device_name:
            self._set_compute_mode_text(
                tr("🟡 CPU 模式: {device}").format(device=device_name), "cpu"
            )
        else:
            self._set_compute_mode_text(tr("🟡 CPU 模式"), "cpu")
        return True

    def _active_mathcraft_provider_info(self) -> dict:
        try:
            model = getattr(self.context.models, "model", None)
            info = getattr(model, "provider_info", None)
            if isinstance(info, dict) and info:
                return {"present": True, **info}
        except Exception:
            pass
        return {}

    def _update_compute_mode_label(self, *_args):
        info = self._active_mathcraft_provider_info()
        if not self._apply_compute_mode_from_info(info):
            self._set_compute_mode_text(tr("⚪ 计算模式未知"), "unknown")

    def update_model_selection(self):
        if getattr(self, "_model_selection_syncing", False):
            return
        current = "mathcraft"
        try:
            current = str(self.context.models.desired_model or "mathcraft")
        except Exception:
            current = "mathcraft"
        target = "external_model" if current == "external_model" else "mathcraft"
        self._model_selection_syncing = True
        try:
            for i, (key, _) in enumerate(self._model_options):
                if key == target:
                    self.model_combo.blockSignals(True)
                    self.model_combo.setCurrentIndex(i)
                    self.model_combo.blockSignals(False)
                    break
            self._init_mathcraft_mode()
            self._init_external_model_config()
            self._update_model_desc()
            self._update_mathcraft_visibility()
        finally:
            self._model_selection_syncing = False

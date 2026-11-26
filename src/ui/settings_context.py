"""Explicit application dependencies used by the settings presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Protocol

    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QLabel, QLineEdit, QWidget
    from qfluentwidgets import ComboBox, PrimaryPushButton, PushButton

    from backend.external_model import ExternalModelConfig
    from runtime.background_task import BackgroundTask
    from runtime.config_manager import ConfigManager
    from ui.controllers.app_lifecycle import AppLifecycleController
    from ui.controllers.automation_api import AutomationApiController
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.status import StatusController
    from ui.controllers.theme import ThemeController
    from ui.resource_diagnostics import ResourceDiagnosticsDialog
    from ui.settings_external_help import ExternalModelHelpWindow


@dataclass(frozen=True)
class SettingsContext:
    cfg: ConfigManager
    models: ModelRuntimeController
    status: StatusController
    theme: ThemeController
    lifecycle: AppLifecycleController
    automation_api: AutomationApiController


if TYPE_CHECKING:

    class SettingsView(Protocol):
        """Shared controls and actions required by the settings mixins."""

        context: SettingsContext
        model_combo: ComboBox
        mathcraft_mode_combo: ComboBox
        mathcraft_mode_widget: QWidget
        external_model_widget: QWidget
        lbl_compute_mode: QLabel
        lbl_model_desc: QLabel
        _model_options: list[tuple[str, str]]
        _model_selection_syncing: bool
        _compute_mode_state: str

        theme_mode_combo: ComboBox
        ui_language_combo: ComboBox
        runtime_log_button: PushButton
        automation_api_button: PushButton
        _theme_mode_values: list[str]
        _ui_language_values: list[str]
        _theme_is_dark_cached: bool | None

        external_provider_combo: ComboBox
        external_prompt_combo: ComboBox
        external_prompt_label: QLabel
        external_preset_combo: ComboBox
        external_base_url_input: QLineEdit
        external_model_name_input: QLineEdit
        external_api_key_input: QLineEdit
        external_timeout_input: QLineEdit
        external_custom_prompt_input: QLineEdit
        external_mineru_endpoint_input: QLineEdit
        external_mineru_test_endpoint_input: QLineEdit
        external_test_btn: PrimaryPushButton
        _external_test_task: BackgroundTask | None
        _external_help_window: ExternalModelHelpWindow | None
        _resource_diagnostics_dialog: ResourceDiagnosticsDialog | None

        def palette(self) -> QPalette: ...
        def _show_info(self, title: str, content: str, level: str = "info") -> None: ...
        def _update_model_desc(self) -> None: ...
        def _init_mathcraft_mode(self) -> None: ...
        def _update_mathcraft_visibility(self) -> None: ...
        def _mathcraft_mode_to_model(self, mode_key: str | None) -> str: ...
        def _get_mathcraft_mode_key(self) -> str: ...
        def _is_mathcraft_selected(self) -> bool: ...
        def select_model(self, model_name: str) -> None: ...
        def _update_compute_mode_label(self, *_args: object) -> None: ...
        def _set_compute_mode_text(self, text: str, state: str) -> None: ...
        def _active_mathcraft_provider_info(self) -> dict: ...
        def _apply_compute_mode_from_info(self, info: dict) -> bool: ...
        def apply_theme_styles(self, force: bool = False) -> None: ...
        def _is_dark_mode(self) -> bool: ...
        def _normalize_theme_mode(self, value: str | None) -> str: ...
        def _theme_tokens(self) -> dict: ...
        def _compute_label_color(self) -> str: ...
        def _style_startup_button(
            self, button: PushButton, text_color: str, disabled_color: str
        ) -> None: ...
        def _init_external_model_config(self) -> None: ...
        def _set_combo_value(self, combo: ComboBox, value: str) -> None: ...
        def _set_lineedit_value(self, widget: QLineEdit, value: str) -> None: ...
        def _get_external_combo_value(self, combo: ComboBox, default: str) -> str: ...
        def _collect_external_model_config(self) -> ExternalModelConfig: ...
        def _update_external_provider_visibility(self) -> None: ...
        def _notify_parent_external_status_changed(self) -> None: ...
        def _save_external_model_config(self) -> None: ...
        def _format_external_test_error(self, error: object) -> str: ...

"""Explicit application dependencies used by the settings presentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.config_manager import ConfigManager
    from ui.controllers.app_lifecycle import AppLifecycleController
    from ui.controllers.automation_api import AutomationApiController
    from ui.controllers.model_runtime import ModelRuntimeController
    from ui.controllers.status import StatusController
    from ui.controllers.theme import ThemeController


@dataclass(frozen=True)
class SettingsContext:
    cfg: ConfigManager
    models: ModelRuntimeController
    status: StatusController
    theme: ThemeController
    lifecycle: AppLifecycleController
    automation_api: AutomationApiController

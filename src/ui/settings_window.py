from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog

from ui.settings_external_model_mixin import SettingsExternalModelMixin
from ui.settings_layout_builder import SettingsLayoutMixin
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin
from ui.settings_resources_mixin import SettingsResourcesMixin
from ui.settings_theme_mixin import SettingsThemeMixin


class SettingsWindow(
    SettingsLayoutMixin,
    SettingsThemeMixin,
    SettingsMathCraftMixin,
    SettingsResourcesMixin,
    SettingsExternalModelMixin,
    QDialog,
):
    def __init__(self, parent, *, context):
        self.context = context
        super().__init__(parent)

    "Settings window."
    model_changed = pyqtSignal(str)

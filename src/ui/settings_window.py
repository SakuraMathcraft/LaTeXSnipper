from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog

from ui.settings_environment_mixin import SettingsEnvironmentMixin
from ui.settings_external_model_mixin import SettingsExternalModelMixin
from ui.settings_latex_mixin import SettingsLatexMixin
from ui.settings_layout_builder import SettingsLayoutMixin
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin
from ui.settings_theme_mixin import SettingsThemeMixin


class SettingsWindow(
    SettingsLayoutMixin,
    SettingsThemeMixin,
    SettingsLatexMixin,
    SettingsMathCraftMixin,
    SettingsEnvironmentMixin,
    SettingsExternalModelMixin,
    QDialog,
):
    """Settings window."""

    model_changed = pyqtSignal(str)
    compute_mode_probe_done = pyqtSignal(object, str)
    mathcraft_pkg_probe_done = pyqtSignal(bool)
    latex_path_test_done = pyqtSignal(bool, str, str, str, str)
    latex_auto_detect_done = pyqtSignal(bool, str, str)
    typst_path_test_done = pyqtSignal(bool, str, str, str)
    typst_auto_detect_done = pyqtSignal(bool, str, str)

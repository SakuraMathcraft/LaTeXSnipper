"""Settings actions for installation diagnostics and desktop model resources."""


class SettingsResourcesMixin:
    def _show_model_resources(self):
        from ui.model_resources_dialog import ModelResourcesDialog
        from ui.window_helpers import show_normal_window

        dialog: ModelResourcesDialog | None = getattr(
            self, "_model_resources_dialog", None
        )
        if dialog is None:
            dialog = ModelResourcesDialog(self)
            self._model_resources_dialog = dialog
        show_normal_window(dialog)

    def _show_resource_diagnostics(self):
        from ui.resource_diagnostics import ResourceDiagnosticsDialog

        dialog = getattr(self, "_resource_diagnostics_dialog", None)
        if dialog is None:
            dialog = ResourceDiagnosticsDialog(self.context.models, self)
            self._resource_diagnostics_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _show_info(self, title: str, content: str, level: str = "info"):
        from qfluentwidgets import InfoBar, InfoBarPosition

        getattr(InfoBar, level, InfoBar.info)(
            title=title,
            content=content,
            parent=self,
            duration=4000,
            position=InfoBarPosition.TOP,
        )

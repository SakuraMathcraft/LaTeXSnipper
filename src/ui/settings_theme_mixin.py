from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QColor, QPalette

from localization.language import normalize_ui_language
from localization.manager import translate as tr


class SettingsThemeMixin:
    def _is_dark_mode(self) -> bool:
        try:
            from qfluentwidgets import isDarkTheme

            return bool(isDarkTheme())
        except Exception:
            pal = self.palette().window().color()
            return ((pal.red() + pal.green() + pal.blue()) / 3.0) < 128

    def _normalize_theme_mode(self, value: str | None) -> str:
        mode = str(value or "auto").strip().lower()
        return mode if mode in self._theme_mode_values else "auto"

    def _init_theme_mode_combo(self):
        mode = "auto"
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                mode = self._normalize_theme_mode(
                    self.parent().cfg.get("theme_mode", "auto")
                )
        except Exception:
            mode = "auto"
        try:
            idx = self._theme_mode_values.index(mode)
        except Exception:
            idx = 0
        prev = self.theme_mode_combo.blockSignals(True)
        self.theme_mode_combo.setCurrentIndex(idx)
        self.theme_mode_combo.blockSignals(prev)

    def _on_theme_mode_changed(self, index: int):
        mode = "auto"
        if index >= 0:
            value = self.theme_mode_combo.itemData(index)
            mode = self._normalize_theme_mode(value)
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("theme_mode", mode)
        except Exception:
            pass
        try:
            if self.parent() and hasattr(self.parent(), "apply_app_theme_mode"):
                self.parent().apply_app_theme_mode(mode, refresh_preview=True)
        except Exception:
            pass
        mapping = {"light": tr("浅色"), "dark": tr("深色"), "auto": tr("跟随系统")}
        self._show_info(
            tr("主题已应用"),
            tr("当前主题: {theme}").format(theme=mapping.get(mode, mode)),
            "success",
        )

    def _init_ui_language_combo(self) -> None:
        language = "auto"
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                language = normalize_ui_language(
                    self.parent().cfg.get("ui_language", "auto")
                )
        except Exception:
            language = "auto"
        try:
            index = self._ui_language_values.index(language)
        except ValueError:
            index = 0
        previous = self.ui_language_combo.blockSignals(True)
        self.ui_language_combo.setCurrentIndex(index)
        self.ui_language_combo.blockSignals(previous)

    def _on_ui_language_changed(self, index: int) -> None:
        language = "auto"
        if index >= 0:
            language = normalize_ui_language(self.ui_language_combo.itemData(index))
        try:
            if self.parent() and hasattr(self.parent(), "cfg"):
                self.parent().cfg.set("ui_language", language)
        except Exception:
            pass
        self._show_info(
            tr("界面语言已保存"),
            tr("重新启动 LaTeXSnipper 后生效。"),
            "info",
        )

    def _theme_tokens(self) -> dict:
        if self._is_dark_mode():
            return {
                "text": "#e7ebf0",
                "muted": "#b6beca",
                "compute_gpu": "#7bd88f",
                "compute_cpu": "#ffb35c",
                "compute_unknown": "#9ea7b3",
            }
        return {
            "text": "#222222",
            "muted": "#666666",
            "compute_gpu": "#2e7d32",
            "compute_cpu": "#f57c00",
            "compute_unknown": "#666666",
        }

    def _compute_label_color(self) -> str:
        t = self._theme_tokens()
        if self._compute_mode_state == "gpu":
            return t["compute_gpu"]
        if self._compute_mode_state == "cpu":
            return t["compute_cpu"]
        return t["compute_unknown"]

    def _style_startup_button(
        self, button, text_color: str, disabled_color: str
    ) -> None:
        pal = button.palette()
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            pal.setColor(group, QPalette.ColorRole.WindowText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.ButtonText, QColor(text_color))
            pal.setColor(group, QPalette.ColorRole.Text, QColor(text_color))
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(disabled_color),
        )
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(disabled_color),
        )
        pal.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor(disabled_color),
        )
        button.setPalette(pal)

    def apply_theme_styles(self, force: bool = False):
        dark = self._is_dark_mode()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._theme_tokens()
        if hasattr(self, "lbl_model_desc") and self.lbl_model_desc is not None:
            self.lbl_model_desc.setStyleSheet(
                f"color: {t['muted']}; font-size: 11px; padding: 4px;"
            )
        if hasattr(self, "lbl_latex_desc") and self.lbl_latex_desc is not None:
            self.lbl_latex_desc.setStyleSheet(
                f"color: {t['muted']}; font-size: 10px; padding: 4px;"
            )
        if hasattr(self, "lbl_compute_mode") and self.lbl_compute_mode is not None:
            self.lbl_compute_mode.setStyleSheet(
                f"color: {self._compute_label_color()}; font-size: 11px; padding: 4px;"
            )
        if hasattr(self, "runtime_log_button") and self.runtime_log_button is not None:
            self._style_startup_button(self.runtime_log_button, t["text"], t["muted"])
        if (
            hasattr(self, "automation_api_button")
            and self.automation_api_button is not None
        ):
            self._style_startup_button(
                self.automation_api_button, t["text"], t["muted"]
            )

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self.apply_theme_styles()
        except Exception:
            pass
        return result

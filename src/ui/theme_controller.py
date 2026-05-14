"""Theme helpers and MainWindow theme mixin."""

from __future__ import annotations

import json

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from preview.math_preview import formula_label_theme_tokens, is_dark_ui
from runtime.app_paths import app_config_path
from runtime.runtime_logging import refresh_runtime_log_dialog_theme


def apply_theme(mode: str = "AUTO") -> bool:
    """Apply the QFluentWidgets theme safely even if QConfig has been destroyed."""
    try:
        import importlib
        import qfluentwidgets.common.config as cfg
        import qfluentwidgets.common.style_sheet as ss

        theme = getattr(cfg.Theme, mode)
        try:
            ss.setTheme(theme)
            return True
        except RuntimeError:
            cfg = importlib.reload(cfg)
            ss = importlib.reload(ss)
            theme = getattr(cfg.Theme, mode)
            ss.setTheme(theme)
            return True
    except Exception as e:
        print(f"[WARN] 应用主题失败: {e}")
        return False


def normalize_theme_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    return mode if mode in ("light", "dark", "auto") else "auto"


def apply_theme_mode(mode: str | None) -> bool:
    normalized = normalize_theme_mode(mode)
    map_mode = {
        "light": "LIGHT",
        "dark": "DARK",
        "auto": "AUTO",
    }
    return apply_theme(map_mode.get(normalized, "AUTO"))


def read_theme_mode_from_config() -> str:
    try:
        cfg_path = app_config_path()
        if not cfg_path.exists():
            return "auto"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return "auto"
        return normalize_theme_mode(data.get("theme_mode", "auto"))
    except Exception:
        return "auto"


def main_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "title": "#8ec5ff",
            "muted": "#95a0af",
        }
    return {
        "title": "#1976d2",
        "muted": "#888888",
    }


def history_row_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "index": "#8ec5ff",
            "name": "#ffb74d",
        }
    return {
        "index": "#1976d2",
        "name": "#f57c00",
    }


class ThemeControllerMixin:
    def _main_theme_tokens(self) -> dict:
        return main_theme_tokens()

    def _apply_theme_styles(self, force: bool = False):
        dark = is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._main_theme_tokens()
        title_style = f"font-size: 14px; font-weight: 500; color: {t['title']}; padding: 4px 0;"
        try:
            if hasattr(self, "history_title_label"):
                self.history_title_label.setStyleSheet(title_style)
            if hasattr(self, "editor_title_label"):
                self.editor_title_label.setStyleSheet(title_style)
            if hasattr(self, "preview_title_label"):
                self.preview_title_label.setStyleSheet(title_style)
            if hasattr(self, "preview_fallback_label") and self.preview_fallback_label:
                self.preview_fallback_label.setStyleSheet(f"color: {t['muted']}; padding: 20px;")
        except Exception:
            pass
        try:
            if self.settings_window and self.settings_window.isVisible() and hasattr(self.settings_window, "apply_theme_styles"):
                self.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            self._refresh_preview()
        except Exception:
            pass
        try:
            self._refresh_history_rows_theme()
        except Exception:
            pass

    def _schedule_auto_theme_refresh(self) -> None:
        if getattr(self, "_theme_mode", "auto") != "auto":
            return
        try:
            if hasattr(self, "_auto_theme_refresh_timer") and self._auto_theme_refresh_timer is not None:
                self._auto_theme_refresh_timer.start()
        except Exception:
            pass

    def _on_auto_theme_refresh_timeout(self) -> None:
        if getattr(self, "_theme_mode", "auto") != "auto":
            return
        if getattr(self, "_auto_theme_sync_in_progress", False):
            return
        self._auto_theme_sync_in_progress = True
        try:
            dark_by_palette = False
            try:
                app = QApplication.instance()
                if app is not None:
                    c = app.palette().window().color()
                    dark_by_palette = ((c.red() + c.green() + c.blue()) / 3.0) < 128
            except Exception:
                dark_by_palette = is_dark_ui()
            apply_theme("DARK" if dark_by_palette else "LIGHT")
            self._apply_theme_styles(force=True)
            for attr in ("settings_window", "workbench_window", "favorites_window", "handwriting_window"):
                try:
                    win = getattr(self, attr, None)
                    if win and win.isVisible() and hasattr(win, "apply_theme_styles"):
                        win.apply_theme_styles(force=True)
                except Exception:
                    pass
            try:
                refresh_runtime_log_dialog_theme(force=True)
            except Exception:
                pass
        finally:
            self._auto_theme_sync_in_progress = False

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                if getattr(self, "_theme_mode", "auto") == "auto":
                    self._schedule_auto_theme_refresh()
                else:
                    self._apply_theme_styles()
        except Exception:
            pass
        return result

    def _apply_formula_label_theme(self, lbl: QLabel):
        if lbl is None:
            return
        t = formula_label_theme_tokens()
        lbl.setToolTip("点击加载到编辑器并渲染")
        lbl.setStyleSheet(
            "QLabel {"
            f"color: {t['text']}; padding: 2px;"
            "}"
        )

    def _history_row_theme_tokens(self) -> dict:
        return history_row_theme_tokens()

    def _apply_history_row_theme(self, row: QWidget):
        if row is None:
            return
        content_lbl = getattr(row, "_content_label", None)
        if isinstance(content_lbl, QLabel):
            self._apply_formula_label_theme(content_lbl)

        t = self._history_row_theme_tokens()
        index_lbl = getattr(row, "_index_label", None)
        if isinstance(index_lbl, QLabel):
            index_lbl.setStyleSheet(
                f"color: {t['index']}; font-weight: bold; font-size: 11px;"
            )

        name_lbl = getattr(row, "_name_label", None)
        if isinstance(name_lbl, QLabel):
            name_lbl.setStyleSheet(
                f"color: {t['name']}; font-size: 10px; margin-right: 4px;"
            )

    def _refresh_history_rows_theme(self):
        if not hasattr(self, "history_layout"):
            return
        row_count = max(0, self.history_layout.count() - 1)
        for i in range(row_count):
            item = self.history_layout.itemAt(i)
            row = item.widget() if item else None
            if isinstance(row, QWidget):
                self._apply_history_row_theme(row)

    def apply_app_theme_mode(self, mode: str | None, refresh_preview: bool = True):
        normalized = normalize_theme_mode(mode)
        self._theme_mode = normalized
        try:
            self.cfg.set("theme_mode", normalized)
        except Exception:
            pass
        apply_theme_mode(normalized)
        try:
            self._apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            if getattr(self, "workbench_window", None) and self.workbench_window.isVisible():
                self.workbench_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            refresh_runtime_log_dialog_theme(force=True)
        except Exception:
            pass
        if refresh_preview:
            try:
                self._refresh_preview()
            except Exception:
                pass

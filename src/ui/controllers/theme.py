"""ThemeController and related helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.config_manager import ConfigManager
    from ui.controllers.preview import PreviewController
    from ui.controllers.windows import WindowController
    from ui.main_window import MainWindow
import json
import logging

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from localization.manager import translate as tr
from runtime.app_paths import app_config_path
from ui.controllers.runtime_log import refresh_runtime_log_dialog_theme
from ui.theme_tokens import formula_label_theme_tokens, is_dark_ui

logger = logging.getLogger(f"latexsnipper.{__name__}")


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
        logger.warning("应用主题失败: %s", e)
        return False


def normalize_theme_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    return mode if mode in ("light", "dark", "auto") else "auto"


def apply_theme_mode(mode: str | None) -> bool:
    normalized = normalize_theme_mode(mode)
    map_mode = {"light": "LIGHT", "dark": "DARK", "auto": "AUTO"}
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
        return {"title": "#8ec5ff", "muted": "#95a0af"}
    return {"title": "#1976d2", "muted": "#888888"}


def history_row_theme_tokens() -> dict:
    if is_dark_ui():
        return {"index": "#8ec5ff", "name": "#ffb74d"}
    return {"index": "#1976d2", "name": "#f57c00"}


class ThemeController(QObject):
    def __init__(
        self,
        view: MainWindow,
        cfg: ConfigManager,
        preview: PreviewController,
        windows: WindowController,
    ):
        super().__init__(view)
        self.view = view
        self.cfg = cfg
        self.preview = preview
        self.windows = windows
        self._theme_is_dark_cached = None
        self._auto_theme_sync_in_progress = False
        self._theme_mode = normalize_theme_mode(cfg.get("theme_mode", "auto"))
        self._auto_theme_refresh_timer = QTimer(self)
        self._auto_theme_refresh_timer.setSingleShot(True)
        self._auto_theme_refresh_timer.setInterval(160)
        self._auto_theme_refresh_timer.timeout.connect(
            self._on_auto_theme_refresh_timeout
        )

    def _main_theme_tokens(self) -> dict:
        return main_theme_tokens()

    def apply_styles(self, force: bool = False):
        dark = is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._main_theme_tokens()
        title_style = (
            f"font-size: 14px; font-weight: 500; color: {t['title']}; padding: 4px 0;"
        )
        try:
            if hasattr(self.view, "history_title_label"):
                self.view.history_title_label.setStyleSheet(title_style)
            if hasattr(self.view, "editor_title_label"):
                self.view.editor_title_label.setStyleSheet(title_style)
            if hasattr(self.view, "preview_title_label"):
                self.view.preview_title_label.setStyleSheet(title_style)
            if (
                hasattr(self.view, "preview_fallback_label")
                and self.view.preview_fallback_label
            ):
                self.view.preview_fallback_label.setStyleSheet(
                    f"color: {t['muted']}; padding: 20px;"
                )
        except Exception:
            pass
        try:
            if (
                self.windows.settings_window
                and self.windows.settings_window.isVisible()
                and hasattr(self.windows.settings_window, "apply_theme_styles")
            ):
                self.windows.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            self.preview.refresh()
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
            if (
                hasattr(self, "_auto_theme_refresh_timer")
                and self._auto_theme_refresh_timer is not None
            ):
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
                    dark_by_palette = (c.red() + c.green() + c.blue()) / 3.0 < 128
            except Exception:
                dark_by_palette = is_dark_ui()
            apply_theme("DARK" if dark_by_palette else "LIGHT")
            self.apply_styles(force=True)
            for attr in (
                "settings_window",
                "workbench_window",
                "favorites_window",
                "handwriting_window",
            ):
                try:
                    win = getattr(self.windows, attr, None)
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

    def handle_event(self, e):
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                if getattr(self, "_theme_mode", "auto") == "auto":
                    self._schedule_auto_theme_refresh()
                else:
                    self.apply_styles()
        except Exception:
            pass

    def style_formula_label(self, lbl: QLabel):
        if lbl is None:
            return
        t = formula_label_theme_tokens()
        lbl.setToolTip(tr("点击加载到编辑器并渲染"))
        lbl.setStyleSheet(f"QLabel {{color: {t['text']}; padding: 2px;}}")

    def _history_row_theme_tokens(self) -> dict:
        return history_row_theme_tokens()

    def style_history_row(self, row: QWidget):
        if row is None:
            return
        content_lbl = getattr(row, "_content_label", None)
        if isinstance(content_lbl, QLabel):
            self.style_formula_label(content_lbl)
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
        if not hasattr(self.view, "history_layout"):
            return
        row_count = max(0, self.view.history_layout.count() - 1)
        for i in range(row_count):
            item = self.view.history_layout.itemAt(i)
            row = item.widget() if item else None
            if isinstance(row, QWidget):
                self.style_history_row(row)

    def apply_mode(self, mode: str | None, refresh_preview: bool = True):
        normalized = normalize_theme_mode(mode)
        self._theme_mode = normalized
        try:
            self.cfg.set("theme_mode", normalized)
        except Exception:
            pass
        apply_theme_mode(normalized)
        try:
            self.apply_styles(force=True)
        except Exception:
            pass
        try:
            if (
                getattr(self.windows, "workbench_window", None)
                and self.windows.workbench_window.isVisible()
            ):
                self.windows.workbench_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            refresh_runtime_log_dialog_theme(force=True)
        except Exception:
            pass
        if refresh_preview:
            try:
                self.preview.refresh()
            except Exception:
                pass

    def shutdown(self):
        self._auto_theme_refresh_timer.stop()

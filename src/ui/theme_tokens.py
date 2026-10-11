"""Shared desktop theme detection and widget color tokens."""

from PyQt6.QtWidgets import QApplication


def is_dark_ui() -> bool:
    try:
        import qfluentwidgets as qfw

        fn = getattr(qfw, "isDarkTheme", None)
        if callable(fn):
            return bool(fn())
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        return False
    c = app.palette().window().color()
    return ((c.red() + c.green() + c.blue()) / 3.0) < 128


def formula_label_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "text": "#d7dee9",
            "tooltip_bg": "#27303b",
            "tooltip_text": "#eef3f8",
            "tooltip_border": "#4d5a6b",
        }
    return {
        "text": "#333333",
        "tooltip_bg": "#ffffff",
        "tooltip_text": "#1f2328",
        "tooltip_border": "#cfd6df",
    }


def dialog_theme_tokens() -> dict:
    if is_dark_ui():
        return {
            "window_bg": "#1b1f27",
            "panel_bg": "#232934",
            "text": "#e7ebf0",
            "muted": "#a9b3bf",
            "border": "#465162",
            "accent": "#8ec5ff",
        }
    return {
        "window_bg": "#ffffff",
        "panel_bg": "#f7f9fc",
        "text": "#222222",
        "muted": "#666666",
        "border": "#d0d7de",
        "accent": "#1976d2",
    }

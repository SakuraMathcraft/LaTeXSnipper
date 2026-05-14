"""Startup splash window helpers."""

from __future__ import annotations

import os

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from runtime.app_paths import resource_path

_STARTUP_SPLASH = None
FORCE_ENTER_STARTUP_MESSAGE = "正在跳过依赖安装并进入主程序..."


class StartupDialog(QWidget):
    def __init__(self, pixmap, flags):
        super().__init__(None, flags)
        self._label = QLabel(self)
        self._label.setScaledContents(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setPixmap(pixmap)

    def setPixmap(self, pixmap):
        self._label.setPixmap(pixmap)
        dpr = float(pixmap.devicePixelRatio() or 1.0)
        logical_w = max(1, int(round(pixmap.width() / dpr)))
        logical_h = max(1, int(round(pixmap.height() / dpr)))
        self._label.setGeometry(0, 0, logical_w, logical_h)
        self.resize(logical_w, logical_h)

    def finish(self, _window=None):
        self.close()


def build_startup_splash_pixmap(app, status_text: str = ""):
    """Build a crisp high-DPI splash pixmap with a safe status text area."""
    logical_w, logical_h = 340, 360
    dpr = 1.0
    try:
        screen = app.primaryScreen() if app else None
        if screen is not None:
            dpr = float(screen.devicePixelRatio() or 1.0)
    except Exception:
        dpr = 1.0

    pm = QPixmap(int(logical_w * dpr), int(logical_h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(248, 248, 248, 246))
    painter.drawRoundedRect(10, 10, logical_w - 20, logical_h - 20, 20, 20)

    icon_path = resource_path("assets/icon.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
    icon_size = 112
    if not icon.isNull():
        icon_rect = QRect((logical_w - icon_size) // 2, 72, icon_size, icon_size)
        icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

    painter.setPen(QColor(38, 38, 38))
    title_font = QFont("Microsoft YaHei UI", 16)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(QRect(0, 196, logical_w, 34), int(Qt.AlignmentFlag.AlignCenter), "LaTeXSnipper")

    painter.setPen(QColor(110, 110, 110))
    sub_font = QFont("Microsoft YaHei UI", 11)
    painter.setFont(sub_font)
    painter.drawText(QRect(0, 232, logical_w, 24), int(Qt.AlignmentFlag.AlignCenter), "正在启动...")

    status_font = QFont("Microsoft YaHei UI", 10)
    painter.setFont(status_font)
    fm = QFontMetrics(status_font)
    safe_text = fm.elidedText((status_text or "").strip(), Qt.TextElideMode.ElideRight, logical_w - 44)
    painter.setPen(QColor(92, 92, 92))
    painter.drawText(QRect(22, 270, logical_w - 44, 32), int(Qt.AlignmentFlag.AlignCenter), safe_text)

    painter.end()
    return pm


def create_startup_splash(app):
    """Create a centered splash window to indicate app is loading."""
    try:
        pm = build_startup_splash_pixmap(app, "")
        splash = StartupDialog(
            pm,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        splash._lsn_status = ""
        try:
            screen = app.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                splash.move(geo.center().x() - splash.width() // 2, geo.center().y() - splash.height() // 2)
        except Exception:
            pass
        splash.show()
        app.processEvents()
        return splash
    except Exception as e:
        print(f"[WARN] startup splash init failed: {e}")
        return None


def update_startup_splash(splash, message: str):
    if not splash:
        return
    try:
        app = QApplication.instance()
        if app is not None:
            splash._lsn_status = str(message or "")
            splash.setPixmap(build_startup_splash_pixmap(app, splash._lsn_status))
            app.processEvents()
    except Exception:
        pass


def ensure_startup_splash(message: str = ""):
    global _STARTUP_SPLASH
    app = QApplication.instance()
    if app is None:
        return None
    if _STARTUP_SPLASH is None:
        _STARTUP_SPLASH = create_startup_splash(app)
    else:
        try:
            if not _STARTUP_SPLASH.isVisible():
                _STARTUP_SPLASH.show()
                app.processEvents()
        except Exception:
            pass
    update_startup_splash(_STARTUP_SPLASH, message)
    return _STARTUP_SPLASH


def take_startup_splash(app, message: str = ""):
    global _STARTUP_SPLASH
    splash = _STARTUP_SPLASH or create_startup_splash(app)
    _STARTUP_SPLASH = splash
    try:
        if splash is not None and not splash.isVisible():
            splash.show()
            app.processEvents()
    except Exception:
        pass
    update_startup_splash(splash, message)
    return splash


def finish_startup_splash(splash, window=None):
    global _STARTUP_SPLASH
    try:
        if window is not None and hasattr(window, "_startup_progress"):
            window._startup_progress = None
    except Exception:
        pass
    try:
        if splash:
            splash.finish(window)
    except Exception:
        pass
    try:
        if splash is not None and _STARTUP_SPLASH is splash:
            _STARTUP_SPLASH = None
    except Exception:
        pass


def hide_startup_splash_for_modal():
    """Hide the startup splash before showing dependency dialogs."""
    splash = _STARTUP_SPLASH
    if not splash:
        return
    try:
        if splash.isVisible():
            splash.hide()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
    except Exception:
        pass


def deps_force_entered(db_module=None) -> bool:
    try:
        db = db_module
        if db is None:
            import bootstrap.deps_bootstrap as db
        checker = getattr(db, "was_last_ensure_deps_force_enter", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def mark_startup_force_entered():
    os.environ["LATEXSNIPPER_FORCE_ENTERED"] = "1"
    app = QApplication.instance()
    if app is not None:
        return take_startup_splash(app, FORCE_ENTER_STARTUP_MESSAGE)
    return ensure_startup_splash(FORCE_ENTER_STARTUP_MESSAGE)


def startup_force_enter_pending() -> bool:
    return os.environ.get("LATEXSNIPPER_FORCE_ENTERED") == "1"


def startup_status_message(default: str) -> str:
    return FORCE_ENTER_STARTUP_MESSAGE if startup_force_enter_pending() else default


def startup_deps_resume_message() -> str:
    if os.environ.pop("LATEXSNIPPER_FORCE_ENTERED", "0") == "1":
        return FORCE_ENTER_STARTUP_MESSAGE
    return "依赖检查完成，继续启动..."

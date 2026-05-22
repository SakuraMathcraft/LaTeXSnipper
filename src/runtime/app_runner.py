from __future__ import annotations

import multiprocessing
import os
import sys

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication

from runtime.dependency_bootstrap_controller import ensure_deps
from runtime.runtime_logging import open_debug_console
from runtime.startup_splash import (
    FORCE_ENTER_STARTUP_MESSAGE,
    finish_startup_splash,
    startup_deps_resume_message,
    startup_force_enter_pending,
    startup_status_message,
    take_startup_splash,
    update_startup_splash,
)
from runtime.std_streams import ensure_std_streams
from ui.theme_controller import apply_theme_mode, read_theme_mode_from_config


def _apply_startup_theme() -> None:
    try:
        from qfluentwidgets import setThemeColor

        apply_theme_mode(read_theme_mode_from_config())
        setThemeColor("#0078D4")
    except Exception:
        pass


class _MacOSApplicationLifecycleBridge(QObject):
    def __init__(self, app: QApplication, window):
        super().__init__(app)
        self._window = window
        try:
            app.applicationStateChanged.connect(self._on_application_state_changed)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ApplicationActivate:
            self._schedule_restore_window()
        return False

    def _on_application_state_changed(self, state) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            self._schedule_restore_window()

    def _schedule_restore_window(self) -> None:
        QTimer.singleShot(0, self._restore_window_if_hidden)

    def _restore_window_if_hidden(self) -> None:
        window = self._window
        if window is None:
            return
        if getattr(window, "_force_exit", False) or getattr(window, "_shutdown_done", False):
            return
        try:
            if window.isVisible():
                return
        except RuntimeError:
            return
        show_window = getattr(window, "show_window", None)
        if callable(show_window):
            show_window()
            return
        window.show()
        try:
            window.showNormal()
        except Exception:
            pass
        window.raise_()
        window.activateWindow()


def _install_macos_lifecycle_bridge(app: QApplication, window) -> None:
    if sys.platform != "darwin":
        return
    bridge = _MacOSApplicationLifecycleBridge(app, window)
    app.installEventFilter(bridge)
    app._latexsnipper_macos_lifecycle_bridge = bridge


def _create_window(main_window_cls, splash):
    update_startup_splash(splash, "初始化运行环境...")
    update_startup_splash(splash, "加载主窗口...")
    win = main_window_cls(startup_progress=lambda m: update_startup_splash(splash, m))
    print("[DEBUG] MainWindow 创建完成，准备显示窗口")
    update_startup_splash(splash, "主窗口已加载，正在显示...")
    win.show()
    app = QApplication.instance()
    if app is not None:
        app._latexsnipper_main_window = win
        _install_macos_lifecycle_bridge(app, win)
    win.start_post_show_tasks()
    QTimer.singleShot(0, lambda: open_debug_console(force=False, tee=True))
    finish_startup_splash(splash, win)
    print("[DEBUG] win.show() 完成，进入事件循环")
    return win


def _run_packaged(app, main_window_cls) -> int:
    splash = take_startup_splash(app, startup_status_message("初始化界面..."))
    open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"

    _apply_startup_theme()

    if open_wizard_on_start:
        update_startup_splash(splash, startup_status_message("检查依赖中..."))
        ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
        if not ok:
            return 1
        splash = take_startup_splash(app, startup_deps_resume_message())
    if startup_force_enter_pending():
        splash = take_startup_splash(app, startup_deps_resume_message())

    _create_window(main_window_cls, splash)
    return app.exec()


def _run_development(app, main_window_cls) -> int:
    splash = take_startup_splash(app, startup_status_message("初始化界面..."))
    open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"
    deps_check_message = startup_status_message("检查依赖中...")
    update_startup_splash(splash, deps_check_message)
    deps_ready_cached = os.environ.get("LATEXSNIPPER_DEPS_OK") == "1"
    needs_interactive_deps_ui = bool(open_wizard_on_start or (not deps_ready_cached))

    if open_wizard_on_start:
        ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
    else:
        ok = ensure_deps(prompt_ui=True, always_show_ui=False, from_settings=False)
    if not ok:
        return 1

    resume_message = startup_deps_resume_message()
    if needs_interactive_deps_ui or resume_message == FORCE_ENTER_STARTUP_MESSAGE:
        splash = take_startup_splash(app, resume_message)
    update_startup_splash(splash, resume_message)

    _apply_startup_theme()
    _create_window(main_window_cls, splash)
    return app.exec()


def run_application(main_window_cls) -> int:
    multiprocessing.freeze_support()
    ensure_std_streams()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if getattr(sys, "frozen", False):
        return _run_packaged(app, main_window_cls)
    return _run_development(app, main_window_cls)

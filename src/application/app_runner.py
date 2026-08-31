from __future__ import annotations

import multiprocessing
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from application.dependency_controller import ensure_deps
from localization.manager import translate as tr
from ui.runtime_log_controller import apply_runtime_log_window_preference
from ui.startup_splash import (
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


def _create_window(main_window_cls, splash):
    update_startup_splash(splash, tr("加载界面组件..."))
    win = main_window_cls(startup_progress=lambda m: update_startup_splash(splash, m))
    update_startup_splash(splash, tr("显示主窗口..."))
    win.show()
    win.start_post_show_tasks()
    QTimer.singleShot(
        0, lambda: apply_runtime_log_window_preference(force=False, tee=True)
    )
    finish_startup_splash(splash, win)
    print("[INFO] 应用界面已就绪")
    return win


def _run_packaged(app, main_window_cls) -> int:
    splash = take_startup_splash(app, startup_status_message(tr("加载界面组件...")))
    open_dependency_management = (
        os.environ.pop("LATEXSNIPPER_OPEN_DEPENDENCY_MANAGEMENT", None) == "1"
    )

    _apply_startup_theme()

    if open_dependency_management:
        update_startup_splash(splash, startup_status_message(tr("检查依赖...")))
        ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
        if not ok:
            return 1
        splash = take_startup_splash(app, startup_deps_resume_message())
    if startup_force_enter_pending():
        splash = take_startup_splash(app, startup_deps_resume_message())

    _create_window(main_window_cls, splash)
    return app.exec()


def _run_development(app, main_window_cls) -> int:
    splash = take_startup_splash(app, startup_status_message(tr("加载界面组件...")))
    open_dependency_management = (
        os.environ.pop("LATEXSNIPPER_OPEN_DEPENDENCY_MANAGEMENT", None) == "1"
    )
    deps_check_message = startup_status_message(tr("检查依赖..."))
    update_startup_splash(splash, deps_check_message)
    deps_ready_cached = os.environ.get("LATEXSNIPPER_DEPS_OK") == "1"
    needs_interactive_deps_ui = bool(
        open_dependency_management or (not deps_ready_cached)
    )

    if open_dependency_management:
        ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
    else:
        ok = ensure_deps(prompt_ui=True, always_show_ui=False, from_settings=False)
    if not ok:
        return 1

    resume_message = startup_deps_resume_message()
    if needs_interactive_deps_ui or resume_message == tr(
        "正在跳过依赖安装并进入主程序..."
    ):
        splash = take_startup_splash(app, resume_message)
    update_startup_splash(splash, resume_message)

    _apply_startup_theme()
    _create_window(main_window_cls, splash)
    return app.exec()


def run_application(main_window_cls) -> int:
    multiprocessing.freeze_support()
    ensure_std_streams()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("LaTeXSnipper")
    app.setOrganizationName("MathCraft")
    app.setQuitOnLastWindowClosed(False)
    if getattr(sys, "frozen", False):
        return _run_packaged(app, main_window_cls)
    return _run_development(app, main_window_cls)

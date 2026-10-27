from __future__ import annotations

import logging
import multiprocessing
import sys
import threading
from typing import cast

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from localization.manager import translate as tr
from runtime.std_streams import ensure_std_streams
from ui.controllers.runtime_log import apply_runtime_log_window_preference
from ui.controllers.theme import apply_theme_mode, read_theme_mode_from_config
from ui.startup_splash import (
    finish_startup_splash,
    take_startup_splash,
    update_startup_splash,
)

logger = logging.getLogger(f"latexsnipper.{__name__}")


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
    QTimer.singleShot(0, lambda: apply_runtime_log_window_preference(force=False))
    finish_startup_splash(splash, win)
    QTimer.singleShot(0, lambda: _report_deployment_outcome(win))
    logger.info("应用界面已就绪")
    return win


def _report_deployment_outcome(win) -> None:
    from runtime.deployment_feedback import (
        cleanup_deployment_task,
        consume_deployment_result,
    )

    try:
        feedback = consume_deployment_result()
        if feedback is None:
            return
        result, directory = feedback
        if result["state"] == "committed":
            win.status.show_action_status(tr("应用更新已完成。"), level="success")
        else:
            win.status.show_action_status(
                tr("更新未完成，已恢复更新前的安装状态。{error}").format(
                    error=result.get("error", "")
                ),
                level="warning",
            )

        def cleanup(attempt=0):
            try:
                if not cleanup_deployment_task(directory) and attempt < 10:
                    QTimer.singleShot(1000, lambda: cleanup(attempt + 1))
            except (OSError, ValueError):
                logger.exception("清理部署任务缓存失败")

        QTimer.singleShot(1000, cleanup)
    except (OSError, ValueError, RuntimeError):
        logger.exception("读取独立部署结果失败")
    finally:
        from update.cache_cleanup import cleanup_update_cache

        threading.Thread(
            target=cleanup_update_cache, name="update-cache-cleanup", daemon=True
        ).start()


def run_application(main_window_cls) -> int:
    multiprocessing.freeze_support()
    ensure_std_streams()

    app = cast("QApplication | None", QApplication.instance()) or QApplication(sys.argv)
    app.setApplicationName("LaTeXSnipper")
    app.setOrganizationName("MathCraft")
    app.setQuitOnLastWindowClosed(False)
    splash = take_startup_splash(app, tr("加载界面组件..."))
    _apply_startup_theme()
    _create_window(main_window_cls, splash)
    return app.exec()

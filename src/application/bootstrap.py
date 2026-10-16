from __future__ import annotations

import atexit
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from localization.manager import install_application_translators, translate as tr
from runtime.app_paths import resource_path, get_app_root
from runtime.runtime_logging import start_runtime_log_session
from runtime.native_runtime import configure_native_runtime_environment
from runtime.single_instance import (
    ensure_single_instance,
    release_single_instance_lock,
)
from ui.startup_splash import ensure_startup_splash
from runtime.webengine_runtime import configure_default_webengine_profile

logger = logging.getLogger(f"latexsnipper.{__name__}")


@dataclass(frozen=True)
class BootstrapContext:
    app: QApplication
    app_dir: Path


_BOOTSTRAP_CONTEXT: BootstrapContext | None = None


def _ensure_qt_application() -> QApplication:
    try:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass
    return QApplication.instance() or QApplication(sys.argv)


def _show_already_running_message(app: QApplication) -> None:
    try:
        icon_path = resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
            app.setWindowIcon(icon)
        else:
            icon = None
        msg = QMessageBox()
        msg.setWindowTitle("LaTeXSnipper")
        msg.setText(tr("LaTeXSnipper 已在运行。"))
        msg.setIcon(QMessageBox.Icon.Information)
        if icon is not None:
            msg.setWindowIcon(icon)
        msg.exec()
    except Exception:
        logger.info("检测到已有实例，本次启动已取消")


def _ensure_single_instance(app: QApplication) -> None:
    if ensure_single_instance():
        atexit.register(release_single_instance_lock)
        start_runtime_log_session()
        return
    _show_already_running_message(app)
    raise SystemExit(0)


def _ensure_src_path() -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(current_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def bootstrap_application() -> BootstrapContext:
    global _BOOTSTRAP_CONTEXT
    if _BOOTSTRAP_CONTEXT is not None:
        return _BOOTSTRAP_CONTEXT

    configure_native_runtime_environment()
    app = _ensure_qt_application()
    install_application_translators(app)
    _ensure_single_instance(app)
    ensure_startup_splash(tr("加载界面组件..."))
    _ensure_src_path()
    configure_default_webengine_profile()

    app_dir = get_app_root()
    _BOOTSTRAP_CONTEXT = BootstrapContext(app=app, app_dir=app_dir)
    return _BOOTSTRAP_CONTEXT

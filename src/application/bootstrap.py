from __future__ import annotations

import atexit
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication

from localization.manager import install_application_translators
from localization.manager import translate as tr
from runtime.app_paths import APP_DESKTOP_ID, get_app_root
from runtime.native_runtime import configure_native_runtime_environment
from runtime.runtime_logging import start_runtime_log_session
from runtime.single_instance import (
    activate_running_instance,
    ensure_single_instance,
    release_single_instance_lock,
    start_instance_activation,
)
from runtime.webengine_runtime import configure_default_webengine_profile
from ui.startup_splash import ensure_startup_splash


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
    return cast("QApplication | None", QApplication.instance()) or QApplication(
        sys.argv
    )


def _ensure_single_instance(app: QApplication) -> None:
    if ensure_single_instance():
        atexit.register(release_single_instance_lock)
        start_instance_activation(app)
        start_runtime_log_session()
        return
    activate_running_instance()
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
    if sys.platform == "linux":
        app.setDesktopFileName(APP_DESKTOP_ID)
    install_application_translators(app)
    _ensure_single_instance(app)
    ensure_startup_splash(tr("加载界面组件..."))
    _ensure_src_path()
    configure_default_webengine_profile()

    app_dir = get_app_root()
    _BOOTSTRAP_CONTEXT = BootstrapContext(app=app, app_dir=app_dir)
    return _BOOTSTRAP_CONTEXT

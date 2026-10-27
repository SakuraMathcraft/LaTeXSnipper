"""Drive the real update buttons inside an isolated installed acceptance fixture."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from runtime.app_paths import app_state_dir
from runtime.distribution_manifest import read_json
from update.deployment_transaction import atomic_json


def start(report: str, tag: str) -> None:
    from update import component_release

    component_release.RELEASE_API = f"https://api.github.com/repos/{component_release.REPOSITORY}/releases/tags/{tag}"
    result: dict[str, Any] = {"pid": os.getpid(), "states": {}}

    def drive() -> None:
        from installed_hotkey_acceptance import validate_hotkeys
        from ui.main_window import MainWindow
        from update import update_dialog

        window: Any = next(
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, MainWindow)
        )
        result["hotkeys"] = validate_hotkeys(window)
        atomic_json(Path(report), result)
        window.settings_button.click()
        window.windows.settings_window.btn_update.click()
        dialog: Any = update_dialog._dialog

        def changed(state: str, data: dict) -> None:
            if state in {"release", "progress"}:
                return
            result["states"][state] = time.monotonic()
            if state == "available":
                result["user_files"] = {
                    str(path): read_json(path)
                    for path in app_state_dir().glob("*.json")
                }
            if state == "handoff-ready":
                result["request"] = str(dialog.controller._request)
                result["update_window_visible"] = dialog.isVisible()
            if state == "failed":
                result["error"] = str(data.get("error", "Update failed"))
            atomic_json(Path(report), result)
            if state in {"available", "ready"}:
                if not dialog.action.isEnabled():
                    result["error"] = "The installed update action is unavailable"
                    atomic_json(Path(report), result)
                    return
                QTimer.singleShot(0, dialog.action.click)

        dialog.controller.changed.connect(changed)

    def begin() -> None:
        try:
            drive()
        except Exception as exc:
            result["error"] = str(exc)
            atomic_json(Path(report), result)

    QTimer.singleShot(1000, begin)

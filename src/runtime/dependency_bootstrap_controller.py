"""Dependency bootstrap entry points shared by startup and settings flows."""

from __future__ import annotations

import os

from runtime.startup_splash import (
    deps_force_entered,
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)


def load_startup_modules():
    from bootstrap.deps_entry import clear_deps_state
    from bootstrap.deps_ui import custom_warning_dialog
    from ui.settings_window import SettingsWindow

    return custom_warning_dialog, clear_deps_state, SettingsWindow


def ensure_deps(*args, **kwargs):
    from_settings = bool(kwargs.get("from_settings", False))
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not from_settings:
        return True

    from bootstrap.deps_entry import ensure_deps as run_dependency_bootstrap

    prompt_ui = bool(kwargs.get("prompt_ui", True))
    if prompt_ui:
        kwargs.setdefault("before_show_ui", hide_startup_splash_for_modal)
        kwargs.setdefault("after_force_enter", mark_startup_force_entered)
    ok = run_dependency_bootstrap(*args, **kwargs)
    if ok:
        os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
        if deps_force_entered():
            mark_startup_force_entered()
    return ok


def show_dependency_wizard(always_show_ui: bool = False):
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not always_show_ui:
        return True
    try:
        from bootstrap.deps_entry import ensure_deps as run_dependency_bootstrap

        ok = run_dependency_bootstrap(
            always_show_ui=always_show_ui,
            before_show_ui=hide_startup_splash_for_modal,
            after_force_enter=mark_startup_force_entered,
        )
        if ok:
            os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
            if deps_force_entered():
                mark_startup_force_entered()
        return ok
    except Exception as e:
        print(f"[WARN] 依赖向导不可用: {e}")
        return False

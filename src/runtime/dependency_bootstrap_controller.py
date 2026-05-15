"""Dependency bootstrap entry points shared by startup and settings flows."""

from __future__ import annotations

import os

from runtime.startup_splash import (
    deps_force_entered,
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)


def load_startup_modules():
    from bootstrap.deps_bootstrap import clear_deps_state, custom_warning_dialog
    from ui.settings_window import SettingsWindow

    return custom_warning_dialog, clear_deps_state, SettingsWindow


def ensure_deps(*args, **kwargs):
    from_settings = bool(kwargs.get("from_settings", False))
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not from_settings:
        return True

    import bootstrap.deps_bootstrap as deps_bootstrap

    prompt_ui = bool(kwargs.get("prompt_ui", True))
    if prompt_ui:
        kwargs.setdefault("before_show_ui", hide_startup_splash_for_modal)
        kwargs.setdefault("after_force_enter", mark_startup_force_entered)
    ok = deps_bootstrap.ensure_deps(*args, **kwargs)
    if ok:
        os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
        if deps_force_entered(deps_bootstrap):
            mark_startup_force_entered()
    return ok


def show_dependency_wizard(always_show_ui: bool = False):
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not always_show_ui:
        return True
    try:
        import bootstrap.deps_bootstrap as deps_bootstrap

        ok = deps_bootstrap.ensure_deps(
            always_show_ui=always_show_ui,
            before_show_ui=hide_startup_splash_for_modal,
            after_force_enter=mark_startup_force_entered,
        )
        if ok:
            os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
            if deps_force_entered(deps_bootstrap):
                mark_startup_force_entered()
        return ok
    except Exception as e:
        print(f"[WARN] 依赖向导不可用: {e}")
        return False

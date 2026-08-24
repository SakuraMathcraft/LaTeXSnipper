"""Dependency bootstrap entry points shared by startup and settings flows."""

from __future__ import annotations

import os

from bootstrap.deps_context import was_last_ensure_deps_force_enter
from ui.startup_splash import (
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)


def deps_force_entered() -> bool:
    return was_last_ensure_deps_force_enter()


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

"""Dependency bootstrap entry points shared by startup and settings flows."""

from __future__ import annotations

import os

from runtime.startup_splash import (
    deps_force_entered,
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)


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

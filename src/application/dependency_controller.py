"""Dependency bootstrap entry points shared by startup and settings flows."""

from __future__ import annotations

from bootstrap.deps_context import was_last_ensure_deps_force_enter
from ui.startup_splash import (
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)


_dependencies_ready = False


def dependencies_ready() -> bool:
    return _dependencies_ready


def deps_force_entered() -> bool:
    return was_last_ensure_deps_force_enter()


def ensure_deps(*args, **kwargs):
    global _dependencies_ready
    from_settings = bool(kwargs.get("from_settings", False))
    if dependencies_ready() and not from_settings:
        return True

    from bootstrap.deps_entry import ensure_deps as run_dependency_bootstrap

    prompt_ui = bool(kwargs.get("prompt_ui", True))
    if prompt_ui:
        kwargs.setdefault("before_show_ui", hide_startup_splash_for_modal)
        kwargs.setdefault("after_force_enter", mark_startup_force_entered)
    ok = run_dependency_bootstrap(*args, **kwargs)
    if ok:
        _dependencies_ready = True
        if deps_force_entered():
            mark_startup_force_entered()
    return ok

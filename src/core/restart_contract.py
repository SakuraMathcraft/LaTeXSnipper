# -*- coding: utf-8 -*-
"""Pure restart launch contract for regression testing."""

from __future__ import annotations

import os


def build_restart_with_wizard_launch(
    python_exe: str,
    argv0: str,
    base_env: dict | None = None,
) -> tuple[list[str], dict]:
    env = dict(base_env or os.environ.copy())
    env["LATEXSNIPPER_OPEN_WIZARD"] = "1"
    env["LATEXSNIPPER_FORCE_VERIFY"] = "1"
    env["LATEXSNIPPER_RESTART"] = "1"
    env.pop("LATEXSNIPPER_DEPS_OK", None)

    script_path = os.path.abspath(argv0)
    if script_path.lower().endswith(".py"):
        cmd = [python_exe, script_path, "--force-deps-check"]
    else:
        cmd = [script_path, "--force-deps-check"]
    return cmd, env


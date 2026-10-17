"""Shared options for background subprocesses."""

from __future__ import annotations

import os
import subprocess
import sys


def hidden_subprocess_kwargs() -> dict:
    """Keep background subprocesses from opening console windows on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def independent_process_environment() -> dict[str, str]:
    """Give independent executables their own frozen runtime and native libraries."""
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        for key in tuple(env):
            if key.startswith("_PYI_"):
                env.pop(key)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        original = env.pop("LD_LIBRARY_PATH_ORIG", "")
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
        for key in tuple(env):
            if key.startswith("DYLD_"):
                env.pop(key)
    return env

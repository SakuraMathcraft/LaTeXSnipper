# pyright: reportUnusedImport=false

import os
import subprocess
import sys
import threading
from pathlib import Path

from bootstrap.deps_pip_runner import configure_pip_runner

try:
    import psutil
except Exception:
    psutil = None

os.environ["PYTHONUTF8"] = "1"

_LAST_ENSURE_DEPS_FORCE_ENTER = False


def set_last_ensure_deps_force_enter(value: bool) -> None:
    global _LAST_ENSURE_DEPS_FORCE_ENTER
    _LAST_ENSURE_DEPS_FORCE_ENTER = bool(value)


def was_last_ensure_deps_force_enter():
    return _LAST_ENSURE_DEPS_FORCE_ENTER


subprocess_lock = threading.Lock()


def _hidden_subprocess_kwargs() -> dict:
    if sys.platform != "win32":
        return {}
    kwargs = {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def safe_run(cmd, cwd=None, shell=False, timeout=None, **popen_kwargs):
    """Start a subprocess and return the Popen object without eagerly reading stdout."""
    print(f"[RUN] {' '.join(cmd)}")

    popen_kwargs.setdefault("stdout", subprocess.PIPE)
    popen_kwargs.setdefault("stderr", subprocess.STDOUT)
    popen_kwargs.setdefault("text", True)
    for key, value in _hidden_subprocess_kwargs().items():
        popen_kwargs.setdefault(key, value)


    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        **popen_kwargs
    )
    return proc


flags = 0
if sys.platform == "win32":
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


CONFIG_FILE = "LaTeXSnipper_config.json"


STATE_FILE = ".deps_state.json"


def _config_dir_path() -> Path:
    p = Path.home() / ".latexsnipper"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


pip_ready_event = threading.Event()


PIP_INSTALL_SUPPRESS_ARGS = ["--no-warn-script-location"]
configure_pip_runner(
    safe_run=safe_run,
    subprocess_lock=subprocess_lock,
    suppress_args=PIP_INSTALL_SUPPRESS_ARGS,
)

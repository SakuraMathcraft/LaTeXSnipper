"""Startup dependency environment orchestration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable


def read_show_console_preference(config_path: Path, default: bool = False) -> bool:
    raw_pref = (os.environ.get("LATEXSNIPPER_SHOW_CONSOLE", "") or "").strip().lower()
    if raw_pref in ("1", "true", "yes", "on", "0", "false", "no", "off"):
        return raw_pref in ("1", "true", "yes", "on")

    try:
        if config_path.exists():
            cfg_data = json.loads(config_path.read_text(encoding="utf-8"))
            raw = cfg_data.get("show_startup_console", default) if isinstance(cfg_data, dict) else default
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            if isinstance(raw, str):
                return raw.strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        pass
    return default


def maybe_redirect_packaged_private_python(
    *,
    install_base_dir: Path,
    main_file: str,
    argv: list[str],
    config_path: Path,
    is_packaged_mode: Callable[[], bool],
    find_install_base_python: Callable[[Path], Path | None],
) -> None:
    """In packaged mode, optionally relaunch through the private Python runtime."""
    if not is_packaged_mode():
        return

    py_exe_path = find_install_base_python(install_base_dir)
    py_name = "python.exe" if os.name == "nt" else "python3"
    py_exe = py_exe_path if py_exe_path is not None else (install_base_dir / "python311" / py_name)

    if not py_exe.exists():
        print(f"[WARN] packaged: private python not found: {py_exe}, keep bundled runtime")
        return

    if os.environ.get("LATEXSNIPPER_FORCE_PRIVATE_PY") != "1":
        print("[INFO] packaged: keep bundled runtime, mount deps dir")
        return

    if os.environ.get("LATEXSNIPPER_INNER_PY") == "1":
        print("[INFO] packaged: already in private python")
        return

    print(f"[INFO] packaged: redirect to private python {py_exe}")
    env = os.environ.copy()
    env["LATEXSNIPPER_INNER_PY"] = "1"
    env["LATEXSNIPPER_SHOW_CONSOLE"] = "1" if read_show_console_preference(config_path) else "0"

    run_py = py_exe
    pyw = py_exe.parent / "pythonw.exe"
    if pyw.exists():
        run_py = pyw

    child_argv = [str(run_py), os.path.abspath(main_file), *argv[1:]]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    subprocess.Popen(child_argv, env=env, creationflags=creationflags)
    sys.exit(0)

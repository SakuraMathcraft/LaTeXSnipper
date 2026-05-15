"""
Cross-platform OS integration helpers: open directories and launch terminals.

Platform-specific spawning code lives here so that settings_window.py stays
free of ctypes / shell32 / batch-file / cmd.exe details per the developer
code standards.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def open_directory(path: str) -> None:
    """Open *path* in the OS file manager (Explorer / Finder / default)."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs: dict = {"creationflags": _subprocess_creationflags()}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def open_terminal(
    *,
    pyexe_dir: str,
    scripts_dir: str,
    working_dir: str,
    python_exe_path: str,
    help_text: str,
    as_admin: bool,
) -> None:
    """Open an OS-native terminal pre-configured for the app environment."""
    if os.name == "nt":
        _open_terminal_windows(
            pyexe_dir=pyexe_dir,
            scripts_dir=scripts_dir,
            working_dir=working_dir,
            python_exe_path=python_exe_path,
            help_text=help_text,
            as_admin=as_admin,
        )
    elif sys.platform == "darwin":
        _open_terminal_macos(
            working_dir=working_dir,
            python_exe_path=python_exe_path,
            help_text=help_text,
            pyexe_dir=pyexe_dir,
            scripts_dir=scripts_dir,
        )
    else:
        _open_terminal_linux(
            working_dir=working_dir,
            python_exe_path=python_exe_path,
            help_text=help_text,
            pyexe_dir=pyexe_dir,
            scripts_dir=scripts_dir,
        )


# ---------------------------------------------------------------------------
# Windows helpers
# ---------------------------------------------------------------------------

def _open_terminal_windows(
    *,
    pyexe_dir: str,
    scripts_dir: str,
    working_dir: str,
    python_exe_path: str,
    help_text: str,
    as_admin: bool,
) -> None:
    python_bind_lines = (
        f'set "LATEXSNIPPER_PYEXE={python_exe_path}"\n'
        f'doskey python="{python_exe_path}" $*\n'
        f'doskey py="{python_exe_path}" $*\n'
        f'doskey pip="{python_exe_path}" -m pip $*\n'
        "echo [*] python macro : %LATEXSNIPPER_PYEXE%\n"
        "echo [*] pip macro    : %LATEXSNIPPER_PYEXE% -m pip\n"
        "echo.\n"
    )
    batch_content = (
        "@echo off\n"
        + f'cd /d "{working_dir}"\n'
        + f'set "PATH={pyexe_dir};{scripts_dir};%PATH%"\n'
        + python_bind_lines
        + help_text
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".bat", delete=False, encoding="mbcs", newline="\r\n"
    ) as f:
        f.write(batch_content)
        batch_path = f.name

    if as_admin:
        import ctypes

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", f'/k "{batch_path}"', None, 1
        )
    else:
        subprocess.Popen(
            ["cmd.exe", "/k", batch_path],
            cwd=working_dir,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )


# ---------------------------------------------------------------------------
# macOS helper
# ---------------------------------------------------------------------------

def _open_terminal_macos(
    *,
    pyexe_dir: str,
    scripts_dir: str,
    working_dir: str,
    python_exe_path: str,
    help_text: str,
) -> None:
    banner = (
        f'echo "============================= LaTeXSnipper Terminal ============================="\n'
        f'echo "[*] Python env root: {pyexe_dir}"\n'
        f'echo "[*] python/pip bound to this env for this terminal session"\n'
        f'echo.\n'
    )
    bind_lines = (
        f'export LATEXSNIPPER_PYEXE="{python_exe_path}"\n'
        f'alias python="{python_exe_path}"\n'
        f'alias pip="{python_exe_path} -m pip"\n'
        f'echo "[*] python alias: $LATEXSNIPPER_PYEXE"\n'
        f'echo "[*] pip alias  : $LATEXSNIPPER_PYEXE -m pip"\n'
        f'echo.\n'
    )
    profile_lines = (
        f'export PATH="{pyexe_dir}:{scripts_dir}:$PATH"\n'
        + banner
        + bind_lines
        + help_text
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    ) as f:
        f.write("#!/bin/bash\n" + profile_lines)
        script_path = f.name
    os.chmod(script_path, 0o755)
    subprocess.Popen(
        ["open", "-a", "Terminal", script_path],
        cwd=working_dir,
    )


# ---------------------------------------------------------------------------
# Linux helper
# ---------------------------------------------------------------------------

def _open_terminal_linux(
    *,
    pyexe_dir: str,
    scripts_dir: str,
    working_dir: str,
    python_exe_path: str,
    help_text: str,
) -> None:
    banner = (
        'echo "============================= LaTeXSnipper Terminal ============================="\n'
        f'echo "[*] Python env root: {pyexe_dir}"\n'
        f'echo "[*] python/pip bound to this env for this terminal session"\n'
        f'echo.\n'
    )
    bind_lines = (
        f'export LATEXSNIPPER_PYEXE="{python_exe_path}"\n'
        f'alias python="{python_exe_path}"\n'
        f'alias pip="{python_exe_path} -m pip"\n'
        f'echo "[*] python alias: $LATEXSNIPPER_PYEXE"\n'
        f'echo "[*] pip alias  : $LATEXSNIPPER_PYEXE -m pip"\n'
        f'echo.\n'
    )
    profile_lines = (
        f'export PATH="{pyexe_dir}:{scripts_dir}:$PATH"\n'
        + banner
        + bind_lines
        + help_text
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    ) as f:
        f.write("#!/bin/bash\n" + profile_lines)
        script_path = f.name
    os.chmod(script_path, 0o755)
    # Try common terminal emulators in order.
    for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "xterm"):
        term_path = None
        try:
            term_path = subprocess.check_output(
                ["which", terminal], text=True, timeout=3
            ).strip()
        except Exception:
            pass
        if term_path and os.path.exists(term_path):
            if terminal == "gnome-terminal":
                subprocess.Popen(
                    [term_path, "--", "bash", script_path],
                    cwd=working_dir,
                )
            elif terminal in ("konsole", "xfce4-terminal"):
                subprocess.Popen(
                    [term_path, "-e", f"bash {script_path}"],
                    cwd=working_dir,
                )
            else:
                subprocess.Popen(
                    [term_path, "-e", f"bash {script_path}"],
                    cwd=working_dir,
                )
            return
    # Last resort: xterm
    subprocess.Popen(
        ["xterm", "-e", f"bash {script_path}"],
        cwd=working_dir,
    )

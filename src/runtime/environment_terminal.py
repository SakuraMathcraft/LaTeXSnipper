"""Launch the main dependency terminal and keep one live session per user."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from runtime.app_paths import app_temp_dir
from runtime.dependency_python import python_env_root

_SESSION_FILENAME = "main-environment-terminal.json"
_LAUNCH_GRACE_SECONDS = 15.0


def _terminal_dir() -> Path:
    path = app_temp_dir() / "environment-terminal"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_path() -> Path:
    return _terminal_dir() / _SESSION_FILENAME


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _read_session() -> dict:
    try:
        return json.loads(_session_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _write_session(pid: int, state: str) -> None:
    path = _session_path()
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps({"pid": pid, "state": state, "created_at": time.time()}),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _clear_session() -> None:
    try:
        _session_path().unlink()
    except FileNotFoundError:
        pass


def main_environment_terminal_is_active() -> bool:
    session = _read_session()
    try:
        pid = int(session.get("pid", 0))
        created_at = float(session.get("created_at", 0.0))
    except (TypeError, ValueError):
        pid = 0
        created_at = 0.0
    if session.get("state") == "launching" and time.time() - created_at > _LAUNCH_GRACE_SECONDS:
        _clear_session()
        return False
    if _pid_is_running(pid):
        return True
    _clear_session()
    return False


def _claim_session() -> bool:
    if main_environment_terminal_is_active():
        return False
    path = _session_path()
    payload = json.dumps({"pid": os.getpid(), "state": "launching", "created_at": time.time()})
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(payload)
    return True


def _terminal_environment(pyexe: str, env_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    bind_dirs = [os.path.dirname(pyexe)]
    scripts_dir = env_root / ("Scripts" if os.name == "nt" else "bin")
    if scripts_dir.is_dir():
        bind_dirs.append(str(scripts_dir))
    bind_dirs.append(env.get("PATH", ""))
    env["PATH"] = os.pathsep.join(item for item in bind_dirs if item)
    env["LATEXSNIPPER_PYEXE"] = pyexe
    env["VIRTUAL_ENV"] = str(env_root)
    return env


def _launch_windows(
    pyexe: str,
    workdir: str,
    env: dict[str, str],
    help_lines: Sequence[str],
) -> None:
    launcher = _terminal_dir() / "main-environment-terminal.bat"
    help_commands = "\n".join(f"echo {line}" if line else "echo." for line in help_lines)
    launcher.write_text(
        "@echo off\n"
        "title LaTeXSnipper Terminal - Main Environment\n"
        f'doskey python="{pyexe}" $*\n'
        f'doskey py="{pyexe}" $*\n'
        f'doskey pip="{pyexe}" -m pip $*\n'
        "echo [*] python macro : %LATEXSNIPPER_PYEXE%\n"
        "echo [*] pip macro    : %LATEXSNIPPER_PYEXE% -m pip\n"
        "echo.\n"
        f"{help_commands}\n",
        encoding="mbcs",
        newline="\r\n",
    )
    process = subprocess.Popen(
        ["cmd.exe", "/d", "/k", str(launcher)],
        cwd=workdir,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    _write_session(process.pid, "active")


def _write_posix_launcher(
    pyexe: str,
    env_root: Path,
    workdir: str,
    env: dict[str, str],
    help_lines: Sequence[str],
) -> Path:
    launcher = _terminal_dir() / "main-environment-terminal.sh"
    wrapper_dir = _terminal_dir() / "bin"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    for name, command in {
        "python": f'exec {shlex.quote(pyexe)} "$@"\n',
        "py": f'exec {shlex.quote(pyexe)} "$@"\n',
        "pip": f'exec {shlex.quote(pyexe)} -m pip "$@"\n',
    }.items():
        wrapper = wrapper_dir / name
        wrapper.write_text("#!/bin/sh\n" + command, encoding="utf-8", newline="\n")
        wrapper.chmod(0o755)
    env["PATH"] = os.pathsep.join((str(wrapper_dir), env["PATH"]))
    help_text = "\n".join(help_lines)
    session_path = _session_path()
    shell = env.get("SHELL") or "/bin/sh"
    launcher.write_text(
        "#!/bin/sh\n"
        f"cd {shlex.quote(workdir)} || exit 1\n"
        f"printf '{{\"pid\":%s,\"state\":\"active\",\"created_at\":%s}}' \"$$\" \"$(date +%s)\" > {shlex.quote(str(session_path))}\n"
        f"export PATH={shlex.quote(env['PATH'])}\n"
        f"export LATEXSNIPPER_PYEXE={shlex.quote(pyexe)}\n"
        f"export VIRTUAL_ENV={shlex.quote(str(env_root))}\n"
        "cat <<'LATEXSNIPPER_HELP'\n"
        f"{help_text}\n"
        "LATEXSNIPPER_HELP\n"
        'echo "[*] python command: $(command -v python)"\n'
        'echo "[*] pip command   : $(command -v pip)"\n'
        "echo\n"
        f"{shlex.quote(shell)} -i\n"
        "status=$?\n"
        f"rm -f -- {shlex.quote(str(session_path))}\n"
        "exit $status\n",
        encoding="utf-8",
        newline="\n",
    )
    launcher.chmod(0o755)
    return launcher


def _launch_posix(
    pyexe: str,
    env_root: Path,
    workdir: str,
    env: dict[str, str],
    help_lines: Sequence[str],
) -> None:
    launcher = _write_posix_launcher(pyexe, env_root, workdir, env, help_lines)
    if sys.platform == "darwin":
        command = f'tell application "Terminal" to do script {json.dumps(shlex.quote(str(launcher)))}'
        subprocess.Popen(["osascript", "-e", command])
        return

    launchers: list[list[str]] = []
    configured_terminal = env.get("TERMINAL", "").strip()
    if configured_terminal:
        launchers.append([configured_terminal, "-e", str(launcher)])
    launchers.extend([
        ["x-terminal-emulator", "-e", str(launcher)],
        ["gnome-terminal", "--", str(launcher)],
        ["konsole", "-e", str(launcher)],
        ["xfce4-terminal", "-e", str(launcher)],
        ["xterm", "-e", str(launcher)],
    ])
    for command in launchers:
        if shutil.which(command[0]):
            subprocess.Popen(command, cwd=workdir, env=env)
            return
    raise RuntimeError("未找到可用的终端模拟器。")


def open_main_environment_terminal(
    pyexe: str,
    workdir: str | Path,
    help_lines_factory: Callable[[], Sequence[str]],
) -> bool:
    """Open the bound terminal; return False when its existing session is active."""
    if not _claim_session():
        return False
    try:
        env_root = python_env_root(pyexe)
        directory = str(workdir or env_root)
        env = _terminal_environment(pyexe, env_root)
        help_lines = help_lines_factory()
        if os.name == "nt":
            _launch_windows(pyexe, directory, env, help_lines)
        else:
            _launch_posix(pyexe, env_root, directory, env, help_lines)
    except Exception:
        _clear_session()
        raise
    return True

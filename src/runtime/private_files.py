"""Cross-platform permissions for files containing local credentials."""

from __future__ import annotations

import csv
import os
import subprocess
import threading
from pathlib import Path


_SID_LOCK = threading.RLock()
_CURRENT_USER_SID = ""
_PRIVATE_DIRECTORIES: set[str] = set()


def _is_windows() -> bool:
    return os.name == "nt"


def _current_user_sid() -> str:
    global _CURRENT_USER_SID
    with _SID_LOCK:
        if _CURRENT_USER_SID:
            return _CURRENT_USER_SID
        try:
            identity = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError("无法读取当前 Windows 用户身份。") from exc
        rows = list(csv.reader([identity]))
        if not rows or len(rows[0]) < 2 or not rows[0][1].strip():
            raise OSError("无法确定当前 Windows 用户 SID。")
        _CURRENT_USER_SID = rows[0][1].strip()
        return _CURRENT_USER_SID


def _restrict_windows_path(target: Path, permission: str) -> None:
    sid = _current_user_sid()
    try:
        subprocess.run(
            ["icacls", str(target), "/inheritance:r", "/grant:r", f"*{sid}:{permission}"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("无法限制敏感文件的访问权限。") from exc


def ensure_private_directory(path: str | Path) -> None:
    """Secure a directory once so atomic replacement files inherit private access."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    cache_key = os.path.normcase(str(target.resolve()))
    with _SID_LOCK:
        if cache_key in _PRIVATE_DIRECTORIES:
            return
        if _is_windows():
            _restrict_windows_path(target, "(OI)(CI)F")
        else:
            target.chmod(0o700)
        _PRIVATE_DIRECTORIES.add(cache_key)


def restrict_file_to_current_user(path: str | Path, *, descriptor: int | None = None) -> None:
    target = Path(path)
    if not _is_windows():
        if descriptor is not None:
            os.fchmod(descriptor, 0o600)
        else:
            target.chmod(0o600)
        return
    _restrict_windows_path(target, "(F)")

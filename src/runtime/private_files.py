"""Cross-platform permissions for files containing local credentials."""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path


def _is_windows() -> bool:
    return os.name == "nt"


def restrict_file_to_current_user(path: str | Path, *, descriptor: int | None = None) -> None:
    target = Path(path)
    if not _is_windows():
        if descriptor is not None:
            os.fchmod(descriptor, 0o600)
        else:
            target.chmod(0o600)
        return

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
    sid = rows[0][1].strip()
    try:
        subprocess.run(
            ["icacls", str(target), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("无法限制敏感配置文件的访问权限。") from exc

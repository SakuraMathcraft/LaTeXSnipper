"""Private local discovery file for Automation API clients."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from runtime.app_paths import app_state_dir
from runtime.private_files import ensure_private_directory


CONNECTION_FILENAME = "automation-api.json"


def default_connection_file() -> Path:
    return app_state_dir() / CONNECTION_FILENAME


def write_connection_file(
    *,
    base_url: str,
    token: str,
    pid: int | None = None,
    path: Path | None = None,
) -> Path:
    target = path or default_connection_file()
    ensure_private_directory(target.parent)
    payload = {
        "base_url": base_url,
        "api_version": "1",
        "pid": int(pid if pid is not None else os.getpid()),
        "token": token,
    }
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
        return target
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise


def remove_connection_file(path: Path | None = None) -> None:
    try:
        (path or default_connection_file()).unlink(missing_ok=True)
    except OSError:
        pass

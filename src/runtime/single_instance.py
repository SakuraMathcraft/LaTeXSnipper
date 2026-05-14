"""Single-instance file lock helpers."""

from __future__ import annotations

import os
import time
from pathlib import Path

_single_instance_lock = None


def release_single_instance_lock() -> None:
    """Release the single-instance file lock explicitly."""
    global _single_instance_lock
    fh = _single_instance_lock
    _single_instance_lock = None
    if fh is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            try:
                fh.seek(0)
            except Exception:
                pass
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass


def ensure_single_instance() -> bool:
    """Prevent multiple GUI instances using a file lock."""
    global _single_instance_lock
    lock_dir = Path.home() / ".latexsnipper"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "instance.lock"
    restart_flag = os.environ.get("LATEXSNIPPER_RESTART") == "1"
    attempts = 150 if restart_flag else 1
    delay = 0.2

    if os.name == "nt":
        try:
            import msvcrt

            for _ in range(attempts):
                fh = open(lock_file, "a+", encoding="utf-8")
                try:
                    fh.seek(0)
                except Exception:
                    pass
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    fh.close()
                    if restart_flag:
                        time.sleep(delay)
                        continue
                    return False
                _single_instance_lock = fh
                return True
            return False
        except Exception:
            return True

    try:
        import fcntl

        for _ in range(attempts):
            fh = open(lock_file, "a+", encoding="utf-8")
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                fh.close()
                if restart_flag:
                    time.sleep(delay)
                    continue
                return False
            _single_instance_lock = fh
            return True
        return False
    except Exception:
        return True

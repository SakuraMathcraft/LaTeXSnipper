#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) in sys.path:
    sys.path.remove(str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from linux_hotkey_packaging import missing_hotkey_modules  # noqa: E402


def main() -> int:
    archived_modules = {line.strip() for line in sys.stdin if line.strip()}
    missing = missing_hotkey_modules(archived_modules)
    if missing:
        print(
            "Missing required Linux hotkey modules: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

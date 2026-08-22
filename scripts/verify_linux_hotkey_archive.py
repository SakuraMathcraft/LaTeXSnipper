#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.linux_hotkey_packaging import REQUIRED_LINUX_HOTKEY_MODULES


def main() -> int:
    archived_modules = {line.strip() for line in sys.stdin if line.strip()}
    missing = [
        name
        for name in REQUIRED_LINUX_HOTKEY_MODULES
        if name not in archived_modules
    ]
    if missing:
        print(
            "Missing required Linux hotkey modules: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

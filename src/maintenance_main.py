"""Frozen, Qt-free maintenance executable used by the desktop installer."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    root = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(root), str(root / "src")]

from update.updater_entry import main

if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for source_path in (ROOT, SRC):
    source = str(source_path)
    if source in sys.path:
        sys.path.remove(source)
    sys.path.insert(0, source)

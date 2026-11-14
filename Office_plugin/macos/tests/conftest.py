from __future__ import annotations

import sys
from pathlib import Path

# The add-in host is its own package; it must not need the desktop app's src/.
HOST = Path(__file__).resolve().parents[1] / "host"
if str(HOST) not in sys.path:
    sys.path.insert(0, str(HOST))

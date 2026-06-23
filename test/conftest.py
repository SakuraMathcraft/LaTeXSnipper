from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime.native_runtime_preload import preload_onnxruntime_before_qt  # noqa: E402

preload_onnxruntime_before_qt()

from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_handwriting_recognizer_imports_without_numpy() -> None:
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("blocked numpy")
        return real_import(name, globals, locals, fromlist, level)

    module_path = SRC / "handwriting" / "recognizer.py"
    spec = importlib.util.spec_from_file_location(
        "handwriting_recognizer_no_numpy", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with mock.patch("builtins.__import__", side_effect=blocked_import):
        spec.loader.exec_module(module)

    assert callable(module.qimage_to_pil)

"""Verify the real UI import graph in an isolated interpreter."""

import os
from pathlib import Path
import subprocess
import sys


def test_main_window_imports_without_test_stubs():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path[:0] = sys.argv[1:]; from ui.main_window import MainWindow; assert callable(MainWindow)", str(root / "src"), str(root)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for source_path in (ROOT, SRC):
    source = str(source_path)
    if source in sys.path:
        sys.path.remove(source)
    sys.path.insert(0, source)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config) -> None:
    if sys.platform != "win32":
        return

    def quiet_inaccessible_pytest_garbage() -> None:
        # Register before pytest's warning context so this filter survives its
        # cleanup and applies to the numbered-temp-dir callback at process exit.
        # Do not hide test warnings or other filesystem failures.
        warnings.filterwarnings(
            "ignore",
            message=r"(?s)^\(rm_rf\) unknown function <built-in function scandir> when removing .*[/\\]garbage-[^\r\n]*:\s*<class 'PermissionError'>: \[WinError 5\].*",
            category=pytest.PytestWarning,
            module=r"^_pytest\.pathlib$",
        )

    config.add_cleanup(quiet_inaccessible_pytest_garbage)

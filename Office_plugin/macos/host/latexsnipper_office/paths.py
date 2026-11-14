"""File locations of the standalone add-in host.

The add-in keeps its own state; the only path it shares with the LaTeXSnipper
desktop app is the Automation API discovery file, which is the published
contract for local clients (docs/automation_api.md).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LaTeXSnipper Office"
BUNDLE_ID = "com.mathcraft.latexsnipper.office"


def state_directory() -> Path:
    """Certificate, settings and logs of the add-in host."""

    return Path.home() / "Library/Application Support" / APP_NAME


def automation_connection_file() -> Path:
    """Where the desktop app publishes its local Automation API endpoint."""

    return Path.home() / "Library/Application Support/LaTeXSnipper/automation-api.json"


def ensure_private_directory(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    return directory


def resources_root() -> Path:
    """Bundled resources when frozen, otherwise the repository checkout."""

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[4]

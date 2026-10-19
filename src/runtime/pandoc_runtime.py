"""Locate installation-owned Pandoc or the developer's PATH executable."""

import shutil
from pathlib import Path

from runtime.installed_resources import installed_resources


def resolve_pandoc() -> Path | None:
    resources = installed_resources()
    if resources is not None:
        name = "pandoc.exe" if resources.manifest.platform == "windows" else "pandoc"
        return resources.resource("runtime", f"pandoc/{name}")
    found = shutil.which("pandoc")
    return Path(found) if found else None

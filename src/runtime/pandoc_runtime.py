"""Locate Pandoc in the application's executable search path."""

import os
import shutil
from pathlib import Path


def resolve_pandoc() -> Path | None:
    name = "pandoc.exe" if os.name == "nt" else "pandoc"
    for entry in os.get_exec_path():
        directory = Path(entry)
        if directory.is_absolute() and shutil.which(str(directory / name)):
            return directory / name
    return None

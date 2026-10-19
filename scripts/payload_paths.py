"""Confine payload cleanup to an explicitly owned staging tree."""

import shutil
from pathlib import Path


def remove_owned(path: Path, owner: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.resolve().is_relative_to(owner.resolve()):
        raise ValueError("Payload cleanup escaped its staging directory")
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)

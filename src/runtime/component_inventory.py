"""Inventory and verify immutable component files without importing UI dependencies."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from runtime.distribution_manifest import (
    BundleSeal,
    Component,
    FileRecord,
    ManifestError,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory_component(root: Path) -> tuple[FileRecord, ...]:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ManifestError("Component source must be a directory")
    records = []
    for directory, directories, files in os.walk(root, followlinks=False):
        base = Path(directory)
        links = [name for name in directories if (base / name).is_symlink()]
        for name in links:
            directories.remove(name)
        for name in files + links:
            path = base / name
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            mode = stat.S_IMODE(metadata.st_mode) & 0o777
            if path.is_symlink():
                target = os.readlink(path)
                encoded = target.encode("utf-8")
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    raise ManifestError(f"External component symlink: {relative}")
                records.append(
                    FileRecord(
                        relative,
                        hashlib.sha256(encoded).hexdigest(),
                        len(encoded),
                        mode,
                        "symlink",
                        target,
                    )
                )
            elif path.is_file():
                records.append(
                    FileRecord(relative, file_sha256(path), metadata.st_size, mode)
                )
            else:
                raise ManifestError(f"Unsupported resource type: {relative}")
    if not records:
        raise ManifestError("Cannot package an empty component")
    return tuple(sorted(records, key=lambda item: item.path))


def verify_component(
    root: Path, component: Component | BundleSeal, *, exact: bool = True
) -> tuple[str, ...]:
    """Return damaged paths; never use a symlink to read outside its resource root."""
    root = Path(root)
    if root.is_symlink():
        return tuple(record.path for record in component.files)
    root = root.resolve()
    damaged = []
    for record in component.files:
        path = root.joinpath(*record.path.split("/"))
        try:
            if not path.resolve(strict=True).is_relative_to(root):
                damaged.append(record.path)
                continue
            if record.kind == "symlink":
                valid = path.is_symlink() and os.readlink(path) == record.target
            else:
                valid = (
                    not path.is_symlink()
                    and path.is_file()
                    and path.stat().st_size == record.size
                    and file_sha256(path) == record.sha256
                )
            if valid and os.name != "nt":
                valid = stat.S_IMODE(path.lstat().st_mode) & 0o777 == record.mode
            if not valid:
                damaged.append(record.path)
        except (OSError, RuntimeError):
            damaged.append(record.path)
    if exact:
        expected = {item.path for item in component.files}
        for directory, directories, files in os.walk(root, followlinks=False):
            base = Path(directory)
            links = [name for name in directories if (base / name).is_symlink()]
            for name in links:
                directories.remove(name)
            for name in files + links:
                relative = (base / name).relative_to(root).as_posix()
                if relative not in expected:
                    damaged.append(relative)
    return tuple(sorted(set(damaged)))

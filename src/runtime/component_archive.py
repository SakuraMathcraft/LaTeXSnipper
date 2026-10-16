"""Confined archive extraction shared by production builds and component updates."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tarfile
import zipfile

from runtime.component_inventory import verify_component
from runtime.distribution_manifest import BundleSeal, Component, FileRecord, ManifestError, safe_relative_path


def _member_path(root: Path, name: str) -> Path:
    while name.startswith('./'):
        name = name[2:]
    name = safe_relative_path(name.rstrip('/'))
    target = root.joinpath(*name.split('/'))
    if not target.parent.resolve().is_relative_to(root):
        raise ManifestError('Archive entry escapes the extraction root')
    return target


def _create_link(root: Path, target: Path, link: str, *, hard: bool = False) -> None:
    relative = target.relative_to(root).as_posix()
    if hard:
        source = _member_path(root, link)
        link = os.path.relpath(source, target.parent).replace('\\', '/')
    encoded = link.encode('utf-8')
    FileRecord(relative, hashlib.sha256(encoded).hexdigest(), len(encoded), 0o777, 'symlink', link)
    source = (target.parent / link).resolve()
    if not source.is_relative_to(root) or target.exists() or target.is_symlink():
        raise ManifestError('Invalid archive link')
    target.parent.mkdir(parents=True, exist_ok=True)
    if hard:
        os.link(source, target)
    else:
        os.symlink(link, target, target_is_directory=source.is_dir())


def extract_archive(archive: Path, destination: Path, *, component: Component | BundleSeal | None = None) -> None:
    """Extract only ordinary files, directories and confined links into a fresh directory."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    links = []
    seen = set()
    expected = {record.path: record for record in component.files} if component else None
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                target = _member_path(destination, member.filename)
                key = target.relative_to(destination).as_posix().casefold()
                if key in seen:
                    raise ManifestError('Duplicate archive entry')
                seen.add(key)
                mode = member.external_attr >> 16
                if not member.is_dir() and expected is not None:
                    record = expected.get(target.relative_to(destination).as_posix())
                    if record is None or member.file_size != record.size or stat.S_ISLNK(mode) != (record.kind == 'symlink'):
                        raise ManifestError('Component archive entry does not match its declared inventory')
                if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                    raise ManifestError('Unsupported archive entry type')
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif stat.S_ISLNK(mode):
                    links.append((target, package.read(member).decode('utf-8'), False))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(member) as incoming, target.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                    target.chmod(stat.S_IMODE(mode) & 0o777 or 0o644)
    else:
        if component is not None:
            raise ManifestError('Component payloads must be ZIP archives')
        with tarfile.open(archive) as package:
            for member in package:
                if member.isdir() and member.name.rstrip('/') in {'', '.'}:
                    continue
                target = _member_path(destination, member.name)
                key = target.relative_to(destination).as_posix().casefold()
                if key in seen:
                    raise ManifestError('Duplicate archive entry')
                seen.add(key)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.issym() or member.islnk():
                    links.append((target, member.linkname, member.islnk()))
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.extractfile(member) as incoming, target.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                    target.chmod(member.mode & 0o777)
                else:
                    raise ManifestError('Unsupported archive entry type')
    for target, link, hard in links:
        _create_link(destination, target, link, hard=hard)
    if component is not None and verify_component(destination, component):
        raise ManifestError('Extracted component does not match its release inventory')

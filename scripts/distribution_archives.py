"""Verified downloads of locked build inputs."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

from runtime.component_inventory import file_sha256
from runtime.distribution_manifest import Artifact, ManifestError, safe_relative_path


def download_artifact(artifact: Artifact, cache: Path) -> Path:
    cache = cache.resolve()
    name = unquote(urlsplit(artifact.url).path.rsplit("/", 1)[-1])
    safe_relative_path(name)
    if "/" in name:
        raise ManifestError("Archive name must be a single file name")
    directory = cache / artifact.sha256
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(cache):
        raise ManifestError("Download cache escapes its resource root")
    target = directory / name
    if target.exists():
        if target.is_symlink():
            raise ManifestError("Download cache must not contain symlink artifacts")
        if (
            target.stat().st_size == artifact.size
            and file_sha256(target) == artifact.sha256
        ):
            return target
    handle, temporary = tempfile.mkstemp(
        prefix="download-", suffix=".part", dir=directory
    )
    digest = hashlib.sha256()
    count = 0
    print(f"Download {name} ({artifact.size} bytes)", flush=True)
    try:
        with (
            os.fdopen(handle, "wb") as stream,
            requests.get(artifact.url, stream=True, timeout=(15, 60)) as response,
        ):
            response.raise_for_status()
            for block in response.iter_content(1024 * 1024):
                stream.write(block)
                digest.update(block)
                count += len(block)
        if count != artifact.size or digest.hexdigest() != artifact.sha256:
            raise ManifestError(f"Archive integrity failure: {name}")
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)

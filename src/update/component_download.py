"""Download whole immutable components with resumable, verified caches."""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path

import requests

from runtime.component_inventory import file_sha256
from runtime.distribution_manifest import Artifact, ManifestError, safe_relative_path

logger = logging.getLogger(f"latexsnipper.{__name__}")


class DownloadCancelled(Exception):
    pass


class DownloadControl:
    def __init__(self) -> None:
        self._gate = threading.Event()
        self._gate.set()
        self._cancelled = threading.Event()

    def pause(self, paused: bool) -> None:
        self._gate.clear() if paused else self._gate.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._gate.set()

    def checkpoint(self) -> None:
        while not self._gate.wait(0.1):
            if self._cancelled.is_set():
                raise DownloadCancelled("Component download cancelled")
        if self._cancelled.is_set():
            raise DownloadCancelled("Component download cancelled")


def download_component(
    artifact: Artifact,
    cache: Path,
    *,
    control: DownloadControl | None = None,
    progress: Callable[[int, int], None] | None = None,
    session: requests.Session | None = None,
    cache_key: str | None = None,
) -> Path:
    """Only return a complete payload with the exact declared size and SHA256."""
    control = control or DownloadControl()
    control.checkpoint()
    cache = cache.resolve()
    key = safe_relative_path(cache_key or artifact.sha256)
    if "/" in key:
        raise ManifestError("Component cache identity must be a single path segment")
    directory = cache / key
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.resolve().is_relative_to(cache):
        raise ManifestError("Component cache redirects outside its root")
    target, partial = directory / "payload", directory / "payload.part"
    if target.is_symlink() or partial.is_symlink():
        raise ManifestError("Component cache payload must not be a symbolic link")
    if (
        target.is_file()
        and target.stat().st_size == artifact.size
        and file_sha256(target) == artifact.sha256
    ):
        if progress:
            progress(artifact.size, artifact.size)
        return target
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset >= artifact.size:
        if offset == artifact.size and file_sha256(partial) == artifact.sha256:
            os.replace(partial, target)
            return target
        partial.unlink()
        offset = 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    logger.info(
        "下载发行资源 sha256=%s bytes=%s resume=%s",
        artifact.sha256,
        artifact.size,
        offset,
    )
    client = session or requests.Session()
    try:
        with client.get(
            artifact.url, headers=headers, stream=True, timeout=(15, 30)
        ) as response:
            response.raise_for_status()
            if response.status_code == 206:
                content_range = re.fullmatch(
                    r"bytes ([0-9]+)-([0-9]+)/([0-9]+)",
                    response.headers.get("Content-Range", ""),
                )
                if not content_range or tuple(map(int, content_range.groups())) != (
                    offset,
                    artifact.size - 1,
                    artifact.size,
                ):
                    raise ManifestError(
                        "Component resume range does not match its declared size"
                    )
            elif response.status_code == 200:
                offset = 0
            else:
                raise ManifestError("Unexpected component download status")
            count = offset
            with partial.open("ab" if offset else "wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    control.checkpoint()
                    count += len(block)
                    if count > artifact.size:
                        raise ManifestError(
                            "Component download exceeds its declared size"
                        )
                    stream.write(block)
                    if progress:
                        progress(count, artifact.size)
                stream.flush()
                os.fsync(stream.fileno())
        control.checkpoint()
        if count != artifact.size:
            raise OSError("Component download interrupted; partial payload retained")
        if file_sha256(partial) != artifact.sha256:
            raise ManifestError("Component download SHA256 does not match its release")
        os.replace(partial, target)
        return target
    except ManifestError:
        partial.unlink(missing_ok=True)
        raise
    finally:
        if session is None:
            client.close()

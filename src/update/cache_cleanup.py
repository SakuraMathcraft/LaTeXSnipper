"""Reclaim finished update tasks and expired downloads from the app cache."""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from runtime.app_paths import app_cache_dir
from runtime.deployment_feedback import cleanup_deployment_task
from runtime.distribution_manifest import read_json
from runtime.installation_layout import deployment_directory
from runtime.installed_resources import current_target
from update.component_download import DOWNLOAD_CACHE_LOCK, discard_download
from update.deployment_transaction import needs_recovery
from update.updater_entry import wait_for_exit

logger = logging.getLogger(f"latexsnipper.{__name__}")
DOWNLOAD_RETENTION_SECONDS = 7 * 24 * 60 * 60
ORPHAN_RETENTION_SECONDS = 24 * 60 * 60
_FINISHED = {"committed", "rolled-back", "failed"}


def _owned_directory(path: Path, parent: Path) -> bool:
    return path.is_dir() and path.parent == parent and path.resolve() == path


def _running(pid: object) -> bool:
    if type(pid) is not int or pid < 1:
        return False
    if pid == os.getpid():
        return True
    try:
        wait_for_exit(pid, timeout=0.01)
        return False
    except (OSError, ValueError, TimeoutError):
        return True


def _cleanup_task(directory: Path, cutoff: float) -> Path | None:
    request_path = directory / "request.json"
    if not request_path.is_file():
        if directory.stat().st_mtime < cutoff:
            cleanup_deployment_task(directory)
        return None
    request = read_json(request_path)
    staged = Path(request["staged"]).parent if request.get("staged") else None
    result_path = directory / "deployment-result.json"
    result = read_json(result_path) if result_path.is_file() else {}
    watcher_path = directory / "watcher.json"
    watcher = read_json(watcher_path) if watcher_path.is_file() else {}
    pids = [result.get("pid"), watcher.get("pid")]
    if result.get("state") not in _FINISHED:
        pids.append(request.get("wait_pid"))
    root = request.get("root")
    pending = bool(
        root and needs_recovery(deployment_directory(Path(root), current_target()[0]))
    )
    if not pending and not any(_running(pid) for pid in pids):
        cleanup_deployment_task(directory)
    return staged if directory.exists() else None


def cleanup_update_cache() -> None:
    """Run after startup; preserve live helpers and unfinished transactions."""
    declared = app_cache_dir().absolute()
    cache = declared.resolve()
    if cache != declared:
        logger.warning("跳过重定向的更新缓存目录: %s", declared)
        return
    cutoff = time.time() - ORPHAN_RETENTION_SECONDS
    protected: set[Path] = set()
    prune_staging = True
    for directory in cache.iterdir():
        if not directory.name.startswith(("deployment-", "recovery-")):
            continue
        try:
            if _owned_directory(directory, cache):
                staged = _cleanup_task(directory, cutoff)
                if staged is not None:
                    protected.add(staged)
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("更新任务缓存暂未回收: %s", directory, exc_info=True)
            # A malformed request must not cause its staging to be discarded.
            prune_staging = False
    for directory in cache.glob("component-update-*") if prune_staging else ():
        try:
            if (
                _owned_directory(directory, cache)
                and directory not in protected
                and directory.stat().st_mtime < cutoff
            ):
                shutil.rmtree(directory)
        except OSError:
            logger.warning("更新暂存目录暂未回收: %s", directory, exc_info=True)
    downloads = cache / "components"
    if not _owned_directory(downloads, cache):
        return
    with DOWNLOAD_CACHE_LOCK:
        cutoff = time.time() - DOWNLOAD_RETENTION_SECONDS
        for directory in downloads.iterdir():
            try:
                if not _owned_directory(directory, downloads):
                    continue
                files = list(directory.iterdir())
                if any(path.name not in {"payload", "payload.part"} for path in files):
                    continue
                modified = max(
                    [
                        directory.stat().st_mtime,
                        *(path.stat().st_mtime for path in files),
                    ]
                )
                if (
                    (directory / "payload").is_file()
                    and not (directory / "payload.part").exists()
                ) or modified < cutoff:
                    discard_download(directory / "payload")
            except OSError:
                logger.warning("过期更新包暂未回收: %s", directory, exc_info=True)

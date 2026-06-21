"""macOS-only local data cleanup helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import sys

from runtime.app_paths import APP_SUPPORT_NAME


@dataclass(frozen=True)
class MacOSCleanupResult:
    removed: list[str]
    missing: list[str]
    failed: list[tuple[str, str]]


def _macos_library_dir(name: str) -> Path:
    return Path.home() / "Library" / name / APP_SUPPORT_NAME


def macos_cleanup_targets(include_config: bool = False) -> list[Path]:
    """Return app-owned user data paths that may be removed on macOS."""
    if sys.platform != "darwin":
        return []

    support_dir = _macos_library_dir("Application Support")
    targets = [
        support_dir / "deps",
        _macos_library_dir("Caches"),
        _macos_library_dir("Logs"),
    ]
    if include_config:
        targets.append(support_dir)
    return targets


def _allowed_roots(include_config: bool) -> tuple[Path, ...]:
    roots = [
        _macos_library_dir("Application Support") / "deps",
        _macos_library_dir("Caches"),
        _macos_library_dir("Logs"),
    ]
    if include_config:
        roots.append(_macos_library_dir("Application Support"))
    return tuple(roots)


def _is_allowed_target(target: Path, allowed_roots: tuple[Path, ...]) -> bool:
    absolute_target = target.expanduser().absolute()
    for root in allowed_roots:
        absolute_root = root.expanduser().absolute()
        if absolute_target == absolute_root or absolute_target.is_relative_to(absolute_root):
            return True
    return False


def cleanup_macos_local_data(include_config: bool = False) -> MacOSCleanupResult:
    """Remove downloaded deps, cache, and logs for the macOS app.

    Configuration is preserved by default. Passing ``include_config=True`` is
    reserved for explicit full-reset flows.
    """
    removed: list[str] = []
    missing: list[str] = []
    failed: list[tuple[str, str]] = []

    if sys.platform != "darwin":
        return MacOSCleanupResult(removed=removed, missing=missing, failed=failed)

    allowed_roots = _allowed_roots(include_config)
    for target in macos_cleanup_targets(include_config=include_config):
        target_str = str(target)
        if not _is_allowed_target(target, allowed_roots):
            failed.append((target_str, "Refusing to remove a path outside LaTeXSnipper user data."))
            continue
        if not target.exists() and not target.is_symlink():
            missing.append(target_str)
            continue
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
            else:
                shutil.rmtree(target)
            removed.append(target_str)
        except Exception as exc:
            failed.append((target_str, str(exc)))

    return MacOSCleanupResult(removed=removed, missing=missing, failed=failed)

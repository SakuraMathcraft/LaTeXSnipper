"""Installed weights and the shared MathCraft cache used by desktop workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mathcraft_ocr.cache import ModelCacheState, default_user_models_dir, inspect_manifest_roots
from mathcraft_ocr.manifest import Manifest, load_manifest

if TYPE_CHECKING:
    from runtime.installed_resources import InstalledResources


@dataclass(frozen=True)
class DesktopModelResources:
    manifest: Manifest
    installed_root: Path | None
    cache_root: Path
    manifest_path: Path | None = None

    @property
    def roots(self) -> tuple[Path, ...]:
        return (self.installed_root, self.cache_root) if self.installed_root else (self.cache_root,)

    def inspect(self) -> dict[str, ModelCacheState]:
        return inspect_manifest_roots(self.roots, self.manifest)


def desktop_model_resources(resources: InstalledResources | None) -> DesktopModelResources:
    cache_root = default_user_models_dir()
    if resources is not None:
        manifest_path = resources.resource('models', 'models.v1.json')
        return DesktopModelResources(load_manifest(manifest_path), resources.root / 'models',
                                     cache_root, manifest_path)
    manifest = load_manifest()
    return DesktopModelResources(manifest, None, cache_root)

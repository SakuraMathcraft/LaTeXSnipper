"""Resolve the single model root owned by each desktop execution mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mathcraft_ocr.cache import (
    ModelCacheState,
    default_user_models_dir,
    inspect_manifest_cache,
)
from mathcraft_ocr.manifest import Manifest, load_manifest

if TYPE_CHECKING:
    from runtime.installed_resources import InstalledResources


@dataclass(frozen=True)
class DesktopModelResources:
    manifest: Manifest
    root: Path
    manifest_path: Path | None = None

    def inspect(self) -> dict[str, ModelCacheState]:
        return inspect_manifest_cache(self.root, self.manifest)


def desktop_model_resources(
    resources: InstalledResources | None,
) -> DesktopModelResources:
    if resources is not None:
        manifest_path = resources.resource("models", "models.v1.json")
        return DesktopModelResources(
            load_manifest(manifest_path),
            resources.root / "models",
            manifest_path,
        )
    manifest = load_manifest()
    return DesktopModelResources(manifest, default_user_models_dir())

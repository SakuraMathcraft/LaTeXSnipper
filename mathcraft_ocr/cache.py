# coding: utf-8

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, ModelSpec


def default_cache_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "MathCraft" / "models"
    return Path.home() / ".mathcraft" / "models"


def resolve_cache_dir(cache_dir: str | Path | None = None) -> Path:
    if cache_dir:
        return Path(cache_dir)
    override = os.environ.get("MATHCRAFT_HOME", "").strip()
    if override:
        return Path(override)
    return default_cache_dir()


@dataclass(frozen=True)
class ModelCacheState:
    model_id: str
    model_dir: Path
    exists: bool
    complete: bool
    missing_files: tuple[str, ...]

    @property
    def broken(self) -> bool:
        return self.exists and not self.complete


def model_dir(root: str | Path, model_id: str) -> Path:
    return Path(root) / model_id


def inspect_model_cache(root: str | Path, spec: ModelSpec) -> ModelCacheState:
    target = model_dir(root, spec.model_id)
    exists = target.is_dir()
    missing: list[str] = []
    if exists:
        for file_spec in spec.files:
            if not (target / file_spec.path).is_file():
                missing.append(file_spec.path)
    else:
        missing = [item.path for item in spec.files]
    return ModelCacheState(
        model_id=spec.model_id,
        model_dir=target,
        exists=exists,
        complete=(exists and not missing),
        missing_files=tuple(missing),
    )


def inspect_manifest_cache(
    root: str | Path, manifest: Manifest, include_optional: bool = True
) -> dict[str, ModelCacheState]:
    states: dict[str, ModelCacheState] = {}
    for model_id, spec in manifest.models.items():
        if spec.optional and not include_optional:
            continue
        states[model_id] = inspect_model_cache(root, spec)
    return states

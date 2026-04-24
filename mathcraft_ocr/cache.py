# coding: utf-8

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, ModelSpec


def default_user_models_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "MathCraft" / "models"
    return Path.home() / ".mathcraft" / "models"


def resolve_user_models_dir(cache_dir: str | Path | None = None) -> Path:
    if cache_dir:
        return Path(cache_dir)
    override = os.environ.get("MATHCRAFT_HOME", "").strip()
    if override:
        return Path(override)
    return default_user_models_dir()


def default_cache_dir() -> Path:
    return default_user_models_dir()


def resolve_cache_dir(cache_dir: str | Path | None = None) -> Path:
    return resolve_user_models_dir(cache_dir)


def bundled_models_dir() -> Path | None:
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "MathCraft" / "models")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "MathCraft" / "models")
        candidates.append(exe_dir / "MathCraft" / "models")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def resolve_model_roots(
    cache_dir: str | Path | None = None,
    bundled_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    bundled = Path(bundled_dir) if bundled_dir else bundled_models_dir()
    if bundled and bundled.is_dir():
        roots.append(bundled)
    user_root = resolve_user_models_dir(cache_dir)
    if user_root not in roots:
        roots.append(user_root)
    return tuple(roots)


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
            file_path = target / file_spec.path
            if not file_path.is_file():
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


def inspect_model_roots(roots: tuple[Path, ...] | list[Path], spec: ModelSpec) -> ModelCacheState:
    states = [inspect_model_cache(root, spec) for root in roots]
    for state in states:
        if state.complete:
            return state
    for state in states:
        if state.exists:
            return state
    return states[-1]


def inspect_manifest_cache(
    root: str | Path, manifest: Manifest, include_optional: bool = True
) -> dict[str, ModelCacheState]:
    states: dict[str, ModelCacheState] = {}
    for model_id, spec in manifest.models.items():
        if spec.optional and not include_optional:
            continue
        states[model_id] = inspect_model_cache(root, spec)
    return states


def inspect_manifest_roots(
    roots: tuple[Path, ...] | list[Path],
    manifest: Manifest,
    include_optional: bool = True,
) -> dict[str, ModelCacheState]:
    states: dict[str, ModelCacheState] = {}
    for model_id, spec in manifest.models.items():
        if spec.optional and not include_optional:
            continue
        states[model_id] = inspect_model_roots(roots, spec)
    return states

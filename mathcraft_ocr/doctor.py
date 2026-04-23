# coding: utf-8

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .cache import inspect_manifest_cache, resolve_cache_dir
from .manifest import Manifest, load_manifest
from .providers import ProviderInfo, detect_providers


@dataclass(frozen=True)
class DoctorReport:
    python_executable: str
    cache_dir: Path
    manifest_version: int
    provider_info: ProviderInfo
    cache_states: dict[str, object]
    supported_runtimes: dict[str, str]


def run_doctor(
    *,
    cache_dir: str | Path | None = None,
    manifest: Manifest | None = None,
    provider_preference: str = "auto",
    include_optional: bool = True,
) -> DoctorReport:
    manifest_obj = manifest or load_manifest()
    cache_root = resolve_cache_dir(cache_dir)
    states = inspect_manifest_cache(
        cache_root, manifest_obj, include_optional=include_optional
    )
    provider_info = detect_providers(prefer=provider_preference)
    return DoctorReport(
        python_executable=sys.executable,
        cache_dir=cache_root,
        manifest_version=manifest_obj.version,
        provider_info=provider_info,
        cache_states=states,
        supported_runtimes={
            model_id: spec.runtime for model_id, spec in manifest_obj.models.items()
        },
    )

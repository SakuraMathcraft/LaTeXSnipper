# coding: utf-8

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path

from ..providers import GPU_PROVIDER_NAMES, ProviderInfo


def _ort():
    return importlib.import_module("onnxruntime")


def session_providers(provider_info: ProviderInfo) -> list[str]:
    available = list(provider_info.available_providers)
    active = provider_info.active_provider
    if active and active in GPU_PROVIDER_NAMES and "CPUExecutionProvider" in available:
        return [active, "CPUExecutionProvider"]
    if "CPUExecutionProvider" in available:
        return ["CPUExecutionProvider"]
    return available


def create_session(model_path: str | Path, provider_info: ProviderInfo):
    model_path = str(Path(model_path).resolve())
    providers = tuple(session_providers(provider_info))
    return _create_session_cached(model_path, providers)


@lru_cache(maxsize=16)
def _create_session_cached(model_path: str, providers: tuple[str, ...]):
    ort = _ort()
    return ort.InferenceSession(model_path, providers=list(providers))


def clear_session_cache() -> None:
    _create_session_cached.cache_clear()

# coding: utf-8

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass

from .errors import ProviderError


GPU_PROVIDER_NAMES = (
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
)


@dataclass(frozen=True)
class ProviderInfo:
    available_providers: tuple[str, ...]
    active_provider: str | None
    device: str
    gpu_requested: bool
    gpu_runtime_ok: bool
    cpu_fallback: bool


def detect_providers(prefer: str = "auto") -> ProviderInfo:
    prefer_norm = (prefer or "auto").strip().lower()
    if prefer_norm not in {"auto", "cpu", "gpu"}:
        raise ProviderError(f"unsupported provider preference: {prefer}")
    try:
        ort = importlib.import_module("onnxruntime")
    except Exception as exc:  # pragma: no cover - import environment dependent
        raise ProviderError(f"failed to import onnxruntime: {exc}") from exc

    try:
        available = tuple(ort.get_available_providers())
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        raise ProviderError(f"failed to query ONNX providers: {exc}") from exc

    force_cpu = os.environ.get("MATHCRAFT_FORCE_ORT_CPU", "").strip() == "1"
    gpu_candidates = tuple(name for name in GPU_PROVIDER_NAMES if name in available)
    gpu_visible = bool(gpu_candidates)
    if force_cpu:
        return ProviderInfo(
            available_providers=available,
            active_provider="CPUExecutionProvider" if "CPUExecutionProvider" in available else None,
            device="cpu",
            gpu_requested=(prefer_norm in {"auto", "gpu"}),
            gpu_runtime_ok=False,
            cpu_fallback=True,
        )
    if prefer_norm == "cpu":
        return ProviderInfo(
            available_providers=available,
            active_provider="CPUExecutionProvider" if "CPUExecutionProvider" in available else None,
            device="cpu",
            gpu_requested=False,
            gpu_runtime_ok=False,
            cpu_fallback=False,
        )
    if gpu_visible:
        return ProviderInfo(
            available_providers=available,
            active_provider=gpu_candidates[0],
            device="gpu",
            gpu_requested=True,
            gpu_runtime_ok=True,
            cpu_fallback=False,
        )
    return ProviderInfo(
        available_providers=available,
        active_provider="CPUExecutionProvider" if "CPUExecutionProvider" in available else None,
        device="cpu",
        gpu_requested=(prefer_norm in {"auto", "gpu"}),
        gpu_runtime_ok=False,
        cpu_fallback=(prefer_norm == "gpu"),
    )

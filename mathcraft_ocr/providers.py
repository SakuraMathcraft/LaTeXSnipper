# coding: utf-8

from __future__ import annotations

import importlib
from dataclasses import dataclass, replace

from .devices import confirm_device_identity, resolve_device_identity
from .errors import ProviderError


GPU_PROVIDER_NAMES = (
    "CUDAExecutionProvider",
    "TensorrtExecutionProvider",
    "DmlExecutionProvider",
)


@dataclass(frozen=True)
class ProviderInfo:
    available_providers: tuple[str, ...]
    active_provider: str | None
    device: str
    gpu_requested: bool
    gpu_runtime_ok: bool
    device_id: int | None = None
    device_name: str = ""
    device_uuid: str = ""
    device_verified: bool = False

    @property
    def use_cuda(self) -> bool:
        return self.active_provider in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}

    @property
    def use_dml(self) -> bool:
        return self.active_provider == "DmlExecutionProvider"


def detect_providers(prefer: str = "auto") -> ProviderInfo:
    prefer_norm = (prefer or "auto").strip().lower()
    if prefer_norm not in {"auto", "cpu", "gpu"}:
        raise ProviderError(f"unsupported provider preference: {prefer}")
    try:
        ort = importlib.import_module("onnxruntime")
    except Exception as exc:  # pragma: no cover - import environment dependent
        raise ProviderError(f"failed to import onnxruntime: {exc}") from exc

    get_available_providers = getattr(ort, "get_available_providers", None)
    if not callable(get_available_providers):
        origin = getattr(ort, "__file__", None) or "<namespace package>"
        raise ProviderError(
            "onnxruntime dependency is incomplete: missing get_available_providers "
            f"(origin={origin})"
        )

    try:
        available = tuple(get_available_providers())
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        raise ProviderError(f"failed to query ONNX providers: {exc}") from exc

    gpu_candidates = tuple(name for name in GPU_PROVIDER_NAMES if name in available)
    gpu_visible = bool(gpu_candidates)
    if prefer_norm == "cpu":
        if "CPUExecutionProvider" not in available:
            raise ProviderError(f"CPUExecutionProvider unavailable: {available}")
        return _provider_info(
            available_providers=available,
            active_provider="CPUExecutionProvider",
            device="cpu",
            gpu_requested=False,
            gpu_runtime_ok=False,
        )
    if gpu_visible:
        return _provider_info(
            available_providers=available,
            active_provider=gpu_candidates[0],
            device="gpu",
            gpu_requested=True,
            gpu_runtime_ok=True,
        )
    if prefer_norm == "gpu":
        raise ProviderError(
            f"GPU provider was requested but none is available: {available}"
        )
    if "CPUExecutionProvider" not in available:
        raise ProviderError(f"no supported ONNX execution provider is available: {available}")
    return _provider_info(
        available_providers=available,
        active_provider="CPUExecutionProvider",
        device="cpu",
        gpu_requested=False,
        gpu_runtime_ok=False,
    )


def _provider_info(
    *,
    available_providers: tuple[str, ...],
    active_provider: str,
    device: str,
    gpu_requested: bool,
    gpu_runtime_ok: bool,
) -> ProviderInfo:
    device_id = 0 if active_provider in GPU_PROVIDER_NAMES else None
    identity = resolve_device_identity(active_provider, device_id)
    return ProviderInfo(
        available_providers=available_providers,
        active_provider=active_provider,
        device=device,
        gpu_requested=gpu_requested,
        gpu_runtime_ok=gpu_runtime_ok,
        device_id=identity.device_id,
        device_name=identity.name,
        device_uuid=identity.uuid,
        device_verified=identity.verified,
    )


def confirm_provider_device(provider_info: ProviderInfo) -> ProviderInfo:
    identity = confirm_device_identity(provider_info.active_provider, provider_info.device_id)
    return replace(
        provider_info,
        device_id=identity.device_id,
        device_name=identity.name,
        device_uuid=identity.uuid,
        device_verified=identity.verified,
    )

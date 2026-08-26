# coding: utf-8

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from .devices import confirm_device_identity, resolve_device_identity
from .errors import ProviderError


MAIN_PROVIDER_NAMES = (
    "CPUExecutionProvider",
    "CUDAExecutionProvider",
    "TensorrtExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
)

ACCELERATOR_PROVIDER_NAMES = tuple(
    name for name in MAIN_PROVIDER_NAMES if name != "CPUExecutionProvider"
)

# Kept as a compatibility alias for integrations importing the old name.
GPU_PROVIDER_NAMES = ACCELERATOR_PROVIDER_NAMES

_PROVIDER_ALIASES = {
    "cpu": "CPUExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "tensorrt": "TensorrtExecutionProvider",
    "trt": "TensorrtExecutionProvider",
    "directml": "DmlExecutionProvider",
    "dml": "DmlExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
}

_AUTO_PRIORITY = (
    "CUDAExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
    "CPUExecutionProvider",
)

_ACCELERATOR_PRIORITY = (
    "CUDAExecutionProvider",
    "TensorrtExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "OpenVINOExecutionProvider",
)

ProviderRequest = str | tuple[str, Mapping[str, object]]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    options: tuple[tuple[str, str], ...] = ()

    def as_ort_provider(self) -> str | tuple[str, dict[str, str]]:
        if not self.options:
            return self.name
        return self.name, dict(self.options)


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
    provider_specs: tuple[ProviderSpec, ...] = ()

    @property
    def use_cuda(self) -> bool:
        return self.active_provider in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}

    @property
    def use_dml(self) -> bool:
        return self.active_provider == "DmlExecutionProvider"

    @property
    def use_tensorrt(self) -> bool:
        return self.active_provider == "TensorrtExecutionProvider"

    @property
    def use_coreml(self) -> bool:
        return self.active_provider == "CoreMLExecutionProvider"

    @property
    def use_openvino(self) -> bool:
        return self.active_provider == "OpenVINOExecutionProvider"

    @property
    def requested_providers(self) -> tuple[str, ...]:
        if self.provider_specs:
            return tuple(spec.name for spec in self.provider_specs)
        return (self.active_provider,) if self.active_provider else ()


def detect_providers(
    prefer: str = "auto",
    providers: Sequence[ProviderRequest] | None = None,
) -> ProviderInfo:
    prefer_norm = (prefer or "auto").strip().lower()
    if providers is None and prefer_norm not in {"auto", "cpu", "gpu", *_PROVIDER_ALIASES}:
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

    specs = _resolve_provider_specs(prefer_norm, providers, available)
    active = specs[0].name
    accelerated = active in ACCELERATOR_PROVIDER_NAMES
    device = (
        "gpu"
        if active in {"CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider"}
        else "accelerator"
        if accelerated
        else "cpu"
    )
    return _provider_info(
        available_providers=available,
        active_provider=active,
        device=device,
        gpu_requested=accelerated,
        gpu_runtime_ok=accelerated,
        provider_specs=specs,
    )


def _resolve_provider_specs(
    prefer: str,
    providers: Sequence[ProviderRequest] | None,
    available: tuple[str, ...],
) -> tuple[ProviderSpec, ...]:
    if providers is not None:
        if isinstance(providers, (str, bytes)) or not providers:
            raise ProviderError("providers must be a non-empty sequence")
        specs = tuple(_normalize_provider_request(item) for item in providers)
        _ensure_available(specs, available)
        return specs

    if prefer == "auto":
        active = next((name for name in _AUTO_PRIORITY if name in available), None)
        if active is None:
            raise ProviderError(f"no supported ONNX execution provider is available: {available}")
        return _default_provider_chain(active, available)

    if prefer == "gpu":
        active = next((name for name in _ACCELERATOR_PRIORITY if name in available), None)
        if active is None:
            raise ProviderError(f"GPU provider was requested but none is available: {available}")
        return _default_provider_chain(active, available)

    active = _PROVIDER_ALIASES[prefer]
    if active not in available:
        raise ProviderError(f"requested ONNX provider {active} is unavailable: {available}")
    return _default_provider_chain(active, available)


def _normalize_provider_request(request: ProviderRequest) -> ProviderSpec:
    if isinstance(request, str):
        raw_name = request
        options: Mapping[str, object] = {}
    elif isinstance(request, tuple) and len(request) == 2 and isinstance(request[1], Mapping):
        raw_name, options = request
    else:
        raise ProviderError(f"invalid provider specification: {request!r}")
    name = _canonical_provider_name(str(raw_name))
    if name not in MAIN_PROVIDER_NAMES:
        raise ProviderError(f"unsupported ONNX provider: {raw_name}")
    frozen_options = tuple(sorted((str(key), str(value)) for key, value in options.items()))
    return ProviderSpec(name=name, options=frozen_options)


def _canonical_provider_name(name: str) -> str:
    stripped = name.strip()
    return _PROVIDER_ALIASES.get(stripped.lower(), stripped)


def _ensure_available(specs: tuple[ProviderSpec, ...], available: tuple[str, ...]) -> None:
    unavailable = tuple(spec.name for spec in specs if spec.name not in available)
    if unavailable:
        raise ProviderError(
            f"requested ONNX providers are unavailable: {unavailable}; available={available}"
        )


def _default_provider_chain(active: str, available: tuple[str, ...]) -> tuple[ProviderSpec, ...]:
    names = [active]
    if active == "TensorrtExecutionProvider" and "CUDAExecutionProvider" in available:
        names.append("CUDAExecutionProvider")
    if active != "CPUExecutionProvider" and "CPUExecutionProvider" in available:
        names.append("CPUExecutionProvider")
    return tuple(ProviderSpec(name=name, options=_default_options(name)) for name in names)


def _default_options(name: str) -> tuple[tuple[str, str], ...]:
    if name in {"CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider"}:
        return (("device_id", "0"),)
    return ()


def _provider_info(
    *,
    available_providers: tuple[str, ...],
    active_provider: str,
    device: str,
    gpu_requested: bool,
    gpu_runtime_ok: bool,
    provider_specs: tuple[ProviderSpec, ...] = (),
) -> ProviderInfo:
    active_spec = next((spec for spec in provider_specs if spec.name == active_provider), None)
    active_options = dict(active_spec.options) if active_spec else {}
    device_id = (
        int(active_options.get("device_id", 0))
        if active_provider in {"CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider"}
        else None
    )
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
        provider_specs=provider_specs,
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


__all__ = [
    "ACCELERATOR_PROVIDER_NAMES",
    "GPU_PROVIDER_NAMES",
    "MAIN_PROVIDER_NAMES",
    "ProviderInfo",
    "ProviderRequest",
    "ProviderSpec",
    "confirm_provider_device",
    "detect_providers",
]

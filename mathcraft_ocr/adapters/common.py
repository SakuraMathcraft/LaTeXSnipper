# coding: utf-8

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path

from ..providers import ACCELERATOR_PROVIDER_NAMES, ProviderInfo


ProviderOptions = tuple[tuple[str, str], ...]
ProviderConfig = tuple[str, ProviderOptions]


def _ort():
    return importlib.import_module("onnxruntime")


def session_providers(provider_info: ProviderInfo) -> list[str | tuple[str, dict[str, object]]]:
    if provider_info.provider_specs:
        return [spec.as_ort_provider() for spec in provider_info.provider_specs]
    available = list(provider_info.available_providers)
    active = provider_info.active_provider
    if active and active in ACCELERATOR_PROVIDER_NAMES and "CPUExecutionProvider" in available:
        return [(active, {"device_id": int(provider_info.device_id or 0)}), "CPUExecutionProvider"]
    if active and active in ACCELERATOR_PROVIDER_NAMES:
        return [(active, {"device_id": int(provider_info.device_id or 0)})]
    if "CPUExecutionProvider" in available:
        return ["CPUExecutionProvider"]
    return available


def create_session(model_path: str | Path, provider_info: ProviderInfo):
    model_path = str(Path(model_path).resolve())
    provider_config = _freeze_provider_config(session_providers(provider_info))
    session = _create_session_cached(model_path, provider_config)
    enforce_session_provider(session, provider_info)
    return session


@lru_cache(maxsize=16)
def _create_session_cached(model_path: str, providers: tuple[ProviderConfig, ...]):
    ort = _ort()
    configured = [
        (name, {key: value for key, value in options}) if options else name
        for name, options in providers
    ]
    kwargs = {
        "providers": configured,
        "enable_fallback": False,
    }
    session_options = _session_options(ort, providers)
    if session_options is not None:
        kwargs["sess_options"] = session_options
    return ort.InferenceSession(model_path, **kwargs)


def _session_options(ort, providers: tuple[ProviderConfig, ...]):
    create_options = getattr(ort, "SessionOptions", None)
    if not callable(create_options):
        return None
    session_options = create_options()
    session_options.log_severity_level = 4
    names = {name for name, _options in providers}
    if "DmlExecutionProvider" not in names:
        return session_options
    session_options.enable_mem_pattern = False
    execution_mode = getattr(getattr(ort, "ExecutionMode", None), "ORT_SEQUENTIAL", None)
    if execution_mode is not None:
        session_options.execution_mode = execution_mode
    return session_options


def _freeze_provider_config(
    providers: list[str | tuple[str, dict[str, object]]],
) -> tuple[ProviderConfig, ...]:
    frozen: list[ProviderConfig] = []
    for item in providers:
        if isinstance(item, str):
            frozen.append((item, ()))
            continue
        name, options = item
        frozen.append((name, tuple(sorted((str(key), str(value)) for key, value in options.items()))))
    return tuple(frozen)


def enforce_session_provider(session, provider_info: ProviderInfo) -> None:
    validate_session_provider(
        session,
        str(provider_info.active_provider or ""),
        int(provider_info.device_id or 0),
    )


def validate_session_provider(
    session,
    active_provider: str,
    device_id: int = 0,
    *,
    runtime_name: str = "ONNX Runtime",
) -> None:
    actual = list(session.get_providers() or [])
    active = str(active_provider or "")
    if not actual or actual[0] != active:
        provider_kind = "ONNX accelerator provider" if active in ACCELERATOR_PROVIDER_NAMES else "ONNX provider"
        raise RuntimeError(
            f"requested {provider_kind} {active or '<none>'}, "
            f"but {runtime_name} session providers are {actual}"
        )
    if active in {"CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider"}:
        get_options = getattr(session, "get_provider_options", None)
        if callable(get_options):
            options_by_provider = get_options() or {}
            active_options = options_by_provider.get(active, {}) if isinstance(options_by_provider, dict) else {}
            actual_device_id = active_options.get("device_id") if isinstance(active_options, dict) else None
            if actual_device_id not in (None, "") and int(actual_device_id) != int(device_id):
                raise RuntimeError(
                    f"requested ONNX provider {active} device_id={int(device_id)}, "
                    f"but {runtime_name} session uses device_id={actual_device_id}"
                )
    disable_fallback = getattr(session, "disable_fallback", None)
    if not callable(disable_fallback):
        raise RuntimeError(f"{runtime_name} session cannot disable provider fallback")
    disable_fallback()


def clear_session_cache() -> None:
    _create_session_cached.cache_clear()

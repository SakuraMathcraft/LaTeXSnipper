# coding: utf-8

from __future__ import annotations


CUDA_RUNTIME_ERROR_MARKERS = (
    "cudaexecutionprovider",
    "onnxruntime_providers_cuda",
    "provider_info_cuda",
    "trygetproviderinfo_cuda",
    "cuda_path is set",
    "cuda wasn't able to be loaded",
    "failed to create cuda",
    "failed to load cuda",
    "cudnn",
    "cublas",
    "cufft",
)

ONNXRUNTIME_INSTALL_ERROR_MARKERS = (
    "failed to import onnxruntime",
    "failed to query onnx providers",
    "onnxruntime missing get_available_providers",
    "module 'onnxruntime' has no attribute 'get_available_providers'",
    "onnxruntime dependency is incomplete",
)


def looks_like_cuda_runtime_error(detail: object) -> bool:
    text = str(detail or "").lower()
    return any(marker in text for marker in CUDA_RUNTIME_ERROR_MARKERS)


def looks_like_onnxruntime_install_error(detail: object) -> bool:
    text = str(detail or "").lower()
    return any(marker in text for marker in ONNXRUNTIME_INSTALL_ERROR_MARKERS)


__all__ = [
    "CUDA_RUNTIME_ERROR_MARKERS",
    "ONNXRUNTIME_INSTALL_ERROR_MARKERS",
    "looks_like_cuda_runtime_error",
    "looks_like_onnxruntime_install_error",
]

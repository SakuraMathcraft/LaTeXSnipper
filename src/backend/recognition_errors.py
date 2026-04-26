# coding: utf-8

from __future__ import annotations

from backend.model import classify_mathcraft_failure


EXTERNAL_MODEL_BACKENDS = {"external_model", "ollama", "openai_compatible", "mineru"}


def is_external_model_backend(backend: str | None) -> bool:
    return str(backend or "").strip().lower() in EXTERNAL_MODEL_BACKENDS


def recognition_failure_user_message(detail: object, backend: str | None = "mathcraft") -> str:
    raw = str(detail or "").strip()
    if is_external_model_backend(backend):
        return raw or "外部模型运行异常，请检查外部服务配置和连接状态。"
    info = classify_mathcraft_failure(raw)
    return str(info.get("user_message") or raw or "").strip()


__all__ = ["is_external_model_backend", "recognition_failure_user_message"]

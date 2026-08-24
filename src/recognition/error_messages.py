# coding: utf-8

from __future__ import annotations

from backend.mathcraft.diagnostics import classify_mathcraft_failure


EXTERNAL_MODEL_BACKENDS = {"external_model", "ollama", "openai_compatible", "mineru"}

_RECOGNITION_ERROR_MESSAGES = {
    "backend_unavailable": "外部模型尚未配置或当前不可用，请检查外部模型设置。",
    "backend_unsupported": "当前识别后端不受支持，请检查识别设置。",
    "canceled": "识别已取消。",
    "empty_content": "未检测到可识别内容",
    "empty_formula": "未识别到公式内容",
    "empty_text": "未识别到文本内容",
    "internal_error": "识别失败，请重试；若问题持续，请查看运行日志。",
    "invalid_backend": "识别后端配置无效，请检查识别设置。",
    "invalid_mode": "当前识别模式不受支持，请检查识别设置。",
    "model_unavailable": "MathCraft OCR 当前不可用，请等待模型加载完成后重试。",
    "queue_full": "识别任务较多，请稍后重试。",
    "timeout": "识别超时，请稍后重试。",
    "upstream_error": "外部模型调用失败，请检查服务状态和模型配置。",
    "upstream_timeout": "外部模型响应超时，请稍后重试或调整超时设置。",
}


def is_external_model_backend(backend: str | None) -> bool:
    return str(backend or "").strip().lower() in EXTERNAL_MODEL_BACKENDS


def recognition_error_code_user_message(code: object, backend: str | None = "mathcraft") -> str:
    normalized = str(code or "internal_error").strip().lower()
    if normalized == "internal_error" and is_external_model_backend(backend):
        normalized = "upstream_error"
    return _RECOGNITION_ERROR_MESSAGES.get(normalized, _RECOGNITION_ERROR_MESSAGES["internal_error"])


def recognition_failure_user_message(detail: object, backend: str | None = "mathcraft") -> str:
    raw = str(detail or "").strip()
    if raw in {"未识别到公式内容", "未识别到文本内容", "未检测到可识别内容", "识别结果为空"}:
        return raw
    if is_external_model_backend(backend):
        return recognition_error_code_user_message("upstream_error", backend)
    info = classify_mathcraft_failure(raw)
    return str(info.get("user_message") or raw or "").strip()


__all__ = [
    "is_external_model_backend",
    "recognition_error_code_user_message",
    "recognition_failure_user_message",
]

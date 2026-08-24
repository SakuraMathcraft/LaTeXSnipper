"""Stable Automation API contracts and resource limits."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from recognition.image_contracts import (
    DEFAULT_MAX_DECODED_IMAGE_PIXELS,
    DEFAULT_MAX_ENCODED_IMAGE_BYTES,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from recognition.jobs.contracts import (
    RecognitionJobError,
    RecognitionLimits,
)


API_VERSION = "1"
API_PREFIX = "/api/v1"
SUPPORTED_IMAGE_FORMATS = SUPPORTED_IMAGE_EXTENSIONS
SUPPORTED_RECOGNITION_MODES = ("formula", "text", "mixed")


@dataclass(frozen=True, slots=True)
class AutomationLimits(RecognitionLimits):
    """HTTP transport limits layered on the recognition coordinator limits."""

    max_encoded_image_bytes: int = DEFAULT_MAX_ENCODED_IMAGE_BYTES
    max_request_body_bytes: int = 64 * 1024 * 1024
    max_decoded_image_pixels: int = DEFAULT_MAX_DECODED_IMAGE_PIXELS
    max_request_decoded_pixels: int = 80_000_000
    max_prefer_wait_seconds: int = 30
    request_concurrency: int = 16
    request_read_timeout_seconds: float = 20.0
    keep_alive_timeout_seconds: float = 10.0
    remote_submissions_per_minute: int = 20
    remote_status_queries_per_minute: int = 120


DEFAULT_LIMITS = AutomationLimits()


class AutomationApiError(RecognitionJobError):
    """An HTTP API error with an explicit response status."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code, message)
        self.status = int(status)


_RECOGNITION_ERROR_STATUSES = {
    "invalid_request": 400,
    "invalid_mode": 400,
    "invalid_backend": 400,
    "next_result_busy": 409,
    "job_expired": 410,
    "batch_too_large": 413,
    "mode_unsupported": 422,
    "empty_formula": 422,
    "empty_text": 422,
    "empty_content": 422,
    "job_not_found": 404,
    "model_unavailable": 503,
    "backend_unavailable": 503,
    "queue_full": 503,
}


def error_http_status(error: RecognitionJobError) -> int:
    if isinstance(error, AutomationApiError):
        return error.status
    return _RECOGNITION_ERROR_STATUSES.get(error.code, 500)


def request_id() -> str:
    return uuid.uuid4().hex


def error_response(error: RecognitionJobError, *, request_id_value: str) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "request_id": request_id_value,
        }
    }


def parse_json_object(raw: bytes) -> dict[str, Any]:
    if not raw:
        raise AutomationApiError(400, "invalid_request", "请求体必须是 JSON 对象。")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutomationApiError(400, "invalid_request", "请求体不是有效的 JSON。") from exc
    if not isinstance(value, dict):
        raise AutomationApiError(400, "invalid_request", "请求体必须是 JSON 对象。")
    return value


def validate_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode not in SUPPORTED_RECOGNITION_MODES:
        raise AutomationApiError(400, "invalid_mode", "识别模式必须为 formula、text 或 mixed。")
    return mode


def validate_timeout(value: object, *, default: float = 120.0) -> float:
    if value is None or value == "":
        return default
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise AutomationApiError(400, "invalid_request", "超时时间必须是正数。") from exc
    if timeout <= 0 or timeout > 3600:
        raise AutomationApiError(400, "invalid_request", "超时时间必须大于 0 且不超过 3600 秒。")
    return timeout

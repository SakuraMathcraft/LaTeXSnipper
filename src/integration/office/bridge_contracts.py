"""JSON contracts and errors used by the Office bridge."""

from __future__ import annotations

import json
from typing import Any


MAX_JSON_BODY_BYTES = 8 * 1024 * 1024


class OfficeBridgeError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def parse_json_body(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BODY_BYTES:
        raise OfficeBridgeError(413, "payload_too_large", "request body is too large")
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise OfficeBridgeError(400, "invalid_json", "request body must be valid JSON") from exc
    if not isinstance(value, dict):
        raise OfficeBridgeError(400, "invalid_json", "request body must be a JSON object")
    return value


def success_response(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "result": result}


def error_response(error: OfficeBridgeError) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
        },
    }

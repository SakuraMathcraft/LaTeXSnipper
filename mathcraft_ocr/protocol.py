"""Versioned desktop worker wire and model format contract."""

WORKER_PROTOCOL = 1
MODEL_FORMAT = 1


def validate_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise ValueError("worker request must be an object")
    if (
        type(request.get("protocol")) is not int
        or request["protocol"] != WORKER_PROTOCOL
    ):
        raise ValueError("unsupported worker protocol")
    if not isinstance(request.get("id"), str) or not request["id"]:
        raise ValueError("worker request needs a non-empty string id")
    return request


def validate_response(response: object, request_id: str) -> dict:
    if not isinstance(response, dict):
        raise ValueError("worker response must be an object")
    if (
        type(response.get("protocol")) is not int
        or response["protocol"] != WORKER_PROTOCOL
    ):
        raise ValueError("unsupported worker response protocol")
    if response.get("id") != request_id:
        raise ValueError("worker response id does not match the request")
    if type(response.get("ok")) is not bool:
        raise ValueError("worker response needs a boolean status")
    if response["ok"] and not isinstance(response.get("result"), dict):
        raise ValueError("worker response needs an object result")
    if not response["ok"] and not isinstance(response.get("error"), dict):
        raise ValueError("worker response needs an object error")
    return response

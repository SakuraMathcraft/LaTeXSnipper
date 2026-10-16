"""Format component failures returned by the worker protocol."""

from typing import Any

def _failed_warmup_component_details(result: dict[str, Any]) -> list[str]:
    statuses = result.get("component_statuses", [])
    if not isinstance(statuses, list):
        return []
    details: list[str] = []
    for status in statuses:
        if not isinstance(status, dict) or bool(status.get("ready")):
            continue
        model_id = str(status.get("model_id") or "").strip()
        detail = str(status.get("detail") or "").strip()
        if model_id and detail:
            details.append(f"{model_id}: {detail}")
        elif detail:
            details.append(detail)
        elif model_id:
            details.append(f"{model_id}: not ready")
    return details

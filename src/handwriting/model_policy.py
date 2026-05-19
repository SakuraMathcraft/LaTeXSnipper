from __future__ import annotations

HANDWRITING_INTERNAL_MODEL = "mathcraft_mixed"
EXTERNAL_MODEL = "external_model"


def resolve_handwriting_recognition_model(preferred_model: str | None) -> str:
    """Return the recognition backend used by the handwriting window."""
    model = str(preferred_model or "").strip().lower()
    if model == EXTERNAL_MODEL:
        return EXTERNAL_MODEL
    return HANDWRITING_INTERNAL_MODEL


def is_internal_handwriting_model(model_name: str | None) -> bool:
    return str(model_name or "").strip().lower() == HANDWRITING_INTERNAL_MODEL

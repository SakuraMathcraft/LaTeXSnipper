from __future__ import annotations

INTERNAL_DOCUMENT_MODEL = "mathcraft_mixed"
EXTERNAL_MODEL = "external_model"


def resolve_document_recognition_model(preferred_model: str | None) -> str:
    """Return the backend used for document-oriented recognition."""
    model = str(preferred_model or "").strip().lower()
    if model == EXTERNAL_MODEL:
        return EXTERNAL_MODEL
    return INTERNAL_DOCUMENT_MODEL


def is_internal_document_model(model_name: str | None) -> bool:
    return str(model_name or "").strip().lower() == INTERNAL_DOCUMENT_MODEL

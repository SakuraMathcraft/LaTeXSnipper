"""Recognition content types shared by result, history, and preview UI."""

from __future__ import annotations

from typing import Literal


ContentType = Literal["mathcraft", "mathcraft_mixed", "mathcraft_text"]

FORMULA_CONTENT_TYPE: ContentType = "mathcraft"
MIXED_CONTENT_TYPE: ContentType = "mathcraft_mixed"
TEXT_CONTENT_TYPE: ContentType = "mathcraft_text"


def normalize_content_type(content_type: str) -> ContentType:
    value = content_type.strip().lower()
    if value == FORMULA_CONTENT_TYPE:
        return FORMULA_CONTENT_TYPE
    if value == MIXED_CONTENT_TYPE:
        return MIXED_CONTENT_TYPE
    if value == TEXT_CONTENT_TYPE:
        return TEXT_CONTENT_TYPE
    raise ValueError(f"Unsupported content type: {content_type!r}")


def content_type_for_mathcraft(model_name: str) -> ContentType:
    return normalize_content_type(model_name)


def content_type_for_external_output(output_mode: str) -> ContentType:
    mode = output_mode.strip().lower()
    if mode == "latex":
        return FORMULA_CONTENT_TYPE
    if mode == "markdown":
        return MIXED_CONTENT_TYPE
    if mode == "text":
        return TEXT_CONTENT_TYPE
    raise ValueError(f"Unsupported external output mode: {output_mode!r}")

from __future__ import annotations


def test_handwriting_external_prompt_preserves_text_and_formula() -> None:
    from backend.external_model.prompts import build_prompt
    from backend.external_model.schemas import ExternalModelConfig

    prompt = build_prompt(
        ExternalModelConfig(
            prompt_template="ocr_handwriting_mixed_v1",
        )
    )

    assert "ordinary words" in prompt
    assert "Chinese text" in prompt
    assert "$$...$$" in prompt
    assert "code fences" in prompt

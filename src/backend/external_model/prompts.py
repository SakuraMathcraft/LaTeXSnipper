from .schemas import ExternalModelConfig


PROMPTS = {
    "ocr_formula_v1": (
        "Recognize the visible formula or math-heavy content in the image. "
        "Return directly usable LaTeX only. Preserve nearby labels or text when they are part of the expression. "
        "Do not explain, summarize, add code fences, or add prefixes."
    ),
    "ocr_markdown_v1": (
        "Recognize the visible page region and return Markdown only. "
        "Preserve reading order, headings, paragraphs, lists, tables, and line breaks. "
        "Use $...$ for inline formulas and $$...$$ for display formulas. "
        "Do not explain, summarize, add code fences, or add prefixes."
    ),
    "ocr_text_v1": (
        "Recognize the visible text in the image and return plain text only. "
        "Preserve reading order and line breaks. "
        "Do not explain, summarize, add code fences, or add prefixes."
    ),
    "ocr_handwriting_mixed_v1": (
        "Recognize the handwritten note and return editable Markdown with LaTeX math. "
        "Preserve ordinary words, Chinese text, English text, labels, annotations, and formulas in reading order. "
        "Use $...$ for inline formulas and $$...$$ for display formulas. "
        "Do not output a complete TeX document, explanations, code fences, or prefixes."
    ),
    "ocr_document_page_v1": (
        "Parse this PDF page and return Markdown only. "
        "Preserve reading order, headings, paragraphs, lists, tables, captions, and page structure. "
        "Use $...$ for inline formulas and $$...$$ for display formulas. "
        "Do not explain, summarize, rewrite, add code fences, or add prefixes."
    ),
    "ocr_document_latex_v1": (
        "Parse this PDF page and return LaTeX only. "
        "Preserve reading order, headings, paragraphs, lists, tables, captions, and page structure. "
        "Use standard LaTeX environments for formulas and structured content. "
        "Do not output a complete document, explain, summarize, rewrite, add code fences, or add prefixes."
    ),
}


def build_prompt(config: ExternalModelConfig) -> str:
    custom = str(config.custom_prompt or "").strip()
    if custom:
        return custom

    return PROMPTS[config.normalized_prompt_template()]

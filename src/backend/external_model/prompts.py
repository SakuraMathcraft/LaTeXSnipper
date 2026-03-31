from .schemas import ExternalModelConfig


PROMPTS = {
    "ocr_formula_v1": (
        "你是一个本地多模态 OCR 助手。"
        "请识别图片中的公式、数学符号和相关文字。"
        "优先输出可直接使用的 LaTeX。"
        "如果有多行内容，保持原始顺序。"
        "不要解释，不要添加额外说明。"
    ),
    "ocr_markdown_v1": (
        "你是一个本地多模态 OCR 助手。"
        "请识别图片中的数学内容与文字，并以 Markdown 输出。"
        "公式尽量使用 LaTeX 数学语法。"
        "不要解释，不要添加额外说明。"
    ),
    "ocr_text_v1": (
        "你是一个本地多模态 OCR 助手。"
        "请识别图片中的全部文字和公式内容，只返回纯文本。"
        "不要解释，不要添加额外说明。"
    ),
}


def build_prompt(config: ExternalModelConfig) -> str:
    custom = str(config.custom_prompt or "").strip()
    if custom:
        return custom
    name = str(config.prompt_template or "").strip()
    if name in PROMPTS:
        return PROMPTS[name]
    output_mode = config.normalized_output_mode()
    if output_mode == "markdown":
        return PROMPTS["ocr_markdown_v1"]
    if output_mode == "text":
        return PROMPTS["ocr_text_v1"]
    return PROMPTS["ocr_formula_v1"]

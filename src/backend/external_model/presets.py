PRESETS = {
    "glm_ocr": {
        "label": "GLM-OCR",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "glm-ocr",
        "output_mode": "latex",
        "prompt_template": "ocr_formula_v1",
        "hint": "适合文档 OCR、表格和公式混合识别；默认按 Ollama 本地服务填写。",
    },
    "paddleocr_vl": {
        "label": "PaddleOCR-VL",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:8000",
        "model_name": "paddleocr-vl",
        "output_mode": "markdown",
        "prompt_template": "ocr_markdown_v1",
        "hint": "适合整页 OCR 与结构化输出；请替换成你本地实际加载的模型名。",
    },
    "qwen_vl": {
        "label": "Qwen2.5/Qwen3-VL",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "qwen2.5vl:7b",
        "output_mode": "latex",
        "prompt_template": "ocr_formula_v1",
        "hint": "适合作为通用多模态兜底模型；Ollama 下请确认模型已 pull。",
    },
    "ollama_vision": {
        "label": "Ollama Vision",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "llava:7b",
        "output_mode": "text",
        "prompt_template": "ocr_text_v1",
        "hint": "适合快速验证本地视觉模型链路是否可用。",
    },
    "mineru_native": {
        "label": "MinerU Native",
        "provider": "mineru",
        "base_url": "http://127.0.0.1:8000",
        "model_name": "",
        "output_mode": "markdown",
        "prompt_template": "ocr_document_page_v1",
        "mineru_endpoint": "/file_parse",
        "mineru_test_endpoint": "/health",
        "mineru_mode": "document",
        "hint": "MinerU 原生接口：可不填模型名，需确认解析接口路径和健康检查路径。",
    },
}

PRESET_ITEMS = [(key, data["label"]) for key, data in PRESETS.items()]


def get_preset(preset_id: str) -> dict | None:
    key = str(preset_id or "").strip()
    if not key:
        return None
    return PRESETS.get(key)

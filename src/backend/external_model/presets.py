PRESETS = {
    "glm_ocr": {
        "label": "GLM-OCR",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "glm-ocr",
        "prompt_template": "ocr_formula_v1",
    },
    "paddleocr_vl": {
        "label": "PaddleOCR-VL (FastDeploy)",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:8185",
        "model_name": "PaddlePaddle/PaddleOCR-VL",
        "prompt_template": "ocr_markdown_v1",
    },
    "qwen_vl": {
        "label": "Qwen2.5/Qwen3-VL",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "qwen2.5vl:7b",
        "prompt_template": "ocr_formula_v1",
    },
    "mineru_local": {
        "label": "MinerU Local",
        "provider": "mineru",
        "base_url": "http://127.0.0.1:8000",
        "model_name": "",
        "prompt_template": "ocr_document_page_v1",
        "mineru_endpoint": "/file_parse",
        "mineru_test_endpoint": "/health",
    },
}

PRESET_ITEMS = [(key, data["label"]) for key, data in PRESETS.items()]


def get_preset(preset_id: str) -> dict | None:
    key = str(preset_id or "").strip()
    if not key:
        return None
    return PRESETS.get(key)

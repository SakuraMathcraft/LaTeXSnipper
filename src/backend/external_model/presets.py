PRESETS = {
    "glm_ocr": {
        "label": "GLM-OCR",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "glm-ocr",
        "prompt_template": "ocr_formula_v1",
        "hint": "适合文档 OCR、表格和公式混合识别；默认按 Ollama 本地服务填写。",
    },
    "paddleocr_vl": {
        "label": "PaddleOCR-VL (FastDeploy)",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:8185",
        "model_name": "PaddlePaddle/PaddleOCR-VL",
        "prompt_template": "ocr_markdown_v1",
        "hint": "适用于 FastDeploy OpenAI API Server；端口和模型名需与实际启动参数一致。",
    },
    "qwen_vl": {
        "label": "Qwen2.5/Qwen3-VL",
        "provider": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model_name": "qwen2.5vl:7b",
        "prompt_template": "ocr_formula_v1",
        "hint": "适合作为通用多模态兜底模型；Ollama 下请确认模型已 pull。",
    },
    "mineru_local": {
        "label": "MinerU Local",
        "provider": "mineru",
        "base_url": "http://127.0.0.1:8000",
        "model_name": "",
        "prompt_template": "ocr_document_page_v1",
        "mineru_endpoint": "/file_parse",
        "mineru_test_endpoint": "/health",
        "hint": "MinerU 本地服务：使用 /health 和 /file_parse，可不填模型名。",
    },
}

PRESET_ITEMS = [(key, data["label"]) for key, data in PRESETS.items()]


def get_preset(preset_id: str) -> dict | None:
    key = str(preset_id or "").strip()
    if not key:
        return None
    return PRESETS.get(key)

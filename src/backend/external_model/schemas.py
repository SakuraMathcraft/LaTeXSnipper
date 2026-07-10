import re
from dataclasses import dataclass

from runtime.secret_store import decrypt_secret, encrypt_secret


DEFAULT_CONFIG = {
    "external_model_provider": "ollama",
    "external_model_base_url": "http://127.0.0.1:11434",
    "external_model_model_name": "",
    "external_model_api_key_enc": "",
    "external_model_timeout_sec": 60,
    "external_model_prompt_template": "ocr_formula_v1",
    "external_model_custom_prompt": "",
    "external_model_preset": "",
    "external_model_mineru_endpoint": "/file_parse",
    "external_model_mineru_test_endpoint": "/health",
}

PROMPT_OUTPUT_MODES = {
    "ocr_formula_v1": "latex",
    "ocr_markdown_v1": "markdown",
    "ocr_text_v1": "text",
    "ocr_handwriting_mixed_v1": "markdown",
    "ocr_document_page_v1": "markdown",
    "ocr_document_latex_v1": "latex",
}


def get_config_value(mapping, key: str):
    try:
        return mapping.get(key, DEFAULT_CONFIG.get(key))
    except Exception:
        return DEFAULT_CONFIG.get(key)


@dataclass(slots=True)
class ExternalModelConfig:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model_name: str = ""
    api_key: str = ""
    timeout_sec: int = 60
    prompt_template: str = "ocr_formula_v1"
    custom_prompt: str = ""
    preset: str = ""
    mineru_endpoint: str = "/file_parse"
    mineru_test_endpoint: str = "/health"

    def normalized_provider(self) -> str:
        value = str(self.provider or "ollama").strip().lower()
        return value if value in ("openai_compatible", "ollama", "mineru") else "ollama"

    def normalized_prompt_template(self) -> str:
        value = str(self.prompt_template).strip()
        if value not in PROMPT_OUTPUT_MODES:
            raise ValueError(f"Unsupported prompt template: {self.prompt_template!r}")
        return value

    def resolved_output_mode(self) -> str:
        return PROMPT_OUTPUT_MODES[self.normalized_prompt_template()]

    def normalized_timeout(self) -> int:
        try:
            value = int(self.timeout_sec)
        except Exception:
            value = 60
        return min(max(value, 5), 300)

    def normalized_base_url(self) -> str:
        return str(self.base_url or "").strip().rstrip("/")

    def normalized_model_name(self) -> str:
        return str(self.model_name or "").strip()

    def normalized_api_key(self) -> str:
        return str(self.api_key or "").strip()

    def normalized_mineru_endpoint(self) -> str:
        value = str(self.mineru_endpoint or "/file_parse").strip()
        if not value:
            value = "/file_parse"
        if not value.startswith("/"):
            value = f"/{value}"
        return value

    def normalized_mineru_test_endpoint(self) -> str:
        value = str(self.mineru_test_endpoint or "/health").strip()
        if not value:
            value = "/health"
        if not value.startswith("/"):
            value = f"/{value}"
        return value

    def to_mapping(self) -> dict:
        return {
            "external_model_provider": self.normalized_provider(),
            "external_model_base_url": self.normalized_base_url(),
            "external_model_model_name": self.normalized_model_name(),
            "external_model_api_key_enc": encrypt_secret(self.normalized_api_key()),
            "external_model_timeout_sec": self.normalized_timeout(),
            "external_model_prompt_template": self.normalized_prompt_template(),
            "external_model_custom_prompt": str(self.custom_prompt or "").strip(),
            "external_model_preset": str(self.preset or "").strip(),
            "external_model_mineru_endpoint": self.normalized_mineru_endpoint(),
            "external_model_mineru_test_endpoint": self.normalized_mineru_test_endpoint(),
        }


@dataclass(slots=True)
class ExternalModelResult:
    text: str = ""
    latex: str = ""
    markdown: str = ""
    backend: str = "external_model"
    provider: str = ""
    model_name: str = ""
    raw: dict | None = None
    structured_payload: dict | None = None

    def _strip_outer_code_fence(self, value: str) -> str:
        text = str(value or "").strip()
        if not text.startswith("```"):
            return text
        match = re.fullmatch(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\n?(.*?)\n?```", text, flags=re.DOTALL)
        if not match:
            return text
        inner = (match.group(2) or "").strip()
        return inner or text

    def _normalize_common_text(self, value: str) -> str:
        text = (value or "").replace("\r\n", "\n")
        if not text:
            return ""

        # Strip common multimodal control tokens emitted by some VLM/OCR services.
        text = re.sub(r"<\|(?:begin|end)_of_image\|>", "", text)
        text = re.sub(r"<\|(?:vision_start|vision_end|image_pad|img_pad)\|>", "", text)
        text = re.sub(r"</?image>", "", text, flags=re.IGNORECASE)
        text = self._strip_outer_code_fence(text)

        lines: list[str] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            lines.append(raw_line.strip())
        return "\n".join(lines).strip()

    def _normalize_latex_text(self, value: str) -> str:
        text = self._normalize_common_text(value)
        if not text:
            return ""

        # If the whole output is wrapped as a single math block, unwrap once so
        # latex mode yields canonical LaTeX content instead of Markdown wrappers.
        pairs = (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"))
        for left, right in pairs:
            if text.startswith(left) and text.endswith(right):
                inner = text[len(left): len(text) - len(right)].strip()
                if inner:
                    return inner
        return text

    def best_text(self, output_mode: str) -> str:
        mode = output_mode.strip().lower()
        if mode == "latex":
            return self._normalize_latex_text(self.latex or self.markdown or self.text or "")
        if mode == "markdown":
            return self._normalize_common_text(self.markdown or self.text or self.latex or "")
        if mode == "text":
            return self._normalize_common_text(self.text or self.markdown or self.latex or "")
        raise ValueError(f"Unsupported external output mode: {output_mode!r}")


def load_config_from_mapping(mapping) -> ExternalModelConfig:
    return ExternalModelConfig(
        provider=str(get_config_value(mapping, "external_model_provider") or "ollama"),
        base_url=str(get_config_value(mapping, "external_model_base_url") or "http://127.0.0.1:11434"),
        model_name=str(get_config_value(mapping, "external_model_model_name") or ""),
        api_key=decrypt_secret(str(get_config_value(mapping, "external_model_api_key_enc") or "")),
        timeout_sec=int(get_config_value(mapping, "external_model_timeout_sec") or 60),
        prompt_template=str(get_config_value(mapping, "external_model_prompt_template") or "ocr_formula_v1"),
        custom_prompt=str(get_config_value(mapping, "external_model_custom_prompt") or ""),
        preset=str(get_config_value(mapping, "external_model_preset") or ""),
        mineru_endpoint=str(get_config_value(mapping, "external_model_mineru_endpoint") or "/file_parse"),
        mineru_test_endpoint=str(get_config_value(mapping, "external_model_mineru_test_endpoint") or "/health"),
    )

import re
from dataclasses import dataclass


DEFAULT_CONFIG = {
    "external_model_provider": "openai_compatible",
    "external_model_base_url": "http://127.0.0.1:11434",
    "external_model_model_name": "",
    "external_model_api_key": "",
    "external_model_timeout_sec": 60,
    "external_model_output_mode": "latex",
    "external_model_prompt_template": "ocr_formula_v1",
    "external_model_custom_prompt": "",
    "external_model_preset": "",
    "external_model_mineru_endpoint": "/file_parse",
    "external_model_mineru_test_endpoint": "/health",
    "external_model_mineru_mode": "auto",
}


def get_config_value(mapping, key: str):
    try:
        return mapping.get(key, DEFAULT_CONFIG.get(key))
    except Exception:
        return DEFAULT_CONFIG.get(key)


@dataclass(slots=True)
class ExternalModelConfig:
    provider: str = "openai_compatible"
    base_url: str = "http://127.0.0.1:11434"
    model_name: str = ""
    api_key: str = ""
    timeout_sec: int = 60
    output_mode: str = "latex"
    prompt_template: str = "ocr_formula_v1"
    custom_prompt: str = ""
    preset: str = ""
    mineru_endpoint: str = "/file_parse"
    mineru_test_endpoint: str = "/health"
    mineru_mode: str = "auto"

    def normalized_provider(self) -> str:
        value = str(self.provider or "openai_compatible").strip().lower()
        return value if value in ("openai_compatible", "ollama", "mineru") else "openai_compatible"

    def normalized_output_mode(self) -> str:
        value = str(self.output_mode or "latex").strip().lower()
        return value if value in ("latex", "markdown", "text") else "latex"

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

    def normalized_mineru_mode(self) -> str:
        value = str(self.mineru_mode or "auto").strip().lower()
        return value if value in ("auto", "document", "page") else "auto"

    def to_mapping(self) -> dict:
        return {
            "external_model_provider": self.normalized_provider(),
            "external_model_base_url": self.normalized_base_url(),
            "external_model_model_name": self.normalized_model_name(),
            "external_model_api_key": self.normalized_api_key(),
            "external_model_timeout_sec": self.normalized_timeout(),
            "external_model_output_mode": self.normalized_output_mode(),
            "external_model_prompt_template": str(self.prompt_template or "ocr_formula_v1").strip() or "ocr_formula_v1",
            "external_model_custom_prompt": str(self.custom_prompt or "").strip(),
            "external_model_preset": str(self.preset or "").strip(),
            "external_model_mineru_endpoint": self.normalized_mineru_endpoint(),
            "external_model_mineru_test_endpoint": self.normalized_mineru_test_endpoint(),
            "external_model_mineru_mode": self.normalized_mineru_mode(),
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

    def best_text(self, output_mode: str = "latex") -> str:
        mode = str(output_mode or "latex").strip().lower()
        if mode == "markdown":
            return self._normalize_common_text(self.markdown or self.text or self.latex or "")
        if mode == "text":
            return self._normalize_common_text(self.text or self.markdown or self.latex or "")
        return self._normalize_latex_text(self.latex or self.markdown or self.text or "")


def load_config_from_mapping(mapping) -> ExternalModelConfig:
    return ExternalModelConfig(
        provider=str(get_config_value(mapping, "external_model_provider") or "openai_compatible"),
        base_url=str(get_config_value(mapping, "external_model_base_url") or "http://127.0.0.1:11434"),
        model_name=str(get_config_value(mapping, "external_model_model_name") or ""),
        api_key=str(get_config_value(mapping, "external_model_api_key") or ""),
        timeout_sec=int(get_config_value(mapping, "external_model_timeout_sec") or 60),
        output_mode=str(get_config_value(mapping, "external_model_output_mode") or "latex"),
        prompt_template=str(get_config_value(mapping, "external_model_prompt_template") or "ocr_formula_v1"),
        custom_prompt=str(get_config_value(mapping, "external_model_custom_prompt") or ""),
        preset=str(get_config_value(mapping, "external_model_preset") or ""),
        mineru_endpoint=str(get_config_value(mapping, "external_model_mineru_endpoint") or "/file_parse"),
        mineru_test_endpoint=str(get_config_value(mapping, "external_model_mineru_test_endpoint") or "/health"),
        mineru_mode=str(get_config_value(mapping, "external_model_mineru_mode") or "auto"),
    )

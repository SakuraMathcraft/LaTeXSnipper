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

    def normalized_provider(self) -> str:
        value = str(self.provider or "openai_compatible").strip().lower()
        return value if value in ("openai_compatible", "ollama") else "openai_compatible"

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

    def best_text(self, output_mode: str = "latex") -> str:
        mode = str(output_mode or "latex").strip().lower()
        if mode == "markdown":
            return (self.markdown or self.text or self.latex or "").strip()
        if mode == "text":
            return (self.text or self.markdown or self.latex or "").strip()
        return (self.latex or self.markdown or self.text or "").strip()


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
    )

"""Backend-specific recognition execution without UI side effects."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from backend.external_model.client import ExternalModelClient
from backend.external_model.schemas import ExternalModelConfig
from integration.automation.contracts import AutomationApiError


_MODE_PROMPTS = {
    "formula": "ocr_formula_v1",
    "text": "ocr_text_v1",
    "mixed": "ocr_markdown_v1",
}


class ExternalRecognitionExecutor:
    """Run configured external OCR calls serially on the coordinator worker."""

    def __init__(
        self,
        config_provider: Callable[[], ExternalModelConfig | None] | None,
        predictor: Callable[[Any, ExternalModelConfig], str] | None = None,
    ) -> None:
        self._config_provider = config_provider
        self._predictor = predictor

    def snapshot(self, mode: str, config: ExternalModelConfig | None = None) -> ExternalModelConfig:
        source = config if config is not None else self._config_provider() if self._config_provider else None
        if source is None:
            raise AutomationApiError(503, "backend_unavailable", "外部模型尚未配置。")
        snapshot = ExternalModelConfig(**asdict(source))
        if config is None:
            snapshot.prompt_template = _MODE_PROMPTS[mode]
            snapshot.custom_prompt = ""
        else:
            snapshot.normalized_prompt_template()
        provider = snapshot.normalized_provider()
        if not snapshot.normalized_base_url():
            raise AutomationApiError(503, "backend_unavailable", "外部模型尚未配置。")
        if provider != "mineru" and not snapshot.normalized_model_name():
            raise AutomationApiError(503, "backend_unavailable", "外部模型尚未配置。")
        return snapshot

    def available(self) -> bool:
        try:
            self.snapshot("formula")
        except (AutomationApiError, ValueError):
            return False
        return True

    @staticmethod
    def supports_mode(mode: str) -> bool:
        return mode in _MODE_PROMPTS

    def predict(self, image: Any, config: ExternalModelConfig) -> str:
        if self._predictor is not None:
            return str(self._predictor(image, config) or "")
        result = ExternalModelClient(config).predict(image)
        return result.best_text(config.resolved_output_mode())

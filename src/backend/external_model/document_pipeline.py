from __future__ import annotations

from dataclasses import asdict, dataclass

from .client import ExternalModelClient
from .schemas import ExternalModelConfig


@dataclass(slots=True)
class DocumentPageResult:
    page_index: int
    content: str
    content_type: str


class ExternalDocumentPipeline:
    def __init__(self, config: ExternalModelConfig, output_format: str, document_mode: str = "document"):
        self.config = config
        self.output_format = "markdown" if str(output_format or "").lower().startswith("markdown") else "latex"
        mode = str(document_mode or "document").strip().lower()
        self.document_mode = mode if mode in ("document", "page") else "document"
        self.last_pages: list[DocumentPageResult] = []

    def _build_runtime_config(self, prompt_template: str | None = None) -> ExternalModelConfig:
        cfg = ExternalModelConfig(**asdict(self.config))
        cfg.output_mode = self.output_format
        prompt = str(prompt_template or "").strip()
        if not prompt:
            prompt = "ocr_document_page_v1"
        cfg.prompt_template = prompt
        return cfg

    def _infer_content_type(self, prompt_template: str) -> str:
        key = str(prompt_template or "").strip().lower()
        if "table" in key:
            return "table"
        if "formula" in key or "math" in key:
            return "formula"
        if "text" in key:
            return "text"
        if self.document_mode == "document":
            return "page"
        return "mixed"

    def process_page(self, image, page_index: int, prompt_template: str | None = None) -> DocumentPageResult | None:
        runtime_cfg = self._build_runtime_config(prompt_template)
        client = ExternalModelClient(runtime_cfg)
        result = client.predict(image)
        content = result.best_text(runtime_cfg.normalized_output_mode()).strip()
        if not content:
            return None
        return DocumentPageResult(
            page_index=int(page_index),
            content=content,
            content_type=self._infer_content_type(runtime_cfg.prompt_template),
        )

    def compose_document(self, pages: list[DocumentPageResult]) -> str:
        normalized = [p for p in pages if p and str(p.content or "").strip()]
        self.last_pages = normalized
        if not normalized:
            return ""

        if self.output_format == "markdown":
            separator = "\n\n---\n\n"
        else:
            separator = "\n\n% --- Page ---\n\n"

        return separator.join([p.content.strip() for p in normalized]).strip()

    def build_structured_result(self) -> dict:
        return {
            "backend": "external_model",
            "mode": self.document_mode,
            "output_format": self.output_format,
            "pages": [
                {
                    "page": item.page_index,
                    "content_type": item.content_type,
                    "text": item.content,
                }
                for item in self.last_pages
            ],
        }

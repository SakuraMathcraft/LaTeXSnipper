from __future__ import annotations

from dataclasses import asdict, dataclass

from .asset_store import PdfAssetStore
from .block_renderers import render_markdown_document
from .client import ExternalModelClient
from .schemas import ExternalModelConfig
from .structured_document import DocumentBlock, StructuredDocument, StructuredPage


@dataclass(slots=True)
class DocumentPageResult:
    page_index: int
    content: str
    content_type: str


class ExternalDocumentPipeline:
    def __init__(
        self,
        config: ExternalModelConfig,
        output_format: str,
        document_mode: str = "document",
        asset_store: PdfAssetStore | None = None,
    ):
        self.config = config
        self.output_format = "markdown" if str(output_format or "").lower().startswith("markdown") else "latex"
        mode = str(document_mode or "document").strip().lower()
        self.document_mode = mode if mode in ("document", "page", "parse") else "document"
        self.last_pages: list[DocumentPageResult] = []
        self.last_structured_document: StructuredDocument | None = None
        self._structured_pages: list[StructuredPage] = []
        self._inline_images: dict[str, str] = {}
        self.asset_store = asset_store

    def _build_runtime_config(self, prompt_template: str | None = None) -> ExternalModelConfig:
        cfg = ExternalModelConfig(**asdict(self.config))
        cfg.output_mode = self.output_format
        prompt = str(prompt_template or "").strip()
        if not prompt:
            prompt = "ocr_document_parse_v1" if self.document_mode == "parse" else "ocr_document_page_v1"
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
        return self.process_result(result, int(page_index), runtime_cfg.prompt_template)

    def process_result(self, result, page_index: int, prompt_template: str | None = None) -> DocumentPageResult | None:
        runtime_cfg = self._build_runtime_config(prompt_template)
        if self.document_mode == "parse":
            self._collect_inline_images(result)
            return self._process_page_parse(result, int(page_index))
        content = result.best_text(runtime_cfg.normalized_output_mode()).strip()
        if not content:
            return None
        return DocumentPageResult(
            page_index=int(page_index),
            content=content,
            content_type=self._infer_content_type(runtime_cfg.prompt_template),
        )

    def _process_page_parse(self, result, page_index: int) -> DocumentPageResult | None:
        page = self._build_structured_page(result, page_index)
        if not page.blocks:
            return None
        self._structured_pages.append(page)
        rendered = render_markdown_document(
            StructuredDocument(
                backend="external_model",
                output_mode=self.output_format,
                pages=[page],
                assets=self.asset_store.assets if self.asset_store else [],
            )
        ).strip()
        if not rendered:
            return None
        return DocumentPageResult(
            page_index=int(page_index),
            content=rendered,
            content_type="page",
        )

    def _collect_inline_images(self, result) -> None:
        payload = getattr(result, "structured_payload", None) or getattr(result, "raw", None) or {}
        if not isinstance(payload, (dict, list)):
            return

        def _walk(node, depth: int = 0):
            if depth > 10:
                return
            if isinstance(node, dict):
                images = node.get("images")
                if isinstance(images, dict):
                    for name, data_uri in images.items():
                        key = str(name or "").strip()
                        val = str(data_uri or "").strip()
                        if not key or not val:
                            continue
                        self._inline_images[key] = val
                for v in node.values():
                    _walk(v, depth + 1)
                return
            if isinstance(node, list):
                for v in node:
                    _walk(v, depth + 1)

        _walk(payload)

    def _build_structured_page(self, result, page_index: int) -> StructuredPage:
        payload = getattr(result, "structured_payload", None) or getattr(result, "raw", None) or {}
        blocks = self._extract_blocks(payload, int(page_index))
        if not blocks:
            text = result.best_text(self.output_format).strip()
            if text:
                blocks.append(
                    DocumentBlock(
                        kind="paragraph",
                        page_index=int(page_index),
                        order=1,
                        text=text,
                    )
                )
        return StructuredPage(page_index=int(page_index), blocks=blocks)

    def _extract_blocks(self, payload: dict, page_index: int) -> list[DocumentBlock]:
        if not isinstance(payload, dict):
            return []
        page_payload = self._resolve_page_payload(payload, int(page_index))
        if not isinstance(page_payload, dict):
            return []
        raw_blocks = (
            page_payload.get("blocks")
            or page_payload.get("items")
            or page_payload.get("elements")
            or []
        )
        if not isinstance(raw_blocks, list):
            return []
        blocks: list[DocumentBlock] = []
        for order, raw_block in enumerate(raw_blocks, start=1):
            block = self._normalize_block(raw_block, int(page_index), order)
            if block is not None:
                blocks.append(block)
        return blocks

    def _resolve_page_payload(self, payload: dict, page_index: int) -> dict:
        pages = payload.get("pages")
        if isinstance(pages, list):
            for item in pages:
                if not isinstance(item, dict):
                    continue
                candidate = int(item.get("page") or item.get("page_index") or 0)
                if candidate == int(page_index):
                    return item
            if pages and isinstance(pages[0], dict):
                return pages[0]
        return payload

    def _normalize_block(self, raw_block: dict, page_index: int, order: int) -> DocumentBlock | None:
        if not isinstance(raw_block, dict):
            return None
        kind = str(
            raw_block.get("type")
            or raw_block.get("kind")
            or raw_block.get("block_type")
            or raw_block.get("category")
            or "paragraph"
        ).strip().lower()
        text = str(raw_block.get("text") or raw_block.get("content") or raw_block.get("markdown") or "").strip()
        latex = str(raw_block.get("latex") or "").strip()
        caption = str(raw_block.get("caption") or raw_block.get("title") or "").strip()
        bbox = raw_block.get("bbox")
        bbox_tuple = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None

        if kind in ("paragraph", "text", "heading", "caption", "list"):
            if not text and caption and kind == "caption":
                text = caption
            if not text:
                return None
            return DocumentBlock(kind="paragraph" if kind == "text" else kind, page_index=page_index, order=order, text=text, caption=caption, bbox=bbox_tuple)

        if kind in ("formula", "equation", "math"):
            if not latex and not text:
                return None
            return DocumentBlock(kind="formula", page_index=page_index, order=order, text=text, latex=latex or text, caption=caption, bbox=bbox_tuple)

        if kind in ("table",):
            rows = self._extract_table_rows(raw_block)
            if rows:
                return DocumentBlock(kind="table", page_index=page_index, order=order, rows=rows, caption=caption, bbox=bbox_tuple)
            asset = self._save_block_image(raw_block, page_index, order, caption, "table")
            if asset is not None:
                return DocumentBlock(kind="table", page_index=page_index, order=order, asset_id=asset.asset_id, caption=caption, bbox=bbox_tuple)
            if text:
                return DocumentBlock(kind="paragraph", page_index=page_index, order=order, text=text, caption=caption, bbox=bbox_tuple)
            return None

        if kind in ("figure", "image", "illustration", "photo"):
            asset = self._save_block_image(raw_block, page_index, order, caption, "figure")
            if asset is not None:
                return DocumentBlock(kind="figure", page_index=page_index, order=order, asset_id=asset.asset_id, caption=caption, text=text, bbox=bbox_tuple)
            if text:
                return DocumentBlock(kind="paragraph", page_index=page_index, order=order, text=text, caption=caption, bbox=bbox_tuple)
            return None

        if text:
            return DocumentBlock(kind="paragraph", page_index=page_index, order=order, text=text, caption=caption, bbox=bbox_tuple, meta=dict(raw_block))
        return None

    def _extract_table_rows(self, raw_block: dict) -> list[list[str]] | None:
        rows = raw_block.get("rows") or raw_block.get("table") or raw_block.get("cells")
        if not isinstance(rows, list):
            return None
        normalized: list[list[str]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            cells: list[str] = []
            for cell in row:
                if isinstance(cell, dict):
                    cells.append(str(cell.get("text") or cell.get("content") or "").strip())
                else:
                    cells.append(str(cell or "").strip())
            if any(cells):
                normalized.append(cells)
        return normalized or None

    def _save_block_image(self, raw_block: dict, page_index: int, order: int, caption: str, kind: str):
        if self.asset_store is None:
            return None
        candidates = [
            raw_block.get("image_base64"),
            raw_block.get("image_b64"),
            raw_block.get("base64"),
            raw_block.get("content_base64"),
        ]
        image_payload = next((item for item in candidates if isinstance(item, str) and item.strip()), "")
        if not image_payload:
            image = raw_block.get("image")
            if isinstance(image, dict):
                image_payload = str(
                    image.get("base64")
                    or image.get("image_base64")
                    or image.get("image_b64")
                    or ""
                ).strip()
        if not image_payload:
            return None
        return self.asset_store.save_image_base64(
            image_payload,
            page_index=page_index,
            order=order,
            caption=caption,
            kind=kind,
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
        assets = self.asset_store.assets if self.asset_store else []
        if self.document_mode == "parse":
            self.last_structured_document = StructuredDocument(
                backend="external_model",
                output_mode=self.output_format,
                pages=list(self._structured_pages),
                assets=assets,
            )
            return {
                "backend": "external_model",
                "mode": self.document_mode,
                "output_format": self.output_format,
                "assets_root": str(self.asset_store.root_dir) if self.asset_store else "",
                "assets": [asdict(item) for item in assets],
                "inline_images": dict(self._inline_images),
                "document": self.last_structured_document.to_mapping(),
            }
        return {
            "backend": "external_model",
            "mode": self.document_mode,
            "output_format": self.output_format,
            "assets_root": str(self.asset_store.root_dir) if self.asset_store else "",
            "assets": [asdict(item) for item in assets],
            "inline_images": dict(self._inline_images),
            "pages": [
                {
                    "page": item.page_index,
                    "content_type": item.content_type,
                    "text": item.content,
                }
                for item in self.last_pages
            ],
        }

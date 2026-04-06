from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class DocumentAsset:
    asset_id: str
    kind: str
    rel_path: str
    abs_path: str
    page_index: int
    caption: str = ""


@dataclass(slots=True)
class DocumentBlock:
    kind: str
    page_index: int
    order: int
    text: str = ""
    latex: str = ""
    rows: list[list[str]] | None = None
    asset_id: str = ""
    caption: str = ""
    bbox: tuple[int, int, int, int] | None = None
    meta: dict = field(default_factory=dict)


@dataclass(slots=True)
class StructuredPage:
    page_index: int
    blocks: list[DocumentBlock]


@dataclass(slots=True)
class StructuredDocument:
    backend: str
    output_mode: str
    pages: list[StructuredPage]
    assets: list[DocumentAsset]

    def to_mapping(self) -> dict:
        return {
            "backend": self.backend,
            "output_mode": self.output_mode,
            "pages": [
                {
                    "page_index": page.page_index,
                    "blocks": [asdict(block) for block in page.blocks],
                }
                for page in self.pages
            ],
            "assets": [asdict(asset) for asset in self.assets],
        }

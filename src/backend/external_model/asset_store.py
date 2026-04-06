from __future__ import annotations

import base64
import shutil
import tempfile
from pathlib import Path

from .structured_document import DocumentAsset


class PdfAssetStore:
    def __init__(
        self,
        task_id: str | None = None,
        root_dir: str | None = None,
        overwrite_existing: bool = False,
    ):
        base = Path(root_dir or (Path(tempfile.gettempdir()) / "latexsnipper" / "pdf_assets"))
        self.task_id = str(task_id or "latest")
        self.root_dir = base / self.task_id
        if overwrite_existing and self.root_dir.exists():
            shutil.rmtree(self.root_dir, ignore_errors=True)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._assets: list[DocumentAsset] = []

    @property
    def assets(self) -> list[DocumentAsset]:
        return list(self._assets)

    def save_image_base64(
        self,
        image_base64: str,
        *,
        page_index: int,
        order: int,
        caption: str = "",
        kind: str = "image",
        ext: str = ".png",
    ) -> DocumentAsset | None:
        payload = str(image_base64 or "").strip()
        if not payload:
            return None
        if payload.startswith("data:") and "," in payload:
            payload = payload.split(",", 1)[1]
        try:
            raw = base64.b64decode(payload, validate=False)
        except Exception:
            return None
        if not raw:
            return None
        assets_dir = self.root_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"page_{int(page_index):03d}_{kind}_{int(order):03d}{ext}"
        abs_path = assets_dir / file_name
        abs_path.write_bytes(raw)
        rel_path = Path("assets") / file_name
        asset = DocumentAsset(
            asset_id=f"{kind}_{page_index}_{order}",
            kind=kind,
            rel_path=str(rel_path).replace("\\", "/"),
            abs_path=str(abs_path),
            page_index=int(page_index),
            caption=str(caption or "").strip(),
        )
        self._assets.append(asset)
        return asset

    def export_to(self, document_path: str) -> list[str]:
        path = Path(document_path)
        if not self._assets:
            return []
        base_dir = path.parent
        exported: list[str] = []
        for asset in self._assets:
            src = Path(asset.abs_path)
            if not src.exists():
                continue
            dst = base_dir / Path(asset.rel_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            exported.append(str(dst))
        return exported

    def cleanup(self) -> None:
        try:
            if self.root_dir.exists():
                shutil.rmtree(self.root_dir, ignore_errors=True)
        except Exception:
            pass

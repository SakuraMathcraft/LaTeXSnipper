from __future__ import annotations

from ..structured_document import StructuredDocument


def _render_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    normalized = [[str(cell or "").strip() for cell in row] for row in rows]
    width = max((len(row) for row in normalized), default=0)
    if width <= 0:
        return ""
    padded = [row + [""] * (width - len(row)) for row in normalized]
    header = padded[0]
    sep = ["---"] * width
    body = padded[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines).strip()


def render_markdown_document(doc: StructuredDocument) -> str:
    chunks: list[str] = []
    for page in doc.pages:
        if chunks:
            chunks.append("---")
        for block in page.blocks:
            kind = str(block.kind or "").strip().lower()
            if kind in ("paragraph", "text", "heading", "caption"):
                text = str(block.text or "").strip()
                if text:
                    chunks.append(text)
                continue
            if kind == "formula":
                latex = str(block.latex or block.text or "").strip()
                if latex:
                    if latex.startswith("$$") and latex.endswith("$$"):
                        chunks.append(latex)
                    else:
                        chunks.append(f"$$\n{latex}\n$$")
                continue
            if kind == "table":
                rows = block.rows or []
                table_md = _render_markdown_table(rows)
                if table_md:
                    chunks.append(table_md)
                elif block.asset_id:
                    asset = next((item for item in doc.assets if item.asset_id == block.asset_id), None)
                    if asset:
                        alt = block.caption or asset.caption or "表格"
                        chunks.append(f"![{alt}]({asset.rel_path})")
                continue
            if kind in ("figure", "image", "table_snapshot"):
                asset = next((item for item in doc.assets if item.asset_id == block.asset_id), None)
                if asset:
                    alt = block.caption or asset.caption or "图片"
                    chunks.append(f"![{alt}]({asset.rel_path})")
                elif block.text:
                    chunks.append(block.text.strip())
                continue
            text = str(block.text or block.latex or "").strip()
            if text:
                chunks.append(text)
    return "\n\n".join([item for item in chunks if str(item or "").strip()]).strip()

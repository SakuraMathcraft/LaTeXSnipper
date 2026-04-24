# coding: utf-8

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


_ROLE_COLORS = {
    "paragraph": "#1f77b4",
    "formula": "#d62728",
    "formula_anchor": "#9467bd",
    "formula_label": "#8c564b",
    "heading": "#2ca02c",
    "list": "#17becf",
    "header": "#7f7f7f",
    "footer": "#7f7f7f",
    "page_number": "#bcbd22",
}


def write_debug_blocks(
    structured_page: dict[str, Any],
    output_dir: str | Path,
    *,
    image: Any | None = None,
) -> dict[str, str]:
    """Write block-layout debug PNG and HTML for one structured MathCraft page."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    blocks = _extract_blocks(structured_page)
    width, height = _page_size(structured_page, image)

    png_path = out / "debug_blocks.png"
    html_path = out / "debug_blocks.html"
    _write_png(png_path, blocks, width, height, image=image)
    _write_html(html_path, blocks, width, height, png_path.name)
    return {"png": str(png_path), "html": str(html_path)}


def _extract_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_blocks = page.get("blocks")
    if not isinstance(raw_blocks, list):
        return []
    blocks: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            continue
        box = _box_to_xyxy(raw.get("box"))
        if box is None:
            continue
        item = dict(raw)
        item["_index"] = index
        item["_xyxy"] = box
        blocks.append(item)
    return blocks


def _page_size(page: dict[str, Any], image: Any | None) -> tuple[int, int]:
    if image is not None and hasattr(image, "size"):
        size = getattr(image, "size")
        if isinstance(size, tuple) and len(size) >= 2:
            return int(size[0]), int(size[1])
    raw_size = page.get("image_size")
    if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 2:
        width = int(float(raw_size[0]))
        height = int(float(raw_size[1]))
        if width > 0 and height > 0:
            return width, height
    max_x = 1.0
    max_y = 1.0
    for block in _extract_blocks(page):
        _x1, _y1, x2, y2 = block["_xyxy"]
        max_x = max(max_x, x2)
        max_y = max(max_y, y2)
    return int(max_x), int(max_y)


def _box_to_xyxy(raw_box: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
        return None
    points: list[tuple[float, float]] = []
    for point in raw_box[:4]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            points.append((float(point[0]), float(point[1])))
        except Exception:
            return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _write_png(
    path: Path,
    blocks: list[dict[str, Any]],
    width: int,
    height: int,
    *,
    image: Any | None,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - dependency fallback
        raise RuntimeError("debug PNG output requires Pillow") from exc

    if image is None:
        canvas = Image.new("RGB", (width, height), "white")
    elif hasattr(image, "convert"):
        canvas = image.convert("RGB")
    else:
        canvas = Image.fromarray(image).convert("RGB")

    draw = ImageDraw.Draw(canvas, "RGBA")
    font = ImageFont.load_default()
    for block in blocks:
        x1, y1, x2, y2 = block["_xyxy"]
        role = str(block.get("role") or "paragraph")
        color = _ROLE_COLORS.get(role, "#ff7f0e")
        rgba = _hex_to_rgba(color, alpha=72)
        outline = _hex_to_rgba(color, alpha=230)
        draw.rectangle((x1, y1, x2, y2), fill=rgba, outline=outline, width=3)
        label = _block_label(block)
        label_box = draw.textbbox((x1 + 3, y1 + 3), label, font=font)
        draw.rectangle(label_box, fill=(255, 255, 255, 210))
        draw.text((x1 + 3, y1 + 3), label, fill=outline, font=font)
    canvas.save(path)


def _write_html(
    path: Path,
    blocks: list[dict[str, Any]],
    width: int,
    height: int,
    image_name: str,
) -> None:
    rows = []
    overlays = []
    for block in blocks:
        x1, y1, x2, y2 = block["_xyxy"]
        role = str(block.get("role") or "paragraph")
        color = _ROLE_COLORS.get(role, "#ff7f0e")
        label = _block_label(block)
        overlays.append(
            f'<div class="box" style="left:{x1}px;top:{y1}px;width:{x2 - x1}px;height:{y2 - y1}px;border-color:{color};">'
            f'<span style="background:{color}">{escape(label)}</span></div>'
        )
        rows.append(
            "<tr>"
            f"<td>{escape(str(block.get('_index', '')))}</td>"
            f"<td>{escape(str(block.get('reading_order', '')))}</td>"
            f"<td>{escape(role)}</td>"
            f"<td>{escape(str(block.get('kind', '')))}</td>"
            f"<td>{escape(str(block.get('column', '')))}</td>"
            f"<td>{escape(str(block.get('line_id', '')))}</td>"
            f"<td>{escape(str(block.get('paragraph_id', '')))}</td>"
            f"<td>{escape(str(round(float(block.get('score') or 0.0), 3)))}</td>"
            f"<td>{escape(str(block.get('confidence_flags', '')))}</td>"
            f"<td>{escape(str(block.get('text', ''))[:240])}</td>"
            "</tr>"
        )

    html = f"""<!doctype html>
<meta charset="utf-8">
<title>MathCraft Debug Blocks</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; margin: 16px; color: #222; }}
.stage {{ position: relative; width: {width}px; height: {height}px; border: 1px solid #ccc; }}
.stage img {{ position:absolute; left:0; top:0; width:{width}px; height:{height}px; }}
.box {{ position: absolute; border: 3px solid; box-sizing: border-box; background: rgba(255,255,255,0.06); }}
.box span {{ color: white; font-size: 12px; padding: 1px 3px; }}
table {{ border-collapse: collapse; margin-top: 16px; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 4px 6px; font-size: 12px; vertical-align: top; }}
th {{ background: #f2f2f2; }}
</style>
<h1>MathCraft Debug Blocks</h1>
<p>bbox / role / column / reading order / score visualization.</p>
<div class="stage"><img src="{escape(image_name)}" alt="debug page">{''.join(overlays)}</div>
<table>
<thead><tr><th>#</th><th>order</th><th>role</th><th>kind</th><th>col</th><th>line</th><th>pid</th><th>score</th><th>flags</th><th>text</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
"""
    path.write_text(html, encoding="utf-8")


def _block_label(block: dict[str, Any]) -> str:
    order = block.get("reading_order", block.get("_index", ""))
    role = str(block.get("role") or "paragraph")
    kind = str(block.get("kind") or "")
    col = block.get("column", "")
    score = float(block.get("score") or 0.0)
    return f"{order} {role}/{kind} c{col} {score:.2f}"


def _hex_to_rgba(color: str, *, alpha: int) -> tuple[int, int, int, int]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        return 255, 127, 14, alpha
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha

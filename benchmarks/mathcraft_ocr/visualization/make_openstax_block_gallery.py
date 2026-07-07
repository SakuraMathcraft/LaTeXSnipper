# coding: utf-8

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


TEXT_COLOR = (31, 119, 180)
FORMULA_COLOR = (214, 39, 40)
HEADING_COLOR = (44, 160, 44)
ANCHOR_COLOR = (148, 103, 189)
LOW_SCORE_COLOR = (255, 127, 14)
PANEL_BACKGROUND = (255, 255, 255)
PANEL_BORDER = (220, 220, 220)


@dataclass(frozen=True)
class PageRecord:
    sample_id: str
    source_id: str
    page_number: int | None
    image_path: Path
    blocks: list[dict[str, Any]]
    latency_ms: float


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create OpenStax block-detection figure assets from MathCraft mixed-page results."
    )
    parser.add_argument("--results", required=True, help="OpenStax mixed-page result JSONL.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated PNG and HTML assets.")
    parser.add_argument("--samples", nargs="*", default=[], help="Optional explicit sample ids.")
    parser.add_argument("--limit", type=int, default=6, help="Number of auto-selected pages.")
    parser.add_argument("--max-width", type=int, default=1800, help="Maximum width for each full panel.")
    args = parser.parse_args(argv)

    records = load_records(Path(args.results))
    selected = select_records(records, sample_ids=set(args.samples), limit=args.limit)
    if not selected:
        raise SystemExit("no OpenStax records selected")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean_output_dir(output_dir)

    gallery_rows = []
    for record in selected:
        panel_path = output_dir / f"{record.sample_id}_block_panel.png"
        overlay_path = output_dir / f"{record.sample_id}_overlay.png"
        make_overlay(record, overlay_path, max_width=args.max_width)
        make_panel(record, overlay_path, panel_path, max_width=args.max_width)
        rel_panel = panel_path.name
        formula_count = sum(1 for block in record.blocks if is_formula_block(block))
        display_count = sum(1 for block in record.blocks if is_formula_block(block) and block.get("is_display"))
        gallery_rows.append(
            {
                "sample_id": record.sample_id,
                "source_id": record.source_id,
                "page_number": record.page_number,
                "block_count": len(record.blocks),
                "formula_count": formula_count,
                "display_count": display_count,
                "latency_ms": record.latency_ms,
                "panel": rel_panel,
            }
        )

    write_html(output_dir / "openstax_block_gallery.html", gallery_rows)
    write_manifest(output_dir / "openstax_block_gallery.jsonl", gallery_rows)
    print(f"wrote {len(gallery_rows)} OpenStax block figure panels to {output_dir}")
    return 0


def load_records(path: Path) -> list[PageRecord]:
    records: list[PageRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("ok"):
                continue
            image_path = Path(str(row.get("image", "")))
            sample_id = str(row.get("sample_id", ""))
            source_id, page_number = parse_openstax_sample_id(sample_id)
            records.append(
                PageRecord(
                    sample_id=sample_id,
                    source_id=source_id,
                    page_number=page_number,
                    image_path=image_path,
                    blocks=list(row.get("blocks") or []),
                    latency_ms=float(row.get("latency_ms") or 0.0),
                )
            )
    return records


def clean_output_dir(output_dir: Path) -> None:
    for pattern in (
        "openstax_*_block_panel.png",
        "openstax_*_overlay.png",
        "openstax_block_gallery.html",
        "openstax_block_gallery.jsonl",
    ):
        for path in output_dir.glob(pattern):
            if path.is_file():
                path.unlink()


def parse_openstax_sample_id(sample_id: str) -> tuple[str, int | None]:
    prefix = "openstax_"
    text = sample_id[len(prefix) :] if sample_id.startswith(prefix) else sample_id
    if "_p" not in text:
        return text, None
    source_id, page_text = text.rsplit("_p", 1)
    try:
        return source_id, int(page_text)
    except ValueError:
        return source_id, None


def select_records(records: list[PageRecord], *, sample_ids: set[str], limit: int) -> list[PageRecord]:
    if sample_ids:
        by_id = {record.sample_id: record for record in records}
        missing = sorted(sample_ids.difference(by_id))
        if missing:
            raise SystemExit(f"unknown sample ids: {', '.join(missing)}")
        return [by_id[sample_id] for sample_id in sorted(sample_ids)]

    selected: list[PageRecord] = []
    for source_id in sorted({record.source_id for record in records}):
        source_records = [record for record in records if record.source_id == source_id]
        add_first(
            selected,
            sorted(source_records, key=display_record_score, reverse=True),
            limit=limit,
        )
        add_first(
            selected,
            sorted(source_records, key=record_score, reverse=True),
            limit=limit,
        )
        if len(selected) >= limit:
            return selected[:limit]

    ranked = sorted(records, key=record_score, reverse=True)
    for record in ranked:
        if record not in selected:
            selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def add_first(selected: list[PageRecord], candidates: list[PageRecord], *, limit: int) -> None:
    for record in candidates:
        if record not in selected:
            selected.append(record)
            return


def record_score(record: PageRecord) -> tuple[int, int, int, float]:
    formula_count = sum(1 for block in record.blocks if is_formula_block(block))
    display_count = sum(1 for block in record.blocks if is_formula_block(block) and block.get("is_display"))
    heading_count = sum(1 for block in record.blocks if str(block.get("role")) == "heading")
    return formula_count, display_count, heading_count, -record.latency_ms


def display_record_score(record: PageRecord) -> tuple[int, int, int, float]:
    formula_count = sum(1 for block in record.blocks if is_formula_block(block))
    display_count = sum(1 for block in record.blocks if is_formula_block(block) and block.get("is_display"))
    block_count = len(record.blocks)
    return display_count, formula_count, block_count, -record.latency_ms


def make_overlay(record: PageRecord, output: Path, *, max_width: int) -> None:
    image = Image.open(record.image_path).convert("RGB")
    scale = min(1.0, max_width / float(image.width))
    if scale != 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(max(12, int(15 * scale)))

    for index, block in enumerate(record.blocks):
        box = scaled_box(block.get("box"), scale)
        if box is None:
            continue
        color = block_color(block)
        fill = (*color, 34)
        outline = (*color, 235)
        width = max(2, int(3 * scale))
        draw.rectangle(box, fill=fill, outline=outline, width=width)
        label = block_label(index, block)
        label_box = draw.textbbox((0, 0), label, font=font)
        label_w = label_box[2] - label_box[0]
        label_h = label_box[3] - label_box[1]
        x1, y1, _x2, _y2 = box
        label_rect = (x1, max(0, y1 - label_h - 4), x1 + label_w + 6, max(label_h + 4, y1))
        draw.rectangle(label_rect, fill=(*color, 210))
        draw.text((label_rect[0] + 3, label_rect[1] + 2), label, font=font, fill=(255, 255, 255, 255))

    image.save(output)


def make_panel(record: PageRecord, overlay_path: Path, output: Path, *, max_width: int) -> None:
    original = Image.open(record.image_path).convert("RGB")
    overlay = Image.open(overlay_path).convert("RGB")
    half_width = max_width // 2
    original = fit_width(original, half_width)
    overlay = fit_width(overlay, half_width)

    title_font = load_font(24)
    meta_font = load_font(18)
    gap = 28
    margin = 28
    header_h = 78
    panel_w = original.width + overlay.width + gap + margin * 2
    panel_h = max(original.height, overlay.height) + header_h + margin
    panel = Image.new("RGB", (panel_w, panel_h), PANEL_BACKGROUND)
    draw = ImageDraw.Draw(panel)
    formula_count = sum(1 for block in record.blocks if is_formula_block(block))
    display_count = sum(1 for block in record.blocks if is_formula_block(block) and block.get("is_display"))
    title = f"{record.sample_id}: public OpenStax page-level mixed OCR"
    meta = (
        f"{len(record.blocks)} blocks, {formula_count} formula blocks, "
        f"{display_count} display formulas, latency {record.latency_ms:.1f} ms"
    )
    draw.text((margin, 18), title, font=title_font, fill=(20, 20, 20))
    draw.text((margin, 50), meta, font=meta_font, fill=(80, 80, 80))

    y = header_h
    panel.paste(original, (margin, y))
    panel.paste(overlay, (margin + original.width + gap, y))
    draw.rectangle((margin, y, margin + original.width - 1, y + original.height - 1), outline=PANEL_BORDER)
    draw.rectangle(
        (
            margin + original.width + gap,
            y,
            margin + original.width + gap + overlay.width - 1,
            y + overlay.height - 1,
        ),
        outline=PANEL_BORDER,
    )
    panel.save(output)


def fit_width(image: Image.Image, width: int) -> Image.Image:
    if image.width == width:
        return image
    height = int(image.height * (width / float(image.width)))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def scaled_box(value: Any, scale: float) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or not value:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in value:
        if not isinstance(point, list) or len(point) < 2:
            continue
        xs.append(float(point[0]))
        ys.append(float(point[1]))
    if not xs or not ys:
        return None
    return (
        int(min(xs) * scale),
        int(min(ys) * scale),
        int(max(xs) * scale),
        int(max(ys) * scale),
    )


def block_color(block: dict[str, Any]) -> tuple[int, int, int]:
    flags = set(block.get("confidence_flags") or [])
    if "low_score" in flags:
        return LOW_SCORE_COLOR
    role = str(block.get("role") or "")
    if role == "heading":
        return HEADING_COLOR
    if role in {"formula_anchor", "formula_label"}:
        return ANCHOR_COLOR
    if is_formula_block(block):
        return FORMULA_COLOR
    return TEXT_COLOR


def block_label(index: int, block: dict[str, Any]) -> str:
    kind = str(block.get("kind") or "block")
    role = str(block.get("role") or "")
    score = block.get("score")
    score_text = f"{float(score):.2f}" if isinstance(score, int | float) else ""
    if role and role != kind:
        return f"{index} {role}/{kind} {score_text}".strip()
    return f"{index} {kind} {score_text}".strip()


def is_formula_block(block: dict[str, Any]) -> bool:
    source = str(block.get("source") or "")
    kind = str(block.get("kind") or "")
    return source.startswith("formula_") or kind in {"formula", "embedding", "isolated", "display_formula"}


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def write_html(path: Path, rows: list[dict[str, Any]]) -> None:
    cards = []
    for row in rows:
        cards.append(
            f"""
            <section class="card">
              <h2>{html.escape(str(row["sample_id"]))}</h2>
              <p>{html.escape(str(row["source_id"]))} page {html.escape(str(row["page_number"]))};
                 {row["block_count"]} blocks, {row["formula_count"]} formula blocks,
                 {row["display_count"]} display formulas.</p>
              <img src="{html.escape(str(row["panel"]))}" alt="{html.escape(str(row["sample_id"]))}">
            </section>
            """
        )

    path.write_text(
        f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MathCraft OpenStax Block Gallery</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; color: #111; }}
h1 {{ font-size: 22px; margin: 0 0 8px; }}
.note {{ color: #555; max-width: 980px; line-height: 1.45; }}
.card {{ border-top: 1px solid #ddd; padding: 18px 0; }}
.card h2 {{ font-size: 15px; margin: 0 0 4px; }}
.card p {{ color: #555; font-size: 13px; margin: 0 0 10px; }}
img {{ max-width: 100%; border: 1px solid #ddd; background: #fff; }}
</style>
</head>
<body>
<h1>MathCraft OpenStax Block Gallery</h1>
<p class="note">Page images are rendered from public OpenStax PDFs and should be used with attribution
according to the relevant OpenStax license. Generated overlays visualize MathCraft mixed runtime blocks.</p>
{''.join(cards)}
</body>
</html>
""",
        encoding="utf-8",
    )


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

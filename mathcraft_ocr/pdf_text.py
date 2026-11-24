"""Merge trusted PDF glyphs with recognized formula regions."""

from __future__ import annotations

from itertools import groupby

from .layout import box_to_xyxy, overlap_ratio
from .protocol import PdfGlyph, PdfTextLine, unreliable_pdf_character
from .results import MathCraftBlock


def has_native_columns(lines: list[PdfTextLine]) -> bool:
    left, right, spanning = [], [], []
    for line in lines:
        glyphs = line["glyphs"]
        if not glyphs or line["heading_level"] == 1 or line["role"] == "author":
            continue
        x0 = min(glyph[1] for glyph in glyphs)
        x1 = max(glyph[3] for glyph in glyphs)
        if x1 - x0 < 0.17:
            continue
        y = min(glyph[2] for glyph in glyphs)
        if x1 <= 0.505:
            left.append(y)
        elif x0 >= 0.495:
            right.append(y)
        elif x1 - x0 >= 0.48:
            spanning.append(y)
    if min(len(left), len(right)) < 3:
        return False
    start, end = max(min(left), min(right)), min(max(left), max(right))
    # The columns must persist over a band of the page, with few full-width lines.
    return end - start >= 0.04 and 3 * sum(start <= y <= end for y in spanning) < min(
        len(left), len(right)
    )


def native_text_blocks(
    lines: list[PdfTextLine],
    formulas: list[MathCraftBlock],
    image_size: tuple[int, int],
) -> list[MathCraftBlock] | None:
    width, height = image_size
    formula_boxes = [box_to_xyxy(block.box) for block in formulas if block.text.strip()]
    blocks = []
    for line in lines:
        glyphs = line["glyphs"]
        if not glyphs:
            continue
        top = min(glyph[2] for glyph in glyphs) * height
        bottom = max(glyph[4] for glyph in glyphs) * height
        overlapping = [box for box in formula_boxes if box[1] < bottom and box[3] > top]

        def covered(
            glyph: PdfGlyph,
            *,
            heading_level=line["heading_level"],
            role=line["role"],
            boxes=overlapping,
        ) -> bool:
            if heading_level is not None or role == "author":
                return False
            _, x0, y0, x1, y1, _ = glyph
            center_x = (x0 + x1) * width / 2
            y0, y1 = y0 * height, y1 * height
            for left, upper, right, lower in boxes:
                overlap = min(y1, lower) - max(y0, upper)
                if (
                    left <= center_x <= right
                    and overlap >= max(1, min(y1 - y0, lower - upper)) * 0.5
                ):
                    return True
            return False

        for is_formula, group in groupby(glyphs, key=covered):
            if is_formula:
                continue
            run = list(group)
            text = "".join(glyph[0] for glyph in run).strip()
            if not text:
                continue
            if any(unreliable_pdf_character(char) for char in text):
                return None
            x0, y0, x1, y1 = (
                min(glyph[1] for glyph in run),
                min(glyph[2] for glyph in run),
                max(glyph[3] for glyph in run),
                max(glyph[4] for glyph in run),
            )
            if x0 >= x1 or y0 >= y1:
                continue
            blocks.append(
                MathCraftBlock(
                    "text",
                    _pixel_box(x0, y0, x1, y1, width, height),
                    text,
                    1.0,
                    source="pdf_text",
                    paragraph_id=line["paragraph"],
                    heading_level=line["heading_level"],
                    role=line["role"],
                    markdown_text=_bold_glyph_runs(run)
                    if line["heading_level"] is None and not line["role"]
                    else "",
                )
            )
    return blocks or None


def merge_pdf_structure(
    lines: list[PdfTextLine],
    ocr_blocks: list[MathCraftBlock],
    image_size: tuple[int, int],
) -> list[MathCraftBlock]:
    """Keep readable headings and bylines when the body requires raster OCR."""
    structure = native_text_blocks(
        [
            line
            for line in lines
            if (line["heading_level"] is not None or line["role"] == "author")
            and not any(
                unreliable_pdf_character(char)
                for glyph in line["glyphs"]
                for char in glyph[0]
            )
        ],
        [],
        image_size,
    )
    if not structure:
        return ocr_blocks
    return structure + [
        block
        for block in ocr_blocks
        if not any(
            overlap_ratio(block.box, item.box) >= 0.55
            or (
                overlap_ratio(item.box, block.box) >= 0.8
                and "".join(block.text.casefold().split())
                == "".join(item.text.casefold().split())
            )
            for item in structure
        )
    ]


def _bold_glyph_runs(glyphs: list[PdfGlyph]) -> str:
    if not any(glyph[5] for glyph in glyphs):
        return ""
    parts = []
    for bold, group in groupby(glyphs, key=lambda glyph: glyph[5]):
        raw = "".join(glyph[0] for glyph in group)
        content = raw.strip()
        if bold and content:
            start = len(raw) - len(raw.lstrip())
            parts.append(f"{raw[:start]}**{content}**{raw[start + len(content) :]}")
        else:
            parts.append(raw)
    return "".join(parts).strip()


def _pixel_box(x0: float, y0: float, x1: float, y1: float, width: float, height: float):
    left, top, right, bottom = x0 * width, y0 * height, x1 * width, y1 * height
    return ((left, top), (right, top), (right, bottom), (left, bottom))

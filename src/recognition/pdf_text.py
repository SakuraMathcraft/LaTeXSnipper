"""Read visible, horizontal PDF text and heading evidence before OCR."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any, cast

from mathcraft_ocr.pdf_text import PdfGlyph, PdfTextLine, unreliable_pdf_character

if TYPE_CHECKING:
    from fitz import Page

_SECTION_PREFIX = re.compile(
    r"^(?:§?\s*\d+(?:\.\d+)*\.?\s+|[IVXLCDM]+\.\s+|[A-Z][.)]\s+)"
)
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\s*\.?\s+(\S.*)$")
_CHAPTER = re.compile(r"^(?:chapter\s+\d+\b|第\s*[\d一二三四五六七八九十]+\s*章)", re.I)
_CONTENTS_ENTRY = re.compile(r"\.{3,}\s*\d+\s*$")
_FOLIO = re.compile(r"^(?:\|\s*)?(?:\d+|[ivxlcdm]+)(?:\s*\|)?$", re.I)
_LIST_MARKERS = ("•", "- ", "– ", "* ")
_ENVIRONMENT = re.compile(
    r"^(?:(?:Example|Theorem|Lemma|Corollary|Proposition|Definition|Proof|Remark)\b"
    r"|(?:例题|例|定理|引理|推论|命题|定义|证明|注)\s*[\d：:])",
    re.I,
)


def _heading_key(text: str) -> str:
    return "".join(char for char in text.casefold() if char.isalnum())


def visible_pdf_text(
    page: Page, *, text_flags: int, outline: list[tuple[int, str]]
) -> list[PdfTextLine] | None:
    """Return normalized glyph boxes or leave the whole page to OCR."""
    rect = page.rect
    # Rotated/vertical writing and a full-page raster need the normal OCR path.
    if page.rotation or not rect.width or not rect.height:
        return None
    raw = cast(dict[str, Any], page.get_text("rawdict", flags=text_flags))
    lines = []
    font_weights: Counter[float] = Counter()
    invalid = characters = visible_characters = 0
    for block in raw["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = line["spans"]
            if tuple(line["dir"]) != (1.0, 0.0):
                return None
            visible = [
                span
                for span in spans
                if span.get("alpha", 255) and span.get("char_flags", 16) & 48
            ]
            characters += sum(len(span["chars"]) for span in spans)
            glyphs: list[PdfGlyph] = []
            for span in visible:
                chars = span["chars"]
                font_weights[round(span["size"], 1)] += len(chars)
                for glyph in chars:
                    text = glyph["c"]
                    x0, y0, x1, y1 = glyph["bbox"]
                    glyphs.append(
                        (
                            text,
                            (x0 - rect.x0) / rect.width,
                            (y0 - rect.y0) / rect.height,
                            (x1 - rect.x0) / rect.width,
                            (y1 - rect.y0) / rect.height,
                            bool(span["flags"] & 16),
                        )
                    )
                    invalid += sum(unreliable_pdf_character(char) for char in text)
            visible_characters += len(glyphs)
            text = "".join(glyph[0] for glyph in glyphs).strip()
            if text and visible:
                bbox = line["bbox"]
                if lines and lines[-1][0] == block["number"]:
                    _, previous_box, previous_spans, previous_glyphs, previous = lines[
                        -1
                    ]
                    size = visible[0]["size"]
                    gap = bbox[0] - previous_box[2]
                    section_number = (
                        re.fullmatch(r"\d+(?:\.\d+)*\.?", previous)
                        and abs(previous_box[1] - bbox[1]) < size * 0.1
                        and previous_spans[0]["size"] == size
                        and previous_spans[0]["flags"] & visible[0]["flags"] & 16
                        and 0 <= gap <= size * 2
                    )
                    drop_cap = (
                        len(previous) == 1
                        and previous.isupper()
                        and previous_spans[0]["size"] > size * 1.7
                        and -size * 0.15 <= gap <= size * 0.45
                        and abs(previous_box[1] - bbox[1]) <= size * 0.4
                    )
                    if section_number or drop_cap:
                        lines.pop()
                        bbox = (
                            *previous_box[:2],
                            bbox[2],
                            max(previous_box[3], bbox[3]),
                        )
                        if section_number:
                            previous_glyphs.append((" ", *glyphs[0][1:]))
                        else:
                            # The decorative initial is part of the first word.
                            previous_glyphs = [
                                (*glyph[:5], False) for glyph in previous_glyphs
                            ]
                        glyphs = previous_glyphs + glyphs
                        text = "".join(glyph[0] for glyph in glyphs).strip()
                        if section_number:
                            visible = previous_spans + visible
                lines.append((block["number"], bbox, visible, glyphs, text))
    if (
        visible_characters < 80
        or len(lines) < 4
        or visible_characters < characters * 0.95
        or invalid > visible_characters * 0.04
    ):
        return None
    if any(
        (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) >= rect.width * rect.height * 0.65
        for item in page.get_image_info()
        if (bbox := item["bbox"])
    ):
        return None

    normal_size = font_weights.most_common(1)[0][0]
    bookmarks: dict[str, int] = {}
    for level, text in outline:
        key = _heading_key(text)
        bookmarks[key] = min(bookmarks.get(key, 6), level + 1)
    text_keys = Counter(_heading_key(text) for _, _, _, _, text in lines)
    title_lines: set[int] = set()
    compact_title = False
    if page.number == 0:
        for index, (_, bbox, spans, _, text) in enumerate(lines):
            centered = abs((bbox[0] + bbox[2]) / 2 - rect.width / 2) < rect.width * 0.18
            if (
                bbox[1] < rect.height * 0.38
                and centered
                and len(text) > 5
                and max(s["size"] for s in spans) >= normal_size * 1.6
            ):
                title_lines.add(index)
        if not title_lines:
            candidates = [
                (bbox[1], index)
                for index, (_, bbox, _, _, text) in enumerate(lines)
                if bbox[1] >= rect.height * 0.08 and len(text) > 5
            ]
            if candidates:
                _, index = min(candidates)
                _, bbox, spans, _, text = lines[index]
                if (
                    bbox[1] < rect.height * 0.30
                    and abs(bbox[0] + bbox[2] - rect.width) < rect.width * 0.16
                    and text.isupper()
                    and all(span["flags"] & 16 for span in spans)
                ):
                    title_lines.add(index)
                    compact_title = True
    author_line = None
    if title_lines:
        title_bottom = max(lines[index][1][3] for index in title_lines)
        for index, (_, bbox, spans, _, text) in enumerate(lines):
            centered = abs((bbox[0] + bbox[2]) / 2 - rect.width / 2) < rect.width * 0.1
            if (
                title_bottom < bbox[1] < title_bottom + normal_size * 3
                and centered
                and (len(text.split()) >= 2 or any(mark in text for mark in "，、"))
                and not text.endswith((".", "。"))
                and max(span["size"] for span in spans) <= normal_size * 1.35
            ):
                author_line = index
                break
    if compact_title and author_line is None:
        title_lines.clear()
    result: list[PdfTextLine] = []
    paragraph = 0
    previous_block = None
    previous_x = 0.0
    list_block = False
    for index, (block_id, bbox, spans, glyphs, text) in enumerate(lines):
        if (
            (bbox[1] < rect.height * 0.12 or bbox[1] > rect.height * 0.86)
            and _FOLIO.fullmatch(text)
        ) or (
            bbox[1] < rect.height * 0.085
            and text_keys[_heading_key(text)] > 1
            and max(span["size"] for span in spans) <= normal_size * 1.05
            and not any(span["flags"] & 16 for span in spans)
        ):
            continue
        if block_id != previous_block:
            list_block = text.startswith(_LIST_MARKERS)
            paragraph += 1
        elif not list_block and bbox[0] - previous_x >= normal_size * 0.8:
            paragraph += 1
        previous_block, previous_x = block_id, bbox[0]
        role = "author" if index == author_line else ""
        level = (
            1
            if index in title_lines
            else None
            if role or list_block
            else _heading_level(
                text, spans, normal_size, bookmarks, (bbox[2] - bbox[0]) / rect.width
            )
        )
        trailing = spans[-1]
        if (
            level
            and len(spans) > 1
            and trailing["flags"] & 1
            and all(char["c"].isdigit() for char in trailing["chars"])
        ):
            glyphs = glyphs[: -len(trailing["chars"])]
        result.append(
            {
                "glyphs": glyphs,
                "heading_level": level,
                "paragraph": paragraph,
                "role": role,
            }
        )
    return result


def _heading_level(text, spans, normal_size, bookmarks, relative_width) -> int | None:
    if (
        len(text) < 2
        or len(text) > 150
        or text.startswith(_LIST_MARKERS)
        or _CONTENTS_ENTRY.search(text)
        or _ENVIRONMENT.match(text)
    ):
        return None
    key = _heading_key(text)
    bookmarked = bookmarks.get(
        key, bookmarks.get(_heading_key(_SECTION_PREFIX.sub("", text)))
    )
    if bookmarked is not None:
        return bookmarked
    sizes: Counter[float] = Counter()
    for span in spans:
        sizes[round(span["size"], 1)] += len(span["chars"])
    size = sizes.most_common(1)[0][0]
    bold = sum(len(span["chars"]) for span in spans if span["flags"] & 16)
    width = sum(len(span["chars"]) for span in spans)
    emphasized = size >= normal_size * 1.13 or bold >= width * 0.8
    if not emphasized or unreliable_pdf_character(text[0]):
        return None
    if _CHAPTER.match(text):
        return 2
    numeric = _SECTION_NUMBER.match(text)
    if numeric and not numeric[2].endswith((".", "。", ";", "；")):
        return min(2 + numeric[1].count("."), 6)
    if (
        size >= normal_size * 1.26
        and (relative_width < 0.52 or bold >= width * 0.8)
        and not text.endswith((".", "。", ";", "；", ":", "："))
    ):
        return 2
    return None

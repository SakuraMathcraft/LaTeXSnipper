# -*- coding: utf-8 -*-
"""Rule-based document cleanup for MathCraft PDF OCR output."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

try:
    import pypandoc
except ImportError:  # pragma: no cover
    pypandoc = None


_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+?)\s*$")
_COMPACT_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)+)(?!\.)(\S.+?)\s*$")
_CHINESE_CHAPTER_RE = re.compile(r"^(第\s*\d+\s*章)\s*(.+?)\s*$")
_SINGLE_CHAPTER_RE = re.compile(r"^Chapter\s+\d+\s*$", re.IGNORECASE)
_BLOCK_LEAD_RE = re.compile(
    r"^(Theorem|Lemma|Corollary|Proposition|Definition|Proof|Remark|Example)\b",
    re.IGNORECASE,
)
_TERMINAL_RE = re.compile(r"[.!?。！？□\)]\s*$")
_PAGE_NUMBER_RE = re.compile(r"^(?:\d+|[ivxlcdm]+)$", re.IGNORECASE)
_UNNUMBERED_HEADING_RE = re.compile(
    r"^(Acknowledgements?|Preface|Contents|References|Bibliography|Index)\s*$",
    re.IGNORECASE,
)
_DISPLAY_MATH_TEXT_RE = re.compile(
    r"\\begin\s*\{\s*(?:aligned|align|array|matrix|pmatrix|bmatrix|vmatrix|cases|split|gathered)\s*\}"
    r"|\\left\s*\("
)


@dataclass(slots=True)
class _Block:
    kind: str
    text: str
    page_index: int


@dataclass(slots=True)
class _StructuredBlock:
    kind: str
    text: str
    box: tuple[float, float, float, float]
    page_index: int
    page_width: float
    page_height: float
    score: float
    source: str = ""
    line_id: int | None = None
    reading_order: int | None = None
    is_display: bool | None = None
    role: str = ""
    column: int | None = None
    paragraph_id: int | None = None
    confidence_flags: tuple[str, ...] = ()


def convert_latex_to_typst(latex_code: str) -> str:
    """Convert LaTeX formula text to Typst when pypandoc is available."""
    if pypandoc is None:
        return latex_code
    try:
        return str(pypandoc.convert_text(latex_code, "typst", format="latex")).strip()
    except Exception:
        return latex_code


def compose_mathcraft_markdown_pages(page_results: list[dict[str, Any]] | tuple[dict[str, Any], ...], *, typst_formulas: bool = False) -> str:
    """Compose page-level structured MathCraft OCR results into Markdown."""
    page_texts: list[str] = []
    for page_index, page in enumerate(page_results, start=1):
        page_text = _structured_page_to_text(page, page_index)
        if page_text.strip():
            page_texts.append(page_text)
    return compose_mathcraft_markdown_document(page_texts, typst_formulas=typst_formulas)


def compose_mathcraft_markdown_document(page_texts: list[str] | tuple[str, ...], *, typst_formulas: bool = False) -> str:
    """Compose page-level MathCraft OCR text into a cleaner Markdown document."""
    pages = [str(page or "").replace("\r\n", "\n").strip() for page in page_texts]
    pages = [page for page in pages if page]
    if not pages:
        return ""

    blocks: list[_Block] = []
    for page_index, page in enumerate(pages, start=1):
        blocks.extend(_page_text_to_blocks(page, page_index))
    blocks = _promote_document_headings(blocks)
    blocks = _merge_cross_page_continuations(blocks)
    return _render_blocks(blocks, typst_formulas=typst_formulas)


def _page_text_to_blocks(text: str, page_index: int) -> list[_Block]:
    blocks: list[_Block] = []
    paragraph_lines: list[str] = []
    math_lines: list[str] = []
    in_math = False
    seen_section = False
    pending_chapter_label: str | None = None
    raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
    has_section_on_page = any(_is_section_heading(line) for line in raw_lines)
    is_contents_page = any(_is_contents_heading(line) for line in raw_lines)

    if page_index == 1 and raw_lines and not has_section_on_page and _looks_like_title_page(raw_lines):
        return [_Block("title", _join_text_lines(raw_lines), page_index)]

    if page_index == 2 and raw_lines and not has_section_on_page and _looks_like_title_page(raw_lines):
        return [_Block("paragraph", line, page_index) for line in raw_lines]

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = _join_text_lines(paragraph_lines)
        paragraph_lines.clear()
        if paragraph:
            blocks.append(_Block("paragraph", paragraph, page_index))

    def flush_math() -> None:
        if not math_lines:
            return
        math = "\n".join(line.rstrip() for line in math_lines).strip()
        math_lines.clear()
        if math:
            blocks.append(_Block("formula", _normalize_display_math(math), page_index))

    def flush_pending_chapter_as_list() -> None:
        nonlocal pending_chapter_label
        if pending_chapter_label:
            blocks.append(_Block("list_item", pending_chapter_label, page_index))
            pending_chapter_label = None

    for raw_line in text.split("\n"):
        line = _clean_ocr_line(raw_line.strip())
        if not line:
            if in_math:
                math_lines.append("")
            else:
                flush_pending_chapter_as_list()
                flush_paragraph()
            continue

        if _is_page_number(line):
            flush_pending_chapter_as_list()
            flush_paragraph()
            continue

        if not blocks and not paragraph_lines and _is_chapter_number_artifact(line):
            flush_paragraph()
            continue

        if _is_running_header(line):
            flush_pending_chapter_as_list()
            flush_paragraph()
            continue

        if pending_chapter_label:
            if _is_single_chapter_label(line):
                blocks.append(_Block("list_item", pending_chapter_label, page_index))
                pending_chapter_label = line
                continue
            if _is_chapter_chart_line(line):
                blocks.append(_Block("list_item", pending_chapter_label, page_index))
                pending_chapter_label = None
                blocks.append(_Block("list_item", line, page_index))
                continue
            if blocks and blocks[-1].kind == "list_item":
                blocks.append(_Block("list_item", pending_chapter_label, page_index))
                pending_chapter_label = None
            else:
                flush_paragraph()
                blocks.append(_Block("heading", f"{pending_chapter_label} {line}", page_index))
                pending_chapter_label = None
                seen_section = True
                continue

        if in_math:
            math_lines.append(line)
            if line.endswith("$$"):
                in_math = False
                flush_math()
            continue

        if line.startswith("$$"):
            flush_paragraph()
            in_math = True
            math_lines = [line]
            if line.endswith("$$") and len(line) > 2:
                in_math = False
                flush_math()
            continue

        if line.endswith("$$") and "$$" in line:
            prefix = line[: line.rfind("$$")].strip()
            if prefix:
                paragraph_lines.append(prefix)
                flush_paragraph()
            in_math = True
            math_lines = ["$$"]
            continue

        if _is_single_chapter_label(line):
            flush_paragraph()
            pending_chapter_label = line
            continue

        if _is_section_heading(line):
            flush_paragraph()
            if is_contents_page:
                blocks.append(_Block("list_item", line, page_index))
            else:
                blocks.append(_Block("heading", line, page_index))
            seen_section = True
            continue

        if _is_unnumbered_heading(line):
            flush_paragraph()
            blocks.append(_Block("heading", line, page_index))
            continue

        if _is_bullet_line(line):
            flush_paragraph()
            blocks.append(_Block("list_item", _normalize_bullet_line(line), page_index))
            continue

        if _is_chapter_chart_line(line):
            flush_paragraph()
            blocks.append(_Block("list_item", line, page_index))
            continue

        if _is_metadata_line(line):
            flush_paragraph()
            blocks.append(_Block("paragraph", line, page_index))
            continue

        if (
            has_section_on_page
            and page_index == 1
            and not seen_section
            and not paragraph_lines
            and len(line) <= 60
            and _looks_like_front_matter_line(line)
        ):
            blocks.append(_Block("paragraph", line, page_index))
            continue

        if _is_block_lead(line) and paragraph_lines:
            flush_paragraph()

        if paragraph_lines and _should_start_new_paragraph_after_current(paragraph_lines, line):
            flush_paragraph()

        paragraph_lines.append(line)

    if in_math:
        flush_math()
    flush_pending_chapter_as_list()
    flush_paragraph()
    return blocks


def _promote_document_headings(blocks: list[_Block]) -> list[_Block]:
    has_numbered_section = any(block.kind == "heading" for block in blocks)
    promoted: list[_Block] = []
    first_text_seen = False
    for block in blocks:
        if block.kind != "paragraph":
            promoted.append(block)
            if block.kind in {"title", "heading", "formula", "list_item"}:
                first_text_seen = True
            continue
        text = block.text.strip()
        if has_numbered_section and not first_text_seen and _looks_like_title(text):
            promoted.append(_Block("title", text, block.page_index))
            first_text_seen = True
            continue
        first_text_seen = True
        promoted.append(block)
    return promoted


def _merge_cross_page_continuations(blocks: list[_Block]) -> list[_Block]:
    merged: list[_Block] = []
    for block in blocks:
        if (
            merged
            and block.kind == "paragraph"
            and merged[-1].kind == "paragraph"
            and block.page_index != merged[-1].page_index
            and _should_merge_paragraphs(merged[-1].text, block.text)
        ):
            merged[-1] = _Block(
                "paragraph",
                _join_text_lines([merged[-1].text, block.text]),
                merged[-1].page_index,
            )
            continue
        merged.append(block)
    return merged


def _render_blocks(blocks: list[_Block], *, typst_formulas: bool = False) -> str:
    chunks: list[str] = []
    last_page = 0
    for block in blocks:
        if last_page and block.page_index != last_page:
            if chunks and not chunks[-1].startswith("<!-- Page "):
                chunks.append(f"<!-- Page {block.page_index} -->")
        last_page = block.page_index

        text = block.text.strip()
        if not text:
            continue
        if block.kind == "title":
            chunks.append(f"# {text}")
        elif block.kind == "heading":
            chunks.append(_render_section_heading(text))
        elif block.kind == "formula":
            if typst_formulas:
                chunks.append(convert_latex_to_typst(text))
            else:
                chunks.append(_normalize_display_math(text))
        elif block.kind == "list_item":
            chunks.append(f"- {text}")
        else:
            chunks.append(_render_paragraph(text))

    return "\n\n".join(chunk for chunk in chunks if chunk.strip()).strip()


def _structured_page_to_text(page: dict[str, Any], page_index: int) -> str:
    if not isinstance(page, dict):
        return str(page or "").strip()
    blocks = _extract_structured_blocks(page, page_index)
    if not blocks:
        return str(page.get("text") or "").strip()
    lines = _group_structured_blocks_into_lines(blocks)
    rendered: list[str] = []
    previous_group: tuple[str, int | None, int] | None = None
    for line in lines:
        line_text = _render_structured_line(line)
        if not line_text.strip():
            continue
        current_group = _structured_line_group_key(line)
        if (
            previous_group is not None
            and current_group != previous_group
            and _should_break_between_structured_groups(previous_group, current_group)
            and rendered
            and rendered[-1] != ""
        ):
            rendered.append("")
        rendered.append(line_text)
        previous_group = current_group
    return "\n".join(rendered).strip()


def _extract_structured_blocks(page: dict[str, Any], page_index: int) -> list[_StructuredBlock]:
    raw_blocks = page.get("blocks")
    if not isinstance(raw_blocks, list):
        return []
    page_width, page_height = _extract_page_size(page)
    blocks: list[_StructuredBlock] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        box = _structured_box_to_xyxy(raw.get("box"))
        if box is None:
            continue
        kind = str(raw.get("kind") or "text").strip().lower() or "text"
        score = _safe_float(raw.get("score"), 0.0)
        raw_page = _safe_int(raw.get("page_index"))
        raw_size = _structured_image_size(raw.get("image_size"))
        block_page_width, block_page_height = raw_size or (page_width, page_height)
        block = _StructuredBlock(
            kind=kind,
            text=text,
            box=box,
            page_index=raw_page or page_index,
            page_width=block_page_width,
            page_height=block_page_height,
            score=score,
            source=str(raw.get("source") or "").strip(),
            line_id=_safe_int(raw.get("line_id")),
            reading_order=_safe_int(raw.get("reading_order")),
            is_display=_safe_bool(raw.get("is_display")),
            role=str(raw.get("role") or "").strip().lower(),
            column=_safe_int(raw.get("column")),
            paragraph_id=_safe_int(raw.get("paragraph_id")),
            confidence_flags=_structured_flags(raw.get("confidence_flags")),
        )
        if not _is_structured_noise(block):
            blocks.append(block)
    return blocks


def _extract_page_size(page: dict[str, Any]) -> tuple[float, float]:
    parsed = _structured_image_size(page.get("image_size"))
    if parsed:
        return parsed
    return 0.0, 0.0


def _structured_image_size(raw_size: Any) -> tuple[float, float] | None:
    if isinstance(raw_size, (list, tuple)) and len(raw_size) >= 2:
        width = _safe_float(raw_size[0], 0.0)
        height = _safe_float(raw_size[1], 0.0)
        if width > 0 and height > 0:
            return width, height
    return None


def _structured_box_to_xyxy(raw_box: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) < 4:
        return None
    points: list[tuple[float, float]] = []
    for point in raw_box[:4]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        points.append((_safe_float(point[0], 0.0), _safe_float(point[1], 0.0)))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _structured_flags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _is_structured_noise(block: _StructuredBlock) -> bool:
    if block.role in {"header", "footer", "page_number"}:
        return True
    text = block.text.strip()
    if block.page_height <= 0:
        return _is_page_number(text)
    _x1, y1, _x2, y2 = block.box
    center_y = (y1 + y2) / 2.0
    is_margin = center_y < block.page_height * 0.08 or center_y > block.page_height * 0.92
    if not is_margin:
        return False
    if _is_page_number(text):
        return True
    return bool(re.match(r"^CHAPTER\s+\d+\.\s+.+$", text, flags=re.IGNORECASE))


def _group_structured_blocks_into_lines(
    blocks: list[_StructuredBlock],
    *,
    y_overlap_threshold: float = 0.45,
) -> list[list[_StructuredBlock]]:
    if blocks and all(block.line_id is not None for block in blocks):
        grouped: dict[tuple[int, int], list[_StructuredBlock]] = {}
        for block in blocks:
            grouped.setdefault((block.page_index, int(block.line_id or 0)), []).append(block)
        return [
            sorted(line, key=_structured_block_order_key)
            for _key, line in sorted(
                grouped.items(),
                key=lambda item: (
                    item[0][0],
                    _structured_column(item[1][0]),
                    min(block.box[1] for block in item[1]),
                    item[0][1],
                ),
            )
        ]

    sorted_blocks = sorted(blocks, key=_structured_block_sort_key)
    lines: list[list[_StructuredBlock]] = []
    for block in sorted_blocks:
        best_line: list[_StructuredBlock] | None = None
        best_overlap = 0.0
        for line in lines:
            line_box = _structured_union_box(line)
            if not _same_structured_region(line[0], block, line_box):
                continue
            overlap = _structured_y_overlap(line_box, block.box)
            if overlap > best_overlap:
                best_overlap = overlap
                best_line = line
        if best_line is None or best_overlap < y_overlap_threshold:
            lines.append([block])
        else:
            best_line.append(block)
    return [
        sorted(line, key=_structured_block_order_key)
        for line in sorted(lines, key=_structured_line_sort_key)
    ]


def _structured_union_box(blocks: list[_StructuredBlock]) -> tuple[float, float, float, float]:
    return (
        min(block.box[0] for block in blocks),
        min(block.box[1] for block in blocks),
        max(block.box[2] for block in blocks),
        max(block.box[3] for block in blocks),
    )


def _structured_block_sort_key(block: _StructuredBlock) -> tuple[float, float, float, float]:
    return (
        float(block.page_index),
        float(_structured_column(block)),
        block.box[1],
        block.box[0],
    )


def _structured_line_sort_key(line: list[_StructuredBlock]) -> tuple[float, float, float, float]:
    first = line[0]
    box = _structured_union_box(line)
    return (
        float(first.page_index),
        float(_structured_column(first)),
        box[1],
        box[0],
    )


def _structured_block_order_key(block: _StructuredBlock) -> tuple[float, float]:
    if block.reading_order is not None:
        return float(block.reading_order), block.box[0]
    return block.box[0], block.box[1]


def _structured_line_group_key(line: list[_StructuredBlock]) -> tuple[str, int | None, int]:
    if not line:
        return "", None, 0
    column = _structured_column(line[0])
    roles = {block.role for block in line if block.role}
    if _is_structured_display_formula_line(line):
        return "formula", line[0].paragraph_id, column
    if all(block.role == "formula_anchor" for block in line):
        return "formula_anchor", line[0].paragraph_id, column
    if all(block.role == "formula_label" for block in line):
        return "formula_label", line[0].paragraph_id, column
    if "heading" in roles:
        return "heading", line[0].paragraph_id, column
    if "list" in roles:
        return "list", line[0].paragraph_id, column
    paragraph_ids = {block.paragraph_id for block in line if block.paragraph_id is not None}
    return (
        "paragraph",
        next(iter(paragraph_ids)) if len(paragraph_ids) == 1 else None,
        column,
    )


def _should_break_between_structured_groups(
    previous: tuple[str, int | None, int],
    current: tuple[str, int | None, int],
) -> bool:
    if previous[0] != current[0]:
        return True
    if previous[0] == "paragraph":
        return previous[2] != current[2]
    if previous[1] is None or current[1] is None:
        return False
    return previous[1] != current[1]


def _same_structured_region(
    first: _StructuredBlock,
    second: _StructuredBlock,
    line_box: tuple[float, float, float, float],
) -> bool:
    if first.page_index != second.page_index:
        return False
    if _structured_column(first) == _structured_column(second):
        return True
    if _is_structured_inline_formula_like(first) or _is_structured_inline_formula_like(second):
        page_width = first.page_width or second.page_width
        if page_width <= 0:
            return False
        gap = max(0.0, max(line_box[0], second.box[0]) - min(line_box[2], second.box[2]))
        return (
            _structured_y_overlap(line_box, second.box) >= 0.45
            and gap <= page_width * 0.08
        )
    if _is_structured_display_formula_like(first) or _is_structured_display_formula_like(second):
        return False
    page_width = first.page_width or second.page_width
    if page_width > 0:
        gap = max(0.0, max(line_box[0], second.box[0]) - min(line_box[2], second.box[2]))
        return _structured_y_overlap(line_box, second.box) >= 0.75 and gap <= page_width * 0.015
    return False


def _structured_column(block: _StructuredBlock) -> int:
    if block.column is not None:
        return block.column
    if block.page_width <= 0:
        return 0
    width = block.box[2] - block.box[0]
    midline = block.page_width * 0.5
    if block.box[0] >= midline:
        return 1
    if block.box[2] <= midline:
        return 0
    if width >= block.page_width * 0.7 or _structured_crosses_page_midline(block):
        return 0
    center_x = (block.box[0] + block.box[2]) / 2.0
    return 1 if center_x >= midline else 0


def _structured_crosses_page_midline(block: _StructuredBlock) -> bool:
    return block.box[0] <= block.page_width * 0.45 and block.box[2] >= block.page_width * 0.55


def _is_structured_inline_formula_like(block: _StructuredBlock) -> bool:
    return block.kind in {"embedding", "formula", "inline_formula"}


def _is_structured_display_formula_like(block: _StructuredBlock) -> bool:
    return block.kind in {"isolated", "display_formula"} or (
        block.source == "formula_rec" and block.kind not in {"embedding", "inline_formula"}
    )


def _structured_y_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    _ax1, ay1, _ax2, ay2 = first
    _bx1, by1, _bx2, by2 = second
    overlap = max(0.0, min(ay2, by2) - max(ay1, by1))
    height = max(1.0, min(ay2 - ay1, by2 - by1))
    return overlap / height


def _render_structured_line(line: list[_StructuredBlock]) -> str:
    if not line:
        return ""
    if _is_structured_display_formula_line(line):
        anchors = [
            block.text.strip()
            for block in line
            if block.role == "formula_anchor" and block.text.strip()
        ]
        labels = [
            block.text.strip()
            for block in line
            if block.role == "formula_label" and block.text.strip()
        ]
        formula_text = " ".join(
            block.text.strip()
            for block in line
            if block.text.strip() and block.role not in {"formula_anchor", "formula_label"}
        )
        chunks: list[str] = []
        if anchors:
            chunks.append(_join_text_lines(anchors))
        if formula_text:
            chunks.append(_normalize_display_math(f"$$\n{formula_text}\n$$"))
        if labels:
            chunks.append(_join_text_lines(labels))
        return "\n\n".join(chunks)
    if any(block.role == "list" for block in line):
        item_text = _join_text_lines(
            [_normalize_bullet_line(block.text) for block in line if block.text.strip()]
        )
        return f"- {item_text}" if item_text else ""
    parts: list[str] = []
    for block in line:
        text = block.text.strip()
        if not text:
            continue
        if block.is_display is True:
            parts.append(_normalize_display_math(f"$$\n{text}\n$$"))
        elif block.kind in {"embedding", "formula", "inline_formula"}:
            parts.append(f"${text}$")
        else:
            parts.append(text)
    return _join_text_lines(parts)


def _is_structured_display_formula_line(line: list[_StructuredBlock]) -> bool:
    if any(block.is_display is True for block in line):
        return all(
            block.is_display is True
            or block.kind in {"isolated", "display_formula"}
            or block.role in {"formula_anchor", "formula_label"}
            for block in line
        )
    if len(line) > 1:
        return False
    if any(block.kind == "isolated" for block in line):
        return True
    block = line[0]
    if _DISPLAY_MATH_TEXT_RE.search(block.text or ""):
        return True
    if block.kind not in {"formula", "display_formula"} or block.page_width <= 0:
        return False
    width = block.box[2] - block.box[0]
    return width >= block.page_width * 0.35


def _render_section_heading(text: str) -> str:
    parsed = _parse_section_heading(text)
    if not parsed:
        return f"## {text.strip()}"
    number, title = parsed
    level = min(2 + number.count("."), 5)
    return f"{'#' * level} {number} {title.strip()}"


def _render_paragraph(text: str) -> str:
    text = text.strip()
    text = _normalize_block_number_spacing(text)
    match = re.match(
        r"^((?:Theorem|Lemma|Corollary|Proposition|Definition|Proof|Remark|Example)"
        r"(?:\s+\d+(?:\.\d+)*)?(?:\s*\([^)]+\))?\.?)\s+(.*)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        lead, rest = match.groups()
        lead = lead.rstrip(".")
        lead = _normalize_block_lead_label(lead)
        return f"**{lead}.** {rest}".strip()
    return text


def _normalize_display_math(text: str) -> str:
    body = text.strip()
    body = re.sub(r"^\[\]\s*", "", body)
    body = re.sub(r"\s*\[\]\s*$", "", body)
    if body.startswith("$$") and body.endswith("$$"):
        body = body[2:-2].strip()
    body = re.sub(r"^\[\]\s*", "", body).strip()
    body = re.sub(r"\s*\[\]\s*$", "", body).strip()
    return f"$$\n{body}\n$$"


def _join_text_lines(lines: list[str]) -> str:
    result = ""
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        if not result:
            result = line
            continue
        if result.endswith("-") and line and line[0].islower():
            result = result[:-1] + line
        elif line.startswith((",", ".", ";", ":", ")", "]")):
            result += line
        else:
            result += " " + line
    return _normalize_inline_spacing(result)


def _normalize_inline_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\[\]\s*", " ", text).strip()
    text = re.sub(r"fi\s+([a-z])", r"fi\1", text)
    text = re.sub(r"\s+([,.;!?])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return text


def _is_section_heading(text: str) -> bool:
    parsed = _parse_section_heading(text)
    if not parsed:
        return False
    _number, title = parsed
    if re.match(r"^\d+\s*\.", title):
        return False
    return bool(title) and len(title) <= 90 and not title.endswith((".", ",", ";", ":"))


def _parse_section_heading(text: str) -> tuple[str, str] | None:
    line = text.strip()
    match = _SECTION_RE.match(line)
    if match:
        return match.group(1), match.group(2).strip()
    match = _COMPACT_SECTION_RE.match(line)
    if match:
        return match.group(1), match.group(2).strip()
    match = _CHINESE_CHAPTER_RE.match(line)
    if match:
        return match.group(1).replace(" ", ""), match.group(2).strip()
    return None


def _is_unnumbered_heading(text: str) -> bool:
    return bool(_UNNUMBERED_HEADING_RE.match(text.strip()))


def _is_contents_heading(text: str) -> bool:
    return text.strip().lower() in {"contents", "目录"}


def _is_bullet_line(text: str) -> bool:
    return text.strip().startswith(("•", "·", "・", "-", "*"))


def _is_chapter_chart_line(text: str) -> bool:
    line = text.strip()
    if len(line) > 90 or not line.startswith("Chapter"):
        return False
    if not (line.startswith("Chapters ") or line.count("Chapter") >= 2):
        return False
    remainder = re.sub(r"Chapters?", "", line)
    remainder = re.sub(r"\d+", "", remainder)
    return not re.search(r"[A-Za-z]", remainder)


def _is_single_chapter_label(text: str) -> bool:
    return bool(_SINGLE_CHAPTER_RE.match(text.strip()))


def _is_running_header(text: str) -> bool:
    line = text.strip()
    return bool(
        re.match(r"^CHAPTER\s+\d+\.\s+.+\s+\d+$", line)
        or re.match(r"^CONTENTS\s+[ivxlcdm]+$", line, flags=re.IGNORECASE)
        or re.match(r"^\d+\s+\d+\s+[A-Z][A-Za-z].{1,80}$", line)
    )


def _normalize_bullet_line(text: str) -> str:
    return re.sub(r"^[•·・\-*\u30fb]+\s*", "", text.strip()).strip()


def _is_page_number(text: str) -> bool:
    line = text.strip()
    if not _PAGE_NUMBER_RE.match(line):
        return False
    return len(line) <= 8


def _is_chapter_number_artifact(text: str) -> bool:
    return bool(re.fullmatch(r"\$\\?neg\$", text.strip(), flags=re.IGNORECASE))


def _is_block_lead(text: str) -> bool:
    return bool(_BLOCK_LEAD_RE.match(text.strip()))


def _looks_like_title(text: str) -> bool:
    if len(text) > 120 or _is_section_heading(text) or _is_block_lead(text):
        return False
    if text.endswith((".", ",", ";", ":")):
        return False
    words = [word for word in re.split(r"\s+", text) if word]
    return 1 <= len(words) <= 14


def _looks_like_front_matter_line(text: str) -> bool:
    line = text.strip()
    if not line or len(line) > 100 or _is_section_heading(line) or _is_block_lead(line):
        return False
    words = [word for word in re.split(r"\s+", line) if word]
    return 1 <= len(words) <= 14


def _is_metadata_line(text: str) -> bool:
    line = text.strip()
    return bool(
        re.match(r"^(Edition|Website)\s*:", line, flags=re.IGNORECASE)
        or re.match(r"^[©(]?\d{4}(?:[-–]\d{4})?\b", line)
    )


def _looks_like_title_page(lines: list[str]) -> bool:
    if not 2 <= len(lines) <= 18:
        return False
    if any(line.startswith("$") or "\\" in line for line in lines):
        return False
    if any(line[:1].islower() for line in lines):
        return False
    if any(_TERMINAL_RE.search(line) for line in lines):
        return False
    return all(_looks_like_front_matter_line(line) for line in lines)


def _clean_ocr_line(line: str) -> str:
    cleaned = line.strip()
    if cleaned in {"[]", "[ ]"}:
        return ""
    cleaned = cleaned.replace("[$$", "$$")
    cleaned = cleaned.replace("[]$$", "$$")
    cleaned = cleaned.replace("$$ []", "$$")
    return cleaned.strip()


def _normalize_block_number_spacing(text: str) -> str:
    return re.sub(
        r"\b(Theorem|Lemma|Corollary|Proposition|Definition|Example)\s+(\d+)\.\s+(\d+)\b",
        r"\1 \2.\3",
        text,
        flags=re.IGNORECASE,
    )


def _normalize_block_lead_label(lead: str) -> str:
    match = re.match(r"^([A-Za-z]+)(.*)$", lead.strip())
    if not match:
        return lead.strip()
    word, rest = match.groups()
    canonical = {
        "theorem": "Theorem",
        "lemma": "Lemma",
        "corollary": "Corollary",
        "proposition": "Proposition",
        "definition": "Definition",
        "proof": "Proof",
        "remark": "Remark",
        "example": "Example",
    }.get(word.lower())
    return f"{canonical}{rest}" if canonical else lead.strip()


def _should_merge_paragraphs(previous: str, current: str) -> bool:
    prev = previous.strip()
    cur = current.strip()
    if not prev or not cur:
        return False
    if _is_metadata_line(prev) or _is_metadata_line(cur):
        return False
    if _looks_like_front_matter_line(prev) and (
        _is_metadata_line(cur) or _looks_like_front_matter_line(cur)
    ):
        return False
    if _is_section_heading(cur) or _is_block_lead(cur):
        return False
    if prev.endswith("-") and cur[0].islower():
        return True
    if not _TERMINAL_RE.search(prev):
        return True
    return cur[0].islower()


def _should_start_new_paragraph_after_current(current_lines: list[str], next_line: str) -> bool:
    current = _join_text_lines(current_lines)
    nxt = next_line.strip()
    if not current or not nxt:
        return False
    if current.endswith("□") and nxt[:1].isupper():
        return True
    if _is_block_lead(current) and _TERMINAL_RE.search(current) and nxt[:1].isupper():
        return True
    if len(current_lines) >= 3 and _TERMINAL_RE.search(current) and nxt[:1].isupper():
        return True
    return False

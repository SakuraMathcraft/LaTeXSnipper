# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import re

import numpy as np

from .results import Box4P, MathCraftBlock


@dataclass(frozen=True)
class TextSegment:
    box: Box4P


@dataclass(frozen=True)
class _LineInfo:
    blocks: tuple[MathCraftBlock, ...]
    box: Box4P
    column: int
    role: str
    paragraph_id: int | None
    is_display: bool


_CONTENT_NOISE_ROLES = {"header", "footer", "page_number"}
_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S.{0,88}$")
_COMPACT_SECTION_HEADING_RE = re.compile(r"^\d+(?:\.\d+)+[^\d\s].{0,88}$")
_CHINESE_SECTION_HEADING_RE = re.compile(r"^第\s*\d+\s*[章节].{0,60}$")
_UNNUMBERED_HEADING_RE = re.compile(
    r"^(Acknowledgements?|Preface|Contents|References|Bibliography|Index|Abstract)\s*$",
    re.IGNORECASE,
)
_BLOCK_LEAD_RE = re.compile(
    r"^(Theorem|Lemma|Corollary|Proposition|Definition|Proof|Remark|Example)\b",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^(?:\d{1,4}|[ivxlcdm]{1,8})$", re.IGNORECASE)
_JOURNAL_RUNNING_HEADER_RE = re.compile(
    r"^[A-Z][A-Z .,'-]{1,48}\s+et\s+al\.\s*:\s*.{1,90}$",
    re.IGNORECASE,
)
_FORMULA_ANCHOR_RE = re.compile(
    r"^(?:where|then|therefore|hence)\s*[:,.]?$",
    re.IGNORECASE,
)
_FORMULA_LABEL_RE = re.compile(r"^\(?\d{1,4}(?:\.\d{1,4})?[a-z]?\)?$")
_DISPLAY_MATH_TEXT_RE = re.compile(
    r"\\begin\s*\{\s*(?:aligned|align|array|matrix|pmatrix|bmatrix|vmatrix|cases|split|gathered)\s*\}"
    r"|\\left\s*\("
    r"|\\begin\s*\{\s*matrix\s*\}"
)
_RUNNING_HEADER_RE = re.compile(
    r"^(?:CHAPTER\s+\d+\.|CONTENTS\b|\d+\s+\d+\s+[A-Z][A-Za-z]).{0,90}$",
    re.IGNORECASE,
)
_TERMINAL_RE = re.compile(r"[.!?。！？\)]\s*$")


def box_to_xyxy(box: Box4P) -> tuple[float, float, float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return min(xs), min(ys), max(xs), max(ys)


def xyxy_to_box(x1: float, y1: float, x2: float, y2: float) -> Box4P:
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def points_to_box(points) -> Box4P:
    array = np.asarray(points, dtype=np.float32)
    x1 = float(np.min(array[:, 0]))
    y1 = float(np.min(array[:, 1]))
    x2 = float(np.max(array[:, 0]))
    y2 = float(np.max(array[:, 1]))
    return xyxy_to_box(x1, y1, x2, y2)


def box_to_points(box: Box4P) -> np.ndarray:
    return np.asarray(box, dtype=np.float32)


def box_area(box: Box4P) -> float:
    x1, y1, x2, y2 = box_to_xyxy(box)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def intersection_area(first: Box4P, second: Box4P) -> float:
    ax1, ay1, ax2, ay2 = box_to_xyxy(first)
    bx1, by1, bx2, by2 = box_to_xyxy(second)
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    return width * height


def overlap_ratio(first: Box4P, second: Box4P, *, denominator: str = "first") -> float:
    denom_box = first if denominator == "first" else second
    area = box_area(denom_box)
    if area <= 0:
        return 0.0
    return intersection_area(first, second) / area


def y_overlap_ratio(first: Box4P, second: Box4P) -> float:
    _ax1, ay1, _ax2, ay2 = box_to_xyxy(first)
    _bx1, by1, _bx2, by2 = box_to_xyxy(second)
    overlap = max(0.0, min(ay2, by2) - max(ay1, by1))
    height = max(1.0, min(ay2 - ay1, by2 - by1))
    return overlap / height


def mask_boxes(
    image_rgb: np.ndarray,
    boxes: tuple[Box4P, ...] | list[Box4P],
    *,
    margin: int = 1,
) -> np.ndarray:
    masked = image_rgb.copy()
    height, width = masked.shape[:2]
    for box in boxes:
        x1, y1, x2, y2 = box_to_xyxy(box)
        left = max(0, int(x1) - margin)
        top = max(0, int(y1) - margin)
        right = min(width, int(x2) + margin)
        bottom = min(height, int(y2) + margin)
        if right > left and bottom > top:
            masked[top:bottom, left:right, :] = 255
    return masked


def is_informative_ocr_box(
    image: np.ndarray,
    box: Box4P,
    *,
    min_width: float = 6.0,
    min_height: float = 6.0,
    min_area: float = 48.0,
    blank_mean_threshold: float = 249.0,
    blank_std_threshold: float = 4.0,
) -> bool:
    x1, y1, x2, y2 = box_to_xyxy(box)
    width = x2 - x1
    height = y2 - y1
    if width < min_width or height < min_height or width * height < min_area:
        return False
    img_h, img_w = image.shape[:2]
    left = max(0, int(np.floor(x1)))
    top = max(0, int(np.floor(y1)))
    right = min(img_w, int(np.ceil(x2)))
    bottom = min(img_h, int(np.ceil(y2)))
    if right <= left or bottom <= top:
        return False
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return False
    if float(np.mean(crop)) >= blank_mean_threshold and float(np.std(crop)) <= blank_std_threshold:
        return False
    return True


def split_text_box_around_formulas(
    text_box: Box4P,
    formula_boxes: tuple[Box4P, ...] | list[Box4P],
    *,
    overlap_threshold: float = 0.1,
    min_width: float = 8.0,
) -> tuple[TextSegment, ...]:
    text_x1, text_y1, text_x2, text_y2 = box_to_xyxy(text_box)
    intervals = [(text_x1, text_x2)]
    relevant_formulas = sorted(
        (
            formula_box
            for formula_box in formula_boxes
            if overlap_ratio(text_box, formula_box) >= overlap_threshold
            or y_overlap_ratio(text_box, formula_box) >= 0.6
        ),
        key=lambda box: box_to_xyxy(box)[0],
    )
    for formula_box in relevant_formulas:
        fx1, _fy1, fx2, _fy2 = box_to_xyxy(formula_box)
        next_intervals: list[tuple[float, float]] = []
        for start, end in intervals:
            if fx2 <= start or fx1 >= end:
                next_intervals.append((start, end))
                continue
            left_end = max(start, min(end, fx1))
            right_start = min(end, max(start, fx2))
            if left_end - start >= min_width:
                next_intervals.append((start, left_end))
            if end - right_start >= min_width:
                next_intervals.append((right_start, end))
        intervals = next_intervals
        if not intervals:
            break
    return tuple(
        TextSegment(box=xyxy_to_box(start, text_y1, end, text_y2))
        for start, end in intervals
        if end - start >= min_width
    )


def resolve_formula_text_conflicts(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    image_size: tuple[int, int] | None = None,
) -> tuple[MathCraftBlock, ...]:
    """Drop text fully swallowed by formulas and tag short formula-adjacent text."""
    formula_blocks = tuple(
        block
        for block in blocks
        if block.kind in {"formula", "embedding", "inline_formula", "isolated", "display_formula"}
        or block.source == "formula_rec"
    )
    if not formula_blocks:
        return tuple(blocks)

    resolved: list[MathCraftBlock] = []
    for block in blocks:
        if block in formula_blocks or block.kind != "text":
            resolved.append(block)
            continue

        text = block.text.strip()
        adjacent = _is_formula_adjacent(block, formula_blocks, image_size=image_size)
        if _is_formula_label_text(text) and adjacent:
            resolved.append(replace(block, role=block.role or "formula_label"))
            continue
        if _is_formula_anchor_text(text) and adjacent:
            resolved.append(replace(block, role=block.role or "formula_anchor"))
            continue
        if _is_text_swallowed_by_formula(block, formula_blocks):
            continue
        resolved.append(block)
    return tuple(resolved)


def group_blocks_into_lines(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    y_overlap_threshold: float = 0.45,
    image_size: tuple[int, int] | None = None,
    two_column_layout: bool | None = None,
) -> tuple[tuple[MathCraftBlock, ...], ...]:
    if two_column_layout is None:
        two_column_layout = _is_two_column_layout(blocks, image_size=image_size)
    sorted_blocks = sorted(blocks, key=lambda block: _block_sort_key(block, two_column_layout))
    lines: list[list[MathCraftBlock]] = []
    for block in sorted_blocks:
        best_line: list[MathCraftBlock] | None = None
        best_overlap = 0.0
        for line in lines:
            line_box = _union_box([item.box for item in line])
            if not _same_layout_region(line[0], block, line_box, two_column_layout=two_column_layout):
                continue
            overlap = y_overlap_ratio(line_box, block.box)
            if overlap > best_overlap:
                best_overlap = overlap
                best_line = line
        if best_line is None or best_overlap < y_overlap_threshold:
            lines.append([block])
        else:
            best_line.append(block)
    return tuple(
        tuple(sorted(line, key=lambda item: box_to_xyxy(item.box)[0]))
        for line in sorted(lines, key=lambda line: _line_sort_key(line, two_column_layout))
    )


def annotate_blocks(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    image_size: tuple[int, int] | None = None,
    page_index: int | None = None,
) -> tuple[MathCraftBlock, ...]:
    seeded = tuple(
        replace(
            block,
            page_index=block.page_index if block.page_index is not None else page_index,
            image_size=block.image_size if block.image_size is not None else image_size,
        )
        for block in blocks
    )
    two_column_layout = _is_two_column_layout(seeded, image_size=image_size)
    lines = group_blocks_into_lines(
        seeded,
        image_size=image_size,
        two_column_layout=two_column_layout,
    )
    line_infos = _annotate_lines(lines, image_size=image_size, two_column_layout=two_column_layout)
    annotated: list[MathCraftBlock] = []
    reading_order = 0
    for line_id, line_info in enumerate(line_infos):
        flags = _line_confidence_flags(line_info, image_size=image_size)
        for block in line_info.blocks:
            block_role = _block_role(block, line_info)
            block_flags = tuple(sorted(set(block.confidence_flags) | set(flags)))
            if block.score < 0.55:
                block_flags = tuple(sorted(set(block_flags) | {"low_score"}))
            annotated.append(
                replace(
                    block,
                    line_id=block.line_id if block.line_id is not None else line_id,
                    reading_order=(
                        block.reading_order
                        if block.reading_order is not None
                        else reading_order
                    ),
                    is_display=(
                        False
                        if block.role in {"formula_anchor", "formula_label"}
                        else (
                            block.is_display
                            if block.is_display is not None
                            else line_info.is_display
                        )
                    ),
                    role=block.role or block_role,
                    column=block.column if block.column is not None else line_info.column,
                    paragraph_id=(
                        block.paragraph_id
                        if block.paragraph_id is not None
                        else line_info.paragraph_id
                    ),
                    confidence_flags=block_flags,
                )
            )
            reading_order += 1
    return tuple(annotated)


def merge_blocks_text(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    line_sep: str = "\n",
    embed_sep: tuple[str, str] = (" $", "$ "),
    isolated_sep: tuple[str, str] = ("$$\n", "\n$$"),
) -> str:
    lines = group_blocks_into_lines(blocks)
    line_texts: list[str] = []
    for line in lines:
        if _line_role(line, _union_box([block.box for block in line]), image_size=None) in _CONTENT_NOISE_ROLES:
            continue
        parts: list[str] = []
        has_isolated = False
        for block in line:
            if block.role in _CONTENT_NOISE_ROLES:
                continue
            text = block.text.strip()
            if not text:
                continue
            if block.is_display is True or block.kind == "isolated":
                has_isolated = True
                parts.append(isolated_sep[0] + text + isolated_sep[1])
            elif block.kind == "embedding":
                parts.append(embed_sep[0] + text + embed_sep[1])
            else:
                parts.append(text)
        merged = _smart_join(parts).strip()
        if merged:
            if has_isolated:
                merged = line_sep + merged + line_sep
            line_texts.append(merged)
    return _collapse_line_separators(line_sep.join(line_texts), line_sep=line_sep).strip()


def _annotate_lines(
    lines: tuple[tuple[MathCraftBlock, ...], ...],
    *,
    image_size: tuple[int, int] | None,
    two_column_layout: bool,
) -> tuple[_LineInfo, ...]:
    base_infos: list[_LineInfo] = []
    for line in lines:
        line_box = _union_box([block.box for block in line])
        column = _line_column(line, line_box, two_column_layout=two_column_layout)
        is_display = _is_display_formula_line(line, image_size=image_size)
        role = _line_role(line, line_box, image_size=image_size)
        base_infos.append(
            _LineInfo(
                blocks=line,
                box=line_box,
                column=column,
                role=role,
                paragraph_id=None,
                is_display=is_display,
            )
        )
    paragraph_ids = _assign_paragraph_ids(base_infos)
    return tuple(
        replace(info, paragraph_id=paragraph_id)
        for info, paragraph_id in zip(base_infos, paragraph_ids)
    )


def _assign_paragraph_ids(lines: list[_LineInfo]) -> list[int | None]:
    heights = [
        max(1.0, box_to_xyxy(info.box)[3] - box_to_xyxy(info.box)[1])
        for info in lines
        if info.role == "paragraph"
    ]
    median_height = float(np.median(heights)) if heights else 16.0
    paragraph_ids: list[int | None] = []
    current_id = -1
    previous: _LineInfo | None = None
    for info in lines:
        if info.role in _CONTENT_NOISE_ROLES:
            paragraph_ids.append(None)
            previous = None
            continue
        if info.role != "paragraph":
            current_id += 1
            paragraph_ids.append(current_id)
            previous = None
            continue
        if previous is None or not _should_merge_line_into_paragraph(
            previous,
            info,
            median_height=median_height,
        ):
            current_id += 1
        paragraph_ids.append(current_id)
        previous = info
    return paragraph_ids


def _should_merge_line_into_paragraph(
    previous: _LineInfo,
    current: _LineInfo,
    *,
    median_height: float,
) -> bool:
    if previous.role != "paragraph" or current.role != "paragraph":
        return False
    if previous.column != current.column:
        return False
    px1, _py1, _px2, py2 = box_to_xyxy(previous.box)
    cx1, cy1, _cx2, _cy2 = box_to_xyxy(current.box)
    vertical_gap = cy1 - py2
    if vertical_gap < 0 or vertical_gap > median_height * 1.8:
        return False
    if abs(px1 - cx1) > median_height * 2.2 and not _line_text(previous.blocks).rstrip().endswith("-"):
        return False
    text = _line_text(previous.blocks).strip()
    current_text = _line_text(current.blocks).strip()
    if _BLOCK_LEAD_RE.match(current_text):
        return False
    return text.endswith("-") or not _TERMINAL_RE.search(text)


def _union_box(boxes: list[Box4P]) -> Box4P:
    x1 = min(box_to_xyxy(box)[0] for box in boxes)
    y1 = min(box_to_xyxy(box)[1] for box in boxes)
    x2 = max(box_to_xyxy(box)[2] for box in boxes)
    y2 = max(box_to_xyxy(box)[3] for box in boxes)
    return xyxy_to_box(x1, y1, x2, y2)


def _box_x1_x2(box: Box4P) -> tuple[float, float]:
    x1, _y1, x2, _y2 = box_to_xyxy(box)
    return x1, x2


def _is_two_column_layout(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    if not blocks:
        return False
    page_width = float((image_size or blocks[0].image_size or (0, 0))[0])
    if page_width <= 0:
        return False
    candidates = [
        block
        for block in blocks
        if block.role not in _CONTENT_NOISE_ROLES
        and block.kind == "text"
        and block.text.strip()
    ]
    if len(candidates) < 3:
        display_blocks = [block for block in blocks if _is_display_formula_like(block)]
        display_left = 0
        display_right = 0
        for block in display_blocks:
            x1, _y1, x2, _y2 = box_to_xyxy(block.box)
            width = x2 - x1
            center = (x1 + x2) / 2.0
            if width >= page_width * 0.62 or _crosses_page_midline(x1, x2, page_width):
                continue
            if center < page_width * 0.46:
                display_left += 1
            elif center > page_width * 0.54:
                display_right += 1
        return display_left >= 1 and display_right >= 1
    wide_count = 0
    left_count = 0
    right_count = 0
    for block in candidates:
        x1, _y1, x2, _y2 = box_to_xyxy(block.box)
        width = x2 - x1
        center = (x1 + x2) / 2.0
        if width >= page_width * 0.62 or _crosses_page_midline(x1, x2, page_width):
            wide_count += 1
        elif center < page_width * 0.46:
            left_count += 1
        elif center > page_width * 0.54:
            right_count += 1
    if wide_count >= max(2, int(len(candidates) * 0.22)):
        return False
    has_center_display = any(
        _is_display_formula_like(block)
        and _crosses_page_midline(*_box_x1_x2(block.box), page_width)
        for block in blocks
    )
    if len(candidates) < 6:
        if has_center_display and left_count >= 2 and right_count >= 1 and wide_count == 0:
            return True
        return left_count >= 2 and right_count >= 2 and wide_count == 0
    return left_count >= 3 and right_count >= 3


def _block_sort_key(
    block: MathCraftBlock,
    two_column_layout: bool,
) -> tuple[float, float, float, float]:
    x1, y1, _x2, _y2 = box_to_xyxy(block.box)
    page = block.page_index if block.page_index is not None else 0
    column = _block_column(block) if two_column_layout else 0
    return float(page), float(column), y1, x1


def _line_sort_key(
    line: list[MathCraftBlock],
    two_column_layout: bool,
) -> tuple[float, float, float, float]:
    first = line[0]
    x1, y1, _x2, _y2 = box_to_xyxy(_union_box([item.box for item in line]))
    page = first.page_index if first.page_index is not None else 0
    column = _block_column(first) if two_column_layout else 0
    return float(page), float(column), y1, x1


def _same_layout_region(
    first: MathCraftBlock,
    second: MathCraftBlock,
    line_box: Box4P,
    *,
    two_column_layout: bool,
) -> bool:
    if (first.page_index or 0) != (second.page_index or 0):
        return False
    if not two_column_layout:
        if _is_display_formula_like(first) or _is_display_formula_like(second):
            return False
        return True
    if _block_column(first) == _block_column(second):
        return True
    if _is_inline_formula_like(first) or _is_inline_formula_like(second):
        size = first.image_size or second.image_size
        if not size or size[0] <= 0:
            return False
        lx1, _ly1, lx2, _ly2 = box_to_xyxy(line_box)
        sx1, _sy1, sx2, _sy2 = box_to_xyxy(second.box)
        gap = max(0.0, max(lx1, sx1) - min(lx2, sx2))
        return y_overlap_ratio(line_box, second.box) >= 0.45 and gap <= float(size[0]) * 0.08
    if _is_display_formula_like(first) or _is_display_formula_like(second):
        return False
    size = first.image_size or second.image_size
    if size and size[0] > 0:
        lx1, _ly1, lx2, _ly2 = box_to_xyxy(line_box)
        sx1, _sy1, sx2, _sy2 = box_to_xyxy(second.box)
        gap = max(0.0, max(lx1, sx1) - min(lx2, sx2))
        return y_overlap_ratio(line_box, second.box) >= 0.75 and gap <= float(size[0]) * 0.015
    return False


def _block_column(block: MathCraftBlock) -> int:
    size = block.image_size
    if not size or size[0] <= 0:
        return 0
    page_width = float(size[0])
    x1, _y1, x2, _y2 = box_to_xyxy(block.box)
    width = x2 - x1
    midline = page_width * 0.5
    if x1 >= midline:
        return 1
    if x2 <= midline:
        return 0
    if width >= page_width * 0.7 or _crosses_page_midline(x1, x2, page_width):
        return 0
    center_x = (x1 + x2) / 2.0
    return 1 if center_x >= midline else 0


def _is_inline_formula_like(block: MathCraftBlock) -> bool:
    return block.kind in {"embedding", "formula", "inline_formula"} and block.kind not in {
        "isolated",
        "display_formula",
    }


def _is_display_formula_like(block: MathCraftBlock) -> bool:
    return block.kind in {"isolated", "display_formula"} or (
        block.source == "formula_rec" and block.kind not in {"embedding", "inline_formula"}
    )


def _crosses_page_midline(x1: float, x2: float, page_width: float) -> bool:
    return x1 <= page_width * 0.45 and x2 >= page_width * 0.55


def _line_column(
    line: tuple[MathCraftBlock, ...],
    line_box: Box4P,
    *,
    two_column_layout: bool,
) -> int:
    if not line:
        return 0
    if not two_column_layout:
        return 0
    size = line[0].image_size
    if not size or size[0] <= 0:
        return _block_column(line[0])
    page_width = float(size[0])
    x1, _y1, x2, _y2 = box_to_xyxy(line_box)
    width = x2 - x1
    midline = page_width * 0.5
    if x1 >= midline:
        return 1
    if x2 <= midline:
        return 0
    if width >= page_width * 0.7 or _crosses_page_midline(x1, x2, page_width):
        return 0
    centers = [
        (box_to_xyxy(block.box)[0] + box_to_xyxy(block.box)[2]) / 2.0
        for block in line
    ]
    return 1 if float(np.median(centers)) >= midline else 0


def _is_display_formula_line(
    line: tuple[MathCraftBlock, ...],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    if not line:
        return False
    if any(block.is_display is True for block in line):
        return all(
            block.is_display is True
            or block.kind in {"isolated", "display_formula"}
            or block.role in {"formula_anchor", "formula_label"}
            for block in line
        )
    formula_blocks = [
        block
        for block in line
        if block.kind in {"formula", "isolated", "display_formula"}
        or block.source == "formula_rec"
    ]
    non_formula_blocks = [
        block
        for block in line
        if block not in formula_blocks and block.role not in {"formula_anchor", "formula_label"}
    ]
    if len(formula_blocks) == 1 and not non_formula_blocks:
        return _is_display_formula_block(formula_blocks[0], (formula_blocks[0],), image_size=image_size)
    if len(line) > 1:
        return False
    return _is_display_formula_block(line[0], line, image_size=image_size)


def _line_role(
    line: tuple[MathCraftBlock, ...],
    line_box: Box4P,
    *,
    image_size: tuple[int, int] | None,
) -> str:
    text = _line_text(line).strip()
    if not text:
        return "paragraph"
    if all(block.role == "formula_anchor" for block in line):
        return "formula_anchor"
    if all(block.role == "formula_label" for block in line):
        return "formula_label"
    if _is_display_formula_line(line, image_size=image_size):
        return "formula"
    if _is_margin_page_number(text, line_box, image_size=image_size):
        return "page_number"
    margin_role = _margin_role(text, line_box, image_size=image_size)
    if margin_role:
        return margin_role
    if _is_heading_text(text):
        return "heading"
    if _is_list_text(text):
        return "list"
    if any(block.kind in {"formula", "embedding", "inline_formula"} for block in line):
        return "paragraph"
    return "paragraph"


def _block_role(block: MathCraftBlock, line_info: _LineInfo) -> str:
    if block.role in {"formula_anchor", "formula_label"}:
        return block.role
    if line_info.role in _CONTENT_NOISE_ROLES:
        return line_info.role
    if block.kind in {"isolated", "display_formula"} or line_info.is_display:
        return "formula"
    if block.kind in {"formula", "embedding", "inline_formula"}:
        return "formula"
    return line_info.role or "paragraph"


def _line_confidence_flags(
    line_info: _LineInfo,
    *,
    image_size: tuple[int, int] | None,
) -> tuple[str, ...]:
    flags: set[str] = set()
    if line_info.is_display:
        flags.add("display_formula")
    if line_info.role in _CONTENT_NOISE_ROLES:
        flags.add(line_info.role)
    if image_size and image_size[1] > 0:
        _x1, y1, _x2, y2 = box_to_xyxy(line_info.box)
        center_y = (y1 + y2) / 2.0
        if center_y < float(image_size[1]) * 0.08:
            flags.add("top_margin")
        elif center_y > float(image_size[1]) * 0.92:
            flags.add("bottom_margin")
    return tuple(sorted(flags))


def _line_text(line: tuple[MathCraftBlock, ...] | list[MathCraftBlock]) -> str:
    return _smart_join([block.text.strip() for block in line if block.text.strip()]).strip()


def _is_margin_page_number(
    text: str,
    line_box: Box4P,
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    if not _PAGE_NUMBER_RE.match(text.strip()):
        return False
    if not image_size or image_size[1] <= 0:
        return True
    _x1, y1, _x2, y2 = box_to_xyxy(line_box)
    center_y = (y1 + y2) / 2.0
    return center_y < float(image_size[1]) * 0.12 or center_y > float(image_size[1]) * 0.88


def _margin_role(
    text: str,
    line_box: Box4P,
    *,
    image_size: tuple[int, int] | None,
) -> str:
    if not image_size or image_size[1] <= 0:
        return ""
    _x1, y1, _x2, y2 = box_to_xyxy(line_box)
    center_y = (y1 + y2) / 2.0
    top = center_y < float(image_size[1]) * 0.08
    bottom = center_y > float(image_size[1]) * 0.92
    if not (top or bottom):
        return ""
    line = text.strip()
    if _RUNNING_HEADER_RE.match(line) or _JOURNAL_RUNNING_HEADER_RE.match(line):
        return "header" if top else "footer"
    if top and len(line) <= 96 and ":" in line and _looks_like_running_header_fragment(line):
        return "header"
    if len(line) <= 80 and (line.isupper() or re.match(r"^CHAPTER\s+\d+", line, flags=re.IGNORECASE)):
        return "header" if top else "footer"
    return ""


def _is_heading_text(text: str) -> bool:
    line = text.strip()
    if len(line) > 100 or line.endswith((".", ",", ";", ":")):
        return False
    return bool(
        _SECTION_HEADING_RE.match(line)
        or _COMPACT_SECTION_HEADING_RE.match(line)
        or _CHINESE_SECTION_HEADING_RE.match(line)
        or _UNNUMBERED_HEADING_RE.match(line)
    )


def _is_list_text(text: str) -> bool:
    return text.strip().startswith(("-", "*", "•", "·", "鈥?", "路", "銉?"))


def _looks_like_running_header_fragment(text: str) -> bool:
    line = re.sub(r"\s+", " ", text.strip())
    if not line or len(line) > 96:
        return False
    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / max(1, len(letters))
    return uppercase_ratio >= 0.55 or bool(re.search(r"\bet\s+al\.", line, flags=re.IGNORECASE))


def _is_display_formula_block(
    block: MathCraftBlock,
    line: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    if block.kind == "isolated":
        return True
    if _DISPLAY_MATH_TEXT_RE.search(block.text or ""):
        return True
    if block.kind not in {"formula", "display_formula"}:
        return False
    if len(line) > 1:
        return False
    if not image_size or image_size[0] <= 0:
        return True
    x1, _y1, x2, _y2 = box_to_xyxy(block.box)
    return (x2 - x1) >= float(image_size[0]) * 0.35


def _is_formula_anchor_text(text: str) -> bool:
    return bool(_FORMULA_ANCHOR_RE.match(text.strip()))


def _is_formula_label_text(text: str) -> bool:
    return bool(_FORMULA_LABEL_RE.match(text.strip()))


def _is_formula_adjacent(
    block: MathCraftBlock,
    formula_blocks: tuple[MathCraftBlock, ...],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    bx1, by1, bx2, by2 = box_to_xyxy(block.box)
    block_height = max(1.0, by2 - by1)
    block_center_x = (bx1 + bx2) / 2.0
    page_width = float(image_size[0]) if image_size and image_size[0] > 0 else 0.0
    for formula in formula_blocks:
        fx1, fy1, fx2, fy2 = box_to_xyxy(formula.box)
        vertical_gap = max(0.0, max(fy1 - by2, by1 - fy2))
        overlaps_y = y_overlap_ratio(block.box, formula.box) >= 0.15
        overlaps_x = max(0.0, min(bx2, fx2) - max(bx1, fx1)) >= min(bx2 - bx1, fx2 - fx1) * 0.1
        center_close = page_width > 0 and abs(block_center_x - ((fx1 + fx2) / 2.0)) <= page_width * 0.16
        horizontal_gap = min(abs(bx2 - fx1), abs(fx2 - bx1))
        beside_formula = page_width > 0 and horizontal_gap <= page_width * 0.06
        if vertical_gap <= block_height * 2.2 and (overlaps_x or center_close or beside_formula):
            return True
        if overlaps_y and (overlaps_x or beside_formula):
            return True
    return False


def _is_text_swallowed_by_formula(
    block: MathCraftBlock,
    formula_blocks: tuple[MathCraftBlock, ...],
) -> bool:
    text = block.text.strip()
    if not text:
        return True
    if _is_formula_anchor_text(text) or _is_formula_label_text(text):
        return False
    for formula in formula_blocks:
        if overlap_ratio(block.box, formula.box, denominator="first") >= 0.82:
            return True
    return False


def _smart_join(parts: list[str]) -> str:
    result = ""
    for part in (item for item in parts if item):
        if not result:
            result = part
            continue
        if result.endswith((" ", "\n")) or part.startswith((" ", "\n", "$")):
            result += part
        else:
            result += " " + part
    return result


def _collapse_line_separators(text: str, *, line_sep: str) -> str:
    while line_sep * 3 in text:
        text = text.replace(line_sep * 3, line_sep * 2)
    return text

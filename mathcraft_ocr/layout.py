# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .results import Box4P, MathCraftBlock


@dataclass(frozen=True)
class TextSegment:
    box: Box4P


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


def group_blocks_into_lines(
    blocks: tuple[MathCraftBlock, ...] | list[MathCraftBlock],
    *,
    y_overlap_threshold: float = 0.45,
) -> tuple[tuple[MathCraftBlock, ...], ...]:
    sorted_blocks = sorted(blocks, key=_block_sort_key)
    lines: list[list[MathCraftBlock]] = []
    for block in sorted_blocks:
        best_line: list[MathCraftBlock] | None = None
        best_overlap = 0.0
        for line in lines:
            line_box = _union_box([item.box for item in line])
            overlap = y_overlap_ratio(line_box, block.box)
            if overlap > best_overlap:
                best_overlap = overlap
                best_line = line
        if best_line is None or best_overlap < y_overlap_threshold:
            lines.append([block])
        else:
            best_line.append(block)
    return tuple(tuple(sorted(line, key=lambda item: box_to_xyxy(item.box)[0])) for line in lines)


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
        parts: list[str] = []
        has_isolated = False
        for block in line:
            text = block.text.strip()
            if not text:
                continue
            if block.kind == "isolated":
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


def _union_box(boxes: list[Box4P]) -> Box4P:
    x1 = min(box_to_xyxy(box)[0] for box in boxes)
    y1 = min(box_to_xyxy(box)[1] for box in boxes)
    x2 = max(box_to_xyxy(box)[2] for box in boxes)
    y2 = max(box_to_xyxy(box)[3] for box in boxes)
    return xyxy_to_box(x1, y1, x2, y2)


def _block_sort_key(block: MathCraftBlock) -> tuple[float, float]:
    x1, y1, _x2, _y2 = box_to_xyxy(block.box)
    return y1, x1


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

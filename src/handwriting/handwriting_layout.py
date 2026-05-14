# coding: utf-8
"""
Layout analysis module: handwriting strokes -> typeset article.

Leverages precise stroke coordinates (instead of OCR boxes inferred from pixels) to:
1. Spatial clustering -> line grouping
2. Line-spacing analysis -> paragraph segmentation
3. Line feature analysis -> heading/list/body classification
4. Merge recognition results -> formatted plain-text article
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List

from PyQt6.QtCore import QPointF, QRectF

from .types import InkStroke


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class StrokeLine:
    """Intermediate representation of one line of strokes."""
    strokes: List[InkStroke] = field(default_factory=list)
    box: QRectF = field(default_factory=QRectF)
    role: str = "paragraph"           # paragraph | heading | list | formula | noise
    is_display_formula: bool = False
    indent_ratio: float = 0.0         # ratio of first character's X offset to line width


@dataclass
class HandwritingArticle:
    """Result of the typeset article."""
    plain_text: str = ""
    lines: List[StrokeLine] = field(default_factory=list)
    paragraph_count: int = 0
    heading_count: int = 0


# ---------------------------------------------------------------------------
# Step 1: Line grouping
# ---------------------------------------------------------------------------


def group_strokes_into_lines(
    strokes: list[InkStroke],
    *,
    image_height: float | None = None,
    y_gap_ratio: float = 0.8,
    min_line_strokes: int = 1,
) -> list[StrokeLine]:
    """
    Cluster strokes into lines by Y-overlap / Y-gap of their bounding boxes.

    Parameters
    ----------
    y_gap_ratio:
        Line-gap threshold. Two strokes start a new line when their Y gap
        exceeds this ratio * median line height.
    image_height:
        Canvas / image height, used to estimate median line height.
        When None, inferred automatically from stroke sizes.
    """
    if not strokes:
        return []

    # Sort by Y coordinate
    sorted_strokes = sorted(strokes, key=_stroke_y_center)

    # Estimate median line height
    heights = [_stroke_height(s) for s in sorted_strokes if _stroke_height(s) > 0]
    median_height = _safe_median(heights) if heights else 24.0
    if image_height and image_height > 0:
        median_height = max(median_height, image_height * 0.008)

    gap_threshold = median_height * y_gap_ratio

    # Greedy clustering: if stroke Y-overlaps current line enough -> merge, else start new line
    lines: list[list[InkStroke]] = []
    for stroke in sorted_strokes:
        added = False
        for line in lines:
            line_top, line_bottom = _line_y_range(line)
            s_top, s_bottom = _stroke_y_range(stroke)
            # Y overlap exceeds threshold -> same line
            overlap = max(0.0, min(line_bottom, s_bottom) - max(line_top, s_top))
            s_height = s_bottom - s_top
            if s_height > 0 and overlap >= s_height * 0.35:
                line.append(stroke)
                added = True
                break
            # Or the gap is within threshold
            gap = max(0.0, max(line_top, s_top) - min(line_bottom, s_bottom))
            if gap <= gap_threshold:
                line.append(stroke)
                added = True
                break
        if not added:
            lines.append([stroke])

    # Drop "lines" with too few strokes
    filtered = [line for line in lines if len(line) >= min_line_strokes]

    return [_build_stroke_line(line, image_height=image_height) for line in filtered]


# ---------------------------------------------------------------------------
# Step 2: Paragraph segmentation
# ---------------------------------------------------------------------------


def detect_paragraphs_from_lines(
    lines: list[StrokeLine],
    *,
    spacing_multiplier: float = 1.6,
    indent_ratio_threshold: float = 0.04,
) -> list[StrokeLine]:
    """
    Detect paragraph boundaries from line spacing and indentation.

    Conditions that signal a paragraph boundary:
    - Large gap between lines
    - First-line indentation
    - Short lines (headings / list items)
    """
    if not lines:
        return lines

    # Compute Y gaps between consecutive lines
    spacings: list[float] = []
    for i in range(1, len(lines)):
        gap = _line_y_gap(lines[i - 1], lines[i])
        if gap > 0:
            spacings.append(gap)

    median_spacing = _safe_median(spacings) if spacings else 24.0
    if median_spacing <= 0:
        median_spacing = 24.0

    paragraph_boundary_threshold = median_spacing * spacing_multiplier

    for i, line in enumerate(lines):
        if i == 0:
            continue  # The first line always starts a paragraph
        prev = lines[i - 1]
        gap = _line_y_gap(prev, line)

        is_new_paragraph = (
            gap > paragraph_boundary_threshold
            or (line.indent_ratio >= indent_ratio_threshold and prev.role == "paragraph")
            or prev.role != line.role  # role change -> new block
        )

        if is_new_paragraph:
            # Marking paragraph boundaries via role is not ideal here;
            # handled in a separate pass instead.
            pass

    return lines


def split_into_paragraphs(lines: list[StrokeLine]) -> list[list[StrokeLine]]:
    """
    Split a list of lines into a list of paragraphs.
    Each paragraph is a group of consecutive lines.
    """
    if not lines:
        return []

    # Compute spacing threshold
    spacings: list[float] = []
    for i in range(1, len(lines)):
        gap = _line_y_gap(lines[i - 1], lines[i])
        spacings.append(gap)
    median_spacing = _safe_median(spacings) if spacings else 24.0
    threshold = max(median_spacing * 1.6, 8.0)

    paragraphs: list[list[StrokeLine]] = []
    current: list[StrokeLine] = [lines[0]]

    for i in range(1, len(lines)):
        prev = lines[i - 1]
        curr = lines[i]
        gap = _line_y_gap(prev, curr)

        # Paragraph-boundary conditions
        is_break = (
            gap > threshold
            or (curr.role != prev.role and curr.role in {"heading", "list", "formula"})
            or prev.role in {"heading", "list", "formula"}
            or (curr.indent_ratio >= 0.03 and prev.role == "paragraph" and curr.role == "paragraph")
        )

        if is_break:
            paragraphs.append(current)
            current = [curr]
        else:
            current.append(curr)

    if current:
        paragraphs.append(current)

    return paragraphs


# ---------------------------------------------------------------------------
# Step 3: Line role classification
# ---------------------------------------------------------------------------


def classify_line_roles(
    lines: list[StrokeLine],
    *,
    image_width: float | None = None,
) -> list[StrokeLine]:
    """
    Classify each line's role from its geometry: heading / list / formula / paragraph / noise.
    """
    if not lines:
        return lines

    heights = [max(1.0, _line_height(l)) for l in lines]
    widths = [max(1.0, _line_width(l)) for l in lines]
    median_height = _safe_median(heights) if heights else 24.0
    image_w = image_width or max(widths)

    for line in lines:
        h = _line_height(line)
        w = _line_width(line)

        # Very small lines -> noise
        if h <= 3.0 or w <= 4.0:
            line.role = "noise"
            continue

        # Significantly taller than median -> likely a heading
        if h >= median_height * 1.35 and w <= image_w * 0.75:
            line.role = "heading"
            continue

        # List-item detection: first-line indent + short line (or starts with -/*)
        # (Geometry-only judgment here; content checks happen in the merge stage)
        if line.indent_ratio >= 0.05:
            # Short indented line -> likely a list item
            if w <= image_w * 0.6 and h <= median_height * 1.15:
                line.role = "list"
                continue

        # Default to body text
        line.role = "paragraph"

    return lines


# ---------------------------------------------------------------------------
# Step 4: Format output
# ---------------------------------------------------------------------------


def strokes_to_article_text(
    strokes: list[InkStroke],
    recognition_results: list[str],
    *,
    image_width: float | None = None,
    image_height: float | None = None,
) -> HandwritingArticle:
    """
    End-to-end: strokes + per-line recognition results -> typeset article.

    Parameters
    ----------
    strokes:
        All strokes on the canvas.
    recognition_results:
        Recognized text per line (order must match the output of
        group_strokes_into_lines).
    image_width / image_height:
        Canvas size in logical coordinates, used for layout analysis.

    Returns
    -------
    HandwritingArticle containing the formatted plain text plus intermediate analysis.
    """
    if not strokes or not recognition_results:
        return HandwritingArticle()

    # Step 1: Group strokes into lines
    lines = group_strokes_into_lines(strokes, image_height=image_height)

    # Align recognition results (take the shorter)
    n = min(len(lines), len(recognition_results))
    lines = lines[:n]

    # Step 2: Classify line roles
    lines = classify_line_roles(lines, image_width=image_width)

    # Step 3: Split into paragraphs
    paragraphs = split_into_paragraphs(lines)

    # Step 4: Format plain text
    article_parts: list[str] = []
    for para_lines in paragraphs:
        para_text = _format_paragraph(para_lines, recognition_results, lines)
        if para_text.strip():
            article_parts.append(para_text)

    result = HandwritingArticle(
        plain_text="\n\n".join(article_parts),
        lines=lines,
        paragraph_count=len(paragraphs),
        heading_count=sum(1 for l in lines if l.role == "heading"),
    )
    return result


def lines_to_article_text(
    lines: list[StrokeLine],
    line_texts: list[str],
) -> str:
    """
    Simplified entry point: pre-grouped lines + line texts -> formatted article.
    Useful when you already have line groupings or a custom grouping strategy.
    """
    if not lines or not line_texts:
        return ""

    n = min(len(lines), len(line_texts))
    lines = lines[:n]
    line_texts = line_texts[:n]

    paragraphs = split_into_paragraphs(lines)

    # Build line -> text mapping
    text_map: dict[int, str] = {}
    # Flatten all paragraphs and find each line's index in the original list
    all_lines_flat: list[StrokeLine] = []
    for para in paragraphs:
        all_lines_flat.extend(para)
    for i, line in enumerate(all_lines_flat):
        # Look up the line's index in the original lines list
        try:
            idx = lines.index(line)
            if idx < len(line_texts):
                text_map[i] = line_texts[idx]
        except ValueError:
            pass

    article_parts: list[str] = []
    for para in paragraphs:
        para_text = _format_paragraph(para, line_texts, lines)
        if para_text.strip():
            article_parts.append(para_text)

    return "\n\n".join(article_parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_stroke_line(
    strokes: list[InkStroke],
    image_height: float | None = None,
) -> StrokeLine:
    """Build a StrokeLine from a group of strokes."""
    if not strokes:
        return StrokeLine()

    boxes = [s.bounding_rect() for s in strokes if not s.bounding_rect().isEmpty()]
    if not boxes:
        return StrokeLine(strokes=list(strokes))

    # Union bounding box
    x1 = min(b.left() for b in boxes)
    y1 = min(b.top() for b in boxes)
    x2 = max(b.right() for b in boxes)
    y2 = max(b.bottom() for b in boxes)
    line_box = QRectF(x1, y1, x2 - x1, y2 - y1)

    # Strokes sorted by X
    sorted_by_x = sorted(strokes, key=lambda s: s.bounding_rect().left())

    # First-character indentation
    if sorted_by_x:
        first_left = sorted_by_x[0].bounding_rect().left()
    else:
        first_left = x1
    line_width = x2 - x1
    indent = (first_left - x1) / max(1.0, line_width) if line_width > 0 else 0.0

    return StrokeLine(
        strokes=list(strokes),
        box=line_box,
        indent_ratio=max(0.0, indent),
    )


def _stroke_y_center(stroke: InkStroke) -> float:
    r = stroke.bounding_rect()
    if r.isEmpty():
        return 0.0
    return r.center().y()


def _stroke_height(stroke: InkStroke) -> float:
    r = stroke.bounding_rect()
    if r.isEmpty():
        return 0.0
    return r.height()


def _stroke_y_range(stroke: InkStroke) -> tuple[float, float]:
    r = stroke.bounding_rect()
    if r.isEmpty():
        return (0.0, 0.0)
    return (r.top(), r.bottom())


def _line_y_range(line: list[InkStroke]) -> tuple[float, float]:
    if not line:
        return (0.0, 0.0)
    top = min(s.bounding_rect().top() for s in line)
    bottom = max(s.bounding_rect().bottom() for s in line)
    return (top, bottom)


def _line_y_gap(prev: StrokeLine, curr: StrokeLine) -> float:
    """Y gap between two lines (bottom of prev to top of curr)."""
    return max(0.0, curr.box.top() - prev.box.bottom())


def _line_height(line: StrokeLine) -> float:
    return max(0.0, line.box.height())


def _line_width(line: StrokeLine) -> float:
    return max(0.0, line.box.width())


def _safe_median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return sorted_vals[n // 2]
    return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0


def _format_paragraph(
    para_lines: list[StrokeLine],
    all_texts: list[str],
    all_lines: list[StrokeLine],
) -> str:
    """Format the lines of a single paragraph into text."""
    parts: list[str] = []
    for line in para_lines:
        # Find this line's index in all_lines
        try:
            idx = all_lines.index(line)
        except ValueError:
            continue
        if idx >= len(all_texts):
            continue
        text = all_texts[idx].strip()
        if not text:
            continue

        if line.role == "heading":
            parts.append(text)
            parts.append("")  # blank line after heading
        elif line.role == "list":
            # Auto-add list marker if the text does not already have one
            if not _has_list_prefix(text):
                parts.append(f"- {text}")
            else:
                parts.append(text)
        elif line.role == "formula" or line.is_display_formula:
            parts.append("")
            parts.append(text)
            parts.append("")
        else:
            parts.append(text)

    # Merge lines within the paragraph
    result_lines: list[str] = []
    for part in parts:
        result_lines.append(part)

    merged = _join_paragraph_lines(result_lines)
    return merged.strip()


def _join_paragraph_lines(lines: list[str]) -> str:
    """
    Intelligently join lines within a paragraph.
    - Blank lines are preserved
    - List items are preserved
    - Headings are preserved
    - Body text lines are joined with spaces
    """
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue
        if _has_list_prefix(stripped) or _looks_like_heading(stripped):
            if result and result[-1] != "":
                result.append("")
            result.append(stripped)
        else:
            if result and result[-1] and not result[-1].endswith((".", "。", "!", "！", "?", "？")):
                result[-1] = result[-1] + " " + stripped
            else:
                result.append(stripped)
    return "\n".join(result)


def _has_list_prefix(text: str) -> bool:
    """Check whether the text starts with a list marker."""
    stripped = text.strip()
    return any(
        stripped.startswith(p)
        for p in ("- ", "* ", "• ", "· ", "1.", "2.", "3.", "4.", "5.", "a)", "b)", "c)", "A)", "B)", "C)")
    )


def _looks_like_heading(text: str) -> bool:
    """Heuristic: does the text look like a heading (short, no trailing punctuation)?"""
    stripped = text.strip()
    if len(stripped) > 60:
        return False
    if stripped.endswith((".", ",", ";", ":", "。", "，", "；", "：", "!", "！", "?", "？")):
        return False
    # Numbered section heading (e.g. "1. Introduction")
    import re
    if re.match(r"^\d+(?:\.\d+)*\s", stripped):
        return True
    return False

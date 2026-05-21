# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
import re

import numpy as np


@dataclass(frozen=True)
class FormulaLineCrop:
    image: np.ndarray
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class FormulaLineGroup:
    crops: tuple[FormulaLineCrop, ...]


_BEGIN_END_RE = re.compile(r"\\(?:begin|end)\s*\{[^{}]+\}(?:\s*\{[^{}]*\})?")
_LEFT_RIGHT_TOKEN_RE = re.compile(r"\\(left|right)(?![A-Za-z])")
_INVISIBLE_LEFT_RIGHT_RE = re.compile(r"\\(?:left|right)(?![A-Za-z])\s*\.")
_LEFT_RIGHT_PREFIX_RE = re.compile(r"\\(?:left|right)(?![A-Za-z])\s*")
_ROW_BREAK_RE = re.compile(r"(?<!\\)(?:\\\\)+")
_WIDE_LINE_ASPECT_RATIO = 7.0


def split_formula_line_crops(image_rgb: np.ndarray) -> tuple[FormulaLineCrop, ...]:
    rgb = _as_rgb_array(image_rgb)
    return _split_formula_rows(rgb)


def split_formula_line_groups(image_rgb: np.ndarray) -> tuple[FormulaLineGroup, ...]:
    rgb = _as_rgb_array(image_rgb)
    rows = _split_formula_rows(rgb)
    if not rows:
        full_crop = FormulaLineCrop(
            image=rgb.copy(),
            box=(0, 0, int(rgb.shape[1]), int(rgb.shape[0])),
        )
        segments = _split_wide_line_segments(full_crop)
        return (FormulaLineGroup(crops=segments),) if len(segments) > 1 else ()
    return tuple(FormulaLineGroup(crops=_split_wide_line_segments(row)) for row in rows)


def compose_aligned_formula(lines: list[str] | tuple[str, ...]) -> str:
    cleaned = [_clean_formula_line(line) for line in lines]
    cleaned = [line for line in cleaned if line]
    if len(cleaned) <= 1:
        return cleaned[0] if cleaned else ""
    body = " \\\\\n".join(cleaned)
    return "\\begin{aligned}\n" + body + "\n\\end{aligned}"


def compose_formula_line(segments: list[str] | tuple[str, ...]) -> str:
    cleaned = [_strip_formula_wrappers(segment) for segment in segments]
    line = " ".join(segment for segment in cleaned if segment).strip()
    return _make_tex_groups_render_safe(
        _make_alignment_tabs_render_safe(
            _make_double_scripts_render_safe(_make_left_right_render_safe(line))
        )
    )


def _split_formula_rows(rgb: np.ndarray) -> tuple[FormulaLineCrop, ...]:
    height, width = rgb.shape[:2]
    if height < 72 or width < 24:
        return ()

    mask = _ink_mask(rgb)
    row_counts = mask.sum(axis=1)
    row_threshold = max(3, int(round(width * 0.006)))
    row_has_ink = row_counts >= row_threshold
    bands = _row_bands(row_has_ink)
    bands = _merge_close_bands(bands, max_gap=max(3, min(14, int(round(height * 0.018)))))
    bands = [
        (top, bottom)
        for top, bottom in bands
        if _band_looks_like_formula_row(mask, top, bottom, image_width=width)
    ]
    bands = _filter_annotation_bands(mask, bands, image_width=width)
    if len(bands) < 2:
        return ()

    return tuple(
        crop
        for crop in (_crop_line(rgb, mask, top, bottom) for top, bottom in bands)
        if crop is not None
    )


def _as_rgb_array(image_rgb: np.ndarray) -> np.ndarray:
    array = np.asarray(image_rgb)
    if array.ndim == 2:
        return np.stack([array, array, array], axis=-1).astype(np.uint8, copy=False)
    if array.ndim == 3 and array.shape[2] >= 3:
        return array[:, :, :3].astype(np.uint8, copy=False)
    raise ValueError(f"unsupported formula image shape: {array.shape}")


def _ink_mask(rgb: np.ndarray) -> np.ndarray:
    gray = (
        0.299 * rgb[:, :, 0].astype(np.float32)
        + 0.587 * rgb[:, :, 1].astype(np.float32)
        + 0.114 * rgb[:, :, 2].astype(np.float32)
    )
    background = float(np.percentile(gray, 95))
    threshold = min(245.0, max(80.0, background - 28.0))
    mask = gray < threshold

    height, width = mask.shape
    border = max(1, min(height, width) // 80)
    if border:
        mask[:border, :] = False
        mask[-border:, :] = False
        mask[:, :border] = False
        mask[:, -border:] = False
    return mask


def _row_bands(row_has_ink: np.ndarray) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, has_ink in enumerate(row_has_ink.tolist()):
        if has_ink and start is None:
            start = index
        elif not has_ink and start is not None:
            bands.append((start, index - 1))
            start = None
    if start is not None:
        bands.append((start, len(row_has_ink) - 1))
    return bands


def _merge_close_bands(
    bands: list[tuple[int, int]],
    *,
    max_gap: int,
) -> list[tuple[int, int]]:
    if not bands:
        return []
    merged = [bands[0]]
    for top, bottom in bands[1:]:
        prev_top, prev_bottom = merged[-1]
        if top - prev_bottom - 1 <= max_gap:
            merged[-1] = (prev_top, bottom)
        else:
            merged.append((top, bottom))
    return merged


def _band_looks_like_formula_row(
    mask: np.ndarray,
    top: int,
    bottom: int,
    *,
    image_width: int,
) -> bool:
    band = mask[top : bottom + 1, :]
    ink = int(band.sum())
    height = bottom - top + 1
    if height < 5 or ink < max(12, int(round(image_width * 0.02))):
        return False

    active_columns = int(np.count_nonzero(band.any(axis=0)))
    if active_columns < max(28, int(round(image_width * 0.13))):
        return False

    points = np.argwhere(band)
    if points.size == 0:
        return False
    x_span = int(points[:, 1].max() - points[:, 1].min() + 1)
    if x_span >= int(round(image_width * 0.55)):
        return active_columns >= max(28, int(round(image_width * 0.08)))
    return x_span >= int(round(image_width * 0.22))


def _filter_annotation_bands(
    mask: np.ndarray,
    bands: list[tuple[int, int]],
    *,
    image_width: int,
) -> list[tuple[int, int]]:
    if len(bands) < 2:
        return bands
    stats = [(_band_active_columns(mask, top, bottom), top, bottom) for top, bottom in bands]
    max_active = max(active for active, _top, _bottom in stats)
    min_active = max(int(round(image_width * 0.13)), int(round(max_active * 0.35)))
    return [(top, bottom) for active, top, bottom in stats if active >= min_active]


def _band_active_columns(mask: np.ndarray, top: int, bottom: int) -> int:
    return int(np.count_nonzero(mask[top : bottom + 1, :].any(axis=0)))


def _crop_line(
    rgb: np.ndarray,
    mask: np.ndarray,
    top: int,
    bottom: int,
) -> FormulaLineCrop | None:
    height, width = rgb.shape[:2]
    band_mask = mask[top : bottom + 1, :]
    points = np.argwhere(band_mask)
    if points.size == 0:
        return None

    x1 = int(points[:, 1].min())
    x2 = int(points[:, 1].max())
    y_pad = max(5, int(round((bottom - top + 1) * 0.22)))
    x_pad = max(8, int(round(width * 0.015)))
    crop_top = max(0, top - y_pad)
    crop_bottom = min(height, bottom + y_pad + 1)
    crop_left = max(0, x1 - x_pad)
    crop_right = min(width, x2 + x_pad + 1)
    if crop_bottom - crop_top < 8 or crop_right - crop_left < 12:
        return None
    return FormulaLineCrop(
        image=rgb[crop_top:crop_bottom, crop_left:crop_right].copy(),
        box=(crop_left, crop_top, crop_right, crop_bottom),
    )


def _split_wide_line_segments(line: FormulaLineCrop) -> tuple[FormulaLineCrop, ...]:
    height, width = line.image.shape[:2]
    if width < 220 or width / max(1, height) < _WIDE_LINE_ASPECT_RATIO:
        return (line,)

    mask = _ink_mask(line.image)
    column_counts = mask.sum(axis=0)
    column_threshold = max(2, int(round(height * 0.035)))
    column_has_ink = column_counts >= column_threshold
    ink_bands = _row_bands(column_has_ink)
    if len(ink_bands) < 2:
        return (line,)

    min_gap = max(14, int(round(width * 0.025)))
    min_segment_width = max(48, int(round(width * 0.12)))
    split_points: list[int] = []
    for (_left_a, right_a), (left_b, _right_b) in zip(ink_bands, ink_bands[1:]):
        gap = left_b - right_a - 1
        if gap < min_gap:
            continue
        split_at = right_a + 1 + gap // 2
        if split_at < min_segment_width or width - split_at < min_segment_width:
            continue
        if split_points and split_at - split_points[-1] < min_segment_width:
            continue
        split_points.append(split_at)

    if not split_points:
        return (line,)

    segments: list[FormulaLineCrop] = []
    left = 0
    base_left, base_top, _base_right, _base_bottom = line.box
    for right in [*split_points, width]:
        segment = _crop_segment(line.image[:, left:right], left, base_left, base_top)
        if segment is not None:
            segments.append(segment)
        left = right
    return tuple(segments) if len(segments) > 1 else (line,)


def _crop_segment(
    segment_rgb: np.ndarray,
    offset_x: int,
    base_left: int,
    base_top: int,
) -> FormulaLineCrop | None:
    mask = _ink_mask(segment_rgb)
    points = np.argwhere(mask)
    if points.size == 0:
        return None
    height, width = segment_rgb.shape[:2]
    y1 = max(0, int(points[:, 0].min()) - 4)
    y2 = min(height, int(points[:, 0].max()) + 5)
    x1 = max(0, int(points[:, 1].min()) - 6)
    x2 = min(width, int(points[:, 1].max()) + 7)
    if y2 - y1 < 8 or x2 - x1 < 16:
        return None
    return FormulaLineCrop(
        image=segment_rgb[y1:y2, x1:x2].copy(),
        box=(base_left + offset_x + x1, base_top + y1, base_left + offset_x + x2, base_top + y2),
    )


def _clean_formula_line(line: str) -> str:
    return _make_tex_groups_render_safe(
        _make_alignment_tabs_render_safe(
            _make_double_scripts_render_safe(_make_left_right_render_safe(_strip_formula_wrappers(line)))
        )
    )


def _strip_formula_wrappers(line: str) -> str:
    text = str(line or "").strip()
    text = _BEGIN_END_RE.sub("", text).strip()
    return _strip_outer_group(text)


def _make_left_right_render_safe(text: str) -> str:
    if _contains_row_break(text) and _LEFT_RIGHT_TOKEN_RE.search(text):
        text = _INVISIBLE_LEFT_RIGHT_RE.sub("", text)
        return _LEFT_RIGHT_PREFIX_RE.sub("", text).strip()
    if _left_right_tokens_are_balanced(text):
        return text
    text = _INVISIBLE_LEFT_RIGHT_RE.sub("", text)
    return _LEFT_RIGHT_PREFIX_RE.sub("", text).strip()


def _left_right_tokens_are_balanced(text: str) -> bool:
    depth = 0
    for match in _LEFT_RIGHT_TOKEN_RE.finditer(text):
        if match.group(1) == "left":
            depth += 1
            continue
        depth -= 1
        if depth < 0:
            return False
    return depth == 0


def _make_tex_groups_render_safe(text: str) -> str:
    text, missing_closers = _balance_tex_groups(text)
    if missing_closers <= 0:
        return text
    return f"{text}{'}' * missing_closers}"


def _balance_tex_groups(text: str) -> tuple[str, int]:
    depth = 0
    chars: list[str] = []
    for index, char in enumerate(text):
        if char not in "{}" or _is_escaped(text, index):
            chars.append(char)
            continue
        if char == "{":
            depth += 1
            chars.append(char)
        elif depth > 0:
            depth -= 1
            chars.append(char)
    return "".join(chars).strip(), depth


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1


def _make_alignment_tabs_render_safe(text: str) -> str:
    if "&" not in text:
        return text
    parts: list[str] = []
    for index, char in enumerate(text):
        if char == "&" and not _is_escaped(text, index):
            parts.append(r"\quad ")
        else:
            parts.append(char)
    return "".join(parts).strip()


def _contains_row_break(text: str) -> bool:
    return bool(_ROW_BREAK_RE.search(text))


def _make_double_scripts_render_safe(text: str) -> str:
    index = 0
    while index < len(text):
        char = text[index]
        if char not in "^_" or _is_escaped(text, index):
            index += 1
            continue
        atom_start = _find_scripted_atom_start(text, index)
        if atom_start is None:
            index += 1
            continue
        atom = text[atom_start:index]
        if not _atom_has_top_level_script(atom, char):
            index += 1
            continue
        text = f"{text[:atom_start]}{{{atom.rstrip()}}}{text[index:]}"
        index += 2
    return text


def _find_scripted_atom_start(text: str, script_index: int) -> int | None:
    pos = _skip_space_left(text, script_index - 1)
    if pos < 0:
        return None
    while True:
        before_arg = _skip_script_argument_left(text, pos)
        before_arg = _skip_space_left(text, before_arg)
        if before_arg >= 0 and text[before_arg] in "^_" and not _is_escaped(text, before_arg):
            pos = _skip_space_left(text, before_arg - 1)
            if pos < 0:
                return None
            continue
        break
    return _find_base_start_left(text, pos)


def _skip_space_left(text: str, pos: int) -> int:
    while pos >= 0 and text[pos].isspace():
        pos -= 1
    return pos


def _skip_script_argument_left(text: str, pos: int) -> int:
    pos = _skip_space_left(text, pos)
    if pos < 0:
        return pos
    if text[pos] == "}" and not _is_escaped(text, pos):
        start = _find_matching_open_brace(text, pos)
        return start - 1 if start is not None else pos - 1
    if text[pos].isalpha():
        while pos >= 0 and text[pos].isalpha():
            pos -= 1
        if pos >= 0 and text[pos] == "\\":
            pos -= 1
        return pos
    return pos - 1


def _find_base_start_left(text: str, pos: int) -> int | None:
    pos = _skip_space_left(text, pos)
    if pos < 0:
        return None
    if text[pos] == "}" and not _is_escaped(text, pos):
        start = _find_matching_open_brace(text, pos)
        return start if start is not None else pos
    if text[pos].isalpha():
        while pos >= 0 and text[pos].isalpha():
            pos -= 1
        if pos >= 0 and text[pos] == "\\":
            return pos
        return pos + 1
    return pos


def _find_matching_open_brace(text: str, close_index: int) -> int | None:
    depth = 0
    for index in range(close_index, -1, -1):
        char = text[index]
        if char not in "{}" or _is_escaped(text, index):
            continue
        if char == "}":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return index
    return None


def _atom_has_top_level_script(atom: str, script: str) -> bool:
    depth = 0
    for index, char in enumerate(atom):
        if char in "{}" and not _is_escaped(atom, index):
            depth += 1 if char == "{" else -1
            depth = max(depth, 0)
            continue
        if depth == 0 and char == script and not _is_escaped(atom, index):
            return True
    return False


def _strip_outer_group(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == "{" and stripped[-1] == "}" and not _is_escaped(stripped, len(stripped) - 1):
        return stripped[1:-1].strip()
    return stripped

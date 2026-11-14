"""System-font glyph outlines for the MathJax typography adapter.

This is the macOS counterpart of the Windows plugin's GDI+
``SystemFontOutlineService``. It returns the same ``FontRunOutline`` fields:
baseline-relative SVG path data in 1000 units per em with the y axis pointing
up, plus advance, ink height/depth and horizontal ink bounds in em units.

CoreText shapes the whole run (kerning and ligatures included). Fallback is
explicit and ordered: CoreText's own cascade is never used, because each
candidate family must cover the whole run.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any

EM = 1000
REGULAR, BOLD, ITALIC = 0, 1, 2
FALLBACK_FAMILIES = (
    "Times New Roman",
    "PingFang SC",
    "Songti SC",
    "Apple Symbols",
    "Menlo",
)
MAX_RUN_CHARACTERS = 2048


class OutlineError(ValueError):
    pass


class SystemFontOutlines:
    def __init__(self, fallback_families: Iterable[str] = FALLBACK_FAMILIES) -> None:
        self.fallback_families = tuple(fallback_families)
        self._lock = threading.Lock()
        self._families: dict[str, str] | None = None
        self._cache: dict[tuple[str, str, int], dict[str, Any]] = {}

    def families(self) -> list[str]:
        # Names starting with "." are private macOS UI fonts, not user choices.
        return sorted(
            {name for name in self._installed().values() if not name.startswith(".")},
            key=str.casefold,
        )

    def shape_runs(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        """Shape adapter runs, keyed by the adapter's opaque run key."""

        result: dict[str, Any] = {}
        for run in runs:
            key, text, family, style = (
                run.get("key"),
                run.get("text"),
                run.get("family"),
                run.get("style"),
            )
            if (
                not isinstance(key, str)
                or not isinstance(text, str)
                or not isinstance(family, str)
            ):
                raise OutlineError("文字段数据无效。")
            if (
                isinstance(style, bool)
                or not isinstance(style, int)
                or style & ~(BOLD | ITALIC)
            ):
                raise OutlineError("文字段样式无效。")
            result[key] = self.shape(text, family, style)
        return result

    def shape(self, text: str, family: str, style: int) -> dict[str, Any]:
        if len(text) > MAX_RUN_CHARACTERS:
            raise OutlineError("文字段过长。")
        for character in text:
            code = ord(character)
            if code < 32 or 0xD800 <= code <= 0xDFFF or code > 0xFFFF:
                raise OutlineError(
                    "系统字体轮廓暂不支持辅助平面字符或控制字符；请使用受支持的数学字形或显式换行结构。"
                )
        if not family.strip():
            raise OutlineError("字体家族不能为空。")
        cache_key = (text, family.strip(), style)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                cached = self._shape(text, family.strip(), style)
                if len(self._cache) > 4096:
                    self._cache.clear()
                self._cache[cache_key] = cached
            return cached

    def _installed(self) -> dict[str, str]:
        if self._families is None:
            import CoreText

            names = CoreText.CTFontManagerCopyAvailableFontFamilyNames() or []
            self._families = {str(name).casefold(): str(name) for name in names}
        return self._families

    def _shape(self, text: str, requested: str, style: int) -> dict[str, Any]:
        installed = self._installed()
        failures: list[str] = []
        seen: set[str] = set()
        for candidate in (requested, *self.fallback_families):
            if candidate.casefold() in seen:
                continue
            seen.add(candidate.casefold())
            name = installed.get(candidate.casefold())
            if name is None:
                failures.append(f"{candidate}：未安装")
                continue
            font = _font(name, style)
            if font is None:
                failures.append(f"{name}：字形样式不可用")
                continue
            missing = _missing_characters(font, text)
            if missing:
                failures.append(f"{name}：缺少 {' '.join(missing)}")
                continue
            warning = f"{'；'.join(failures)}；已使用 {name}" if failures else None
            return _outline(font, text, requested, name, style, warning)
        raise OutlineError("无法为文字段选择字体：" + "；".join(failures))


def _font(family: str, style: int):
    """The family's face for the style, or None if the family lacks that style."""
    import CoreText

    traits = 0
    if style & BOLD:
        traits |= CoreText.kCTFontBoldTrait
    if style & ITALIC:
        traits |= CoreText.kCTFontItalicTrait
    attributes = {
        CoreText.kCTFontFamilyNameAttribute: family,
        CoreText.kCTFontTraitsAttribute: {CoreText.kCTFontSymbolicTrait: traits},
    }
    descriptor = CoreText.CTFontDescriptorCreateWithAttributes(attributes)
    font = CoreText.CTFontCreateWithFontDescriptor(descriptor, EM, None)
    if (
        font is None
        or str(CoreText.CTFontCopyFamilyName(font)).casefold() != family.casefold()
    ):
        return None
    actual = CoreText.CTFontGetSymbolicTraits(font)
    wanted = traits & (CoreText.kCTFontBoldTrait | CoreText.kCTFontItalicTrait)
    if actual & wanted != wanted:
        return None
    return font


def _missing_characters(font, text: str) -> list[str]:
    import CoreText

    missing = []
    for character in text:
        if character.isspace():
            continue
        ok, _glyphs = CoreText.CTFontGetGlyphsForCharacters(font, character, None, 1)
        if not ok:
            missing.append(f"U+{ord(character):04X}")
    return missing


def _outline(
    font, text: str, requested: str, actual: str, style: int, warning: str | None
) -> dict[str, Any]:
    import CoreText
    import Quartz

    base = {
        "Text": text,
        "RequestedFamily": requested,
        "ActualFamily": actual,
        "Style": style,
        "Warning": warning,
    }
    if not text:
        return {
            **base,
            "Advance": 0.0,
            "Height": 0.0,
            "Depth": 0.0,
            "Left": 0.0,
            "Right": 0.0,
            "Path": "",
        }
    # NoFontFallback semantics: the line is shaped with exactly this face.
    attributed = CoreText.CFAttributedStringCreate(
        None, text, {CoreText.kCTFontAttributeName: font}
    )
    line = CoreText.CTLineCreateWithAttributedString(attributed)
    advance = CoreText.CTLineGetTypographicBounds(line, None, None, None)[0] / EM
    path = Quartz.CGPathCreateMutable()
    for run in CoreText.CTLineGetGlyphRuns(line):
        run_font = CoreText.CFDictionaryGetValue(
            CoreText.CTRunGetAttributes(run), CoreText.kCTFontAttributeName
        )
        count = CoreText.CTRunGetGlyphCount(run)
        glyphs = CoreText.CTRunGetGlyphs(run, (0, count), None)
        positions = CoreText.CTRunGetPositions(run, (0, count), None)
        for glyph, position in zip(glyphs, positions, strict=True):
            transform = Quartz.CGAffineTransformMakeTranslation(position.x, position.y)
            glyph_path = CoreText.CTFontCreatePathForGlyph(run_font, glyph, transform)
            if glyph_path is not None:
                Quartz.CGPathAddPath(path, None, glyph_path)
    if Quartz.CGPathIsEmpty(path):
        return {
            **base,
            "Advance": advance,
            "Height": 0.0,
            "Depth": 0.0,
            "Left": 0.0,
            "Right": 0.0,
            "Path": "",
        }
    # CoreText already uses a y-up, baseline-relative space: no flip needed.
    bounds = Quartz.CGPathGetPathBoundingBox(path)
    left, bottom = bounds.origin.x, bounds.origin.y
    right, top = left + bounds.size.width, bottom + bounds.size.height
    return {
        **base,
        "Advance": advance,
        "Height": max(0.0, top) / EM,
        "Depth": max(0.0, -bottom) / EM,
        "Left": left / EM,
        "Right": right / EM,
        "Path": _svg_path(path),
    }


def _svg_path(path) -> str:
    import Quartz

    parts: list[str] = []

    def element(_info, item) -> None:
        kind, points = item.type, item.points
        if kind == Quartz.kCGPathElementMoveToPoint:
            parts.append(f"M{_n(points[0].x)} {_n(points[0].y)}")
        elif kind == Quartz.kCGPathElementAddLineToPoint:
            parts.append(f"L{_n(points[0].x)} {_n(points[0].y)}")
        elif kind == Quartz.kCGPathElementAddQuadCurveToPoint:
            parts.append(
                f"Q{_n(points[0].x)} {_n(points[0].y)} {_n(points[1].x)} {_n(points[1].y)}"
            )
        elif kind == Quartz.kCGPathElementAddCurveToPoint:
            parts.append(
                f"C{_n(points[0].x)} {_n(points[0].y)} {_n(points[1].x)} {_n(points[1].y)} "
                f"{_n(points[2].x)} {_n(points[2].y)}"
            )
        elif kind == Quartz.kCGPathElementCloseSubpath:
            parts.append("Z")
        else:
            raise OutlineError("字形路径类型无效。")

    Quartz.CGPathApply(path, None, element)
    return "".join(parts)


def _n(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text

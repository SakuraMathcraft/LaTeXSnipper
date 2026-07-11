"""Safe extraction and rendering of image assets embedded in exported text."""

from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


_SVG_TAG_RE = re.compile(r"(?is)<(?P<close>/?)svg\b[^>]*>")
_CODE_FENCE_RE = re.compile(r"(?is)```[ \t]*([^\r\n]*)\r?\n?(.*?)```")
_INLINE_CODE_RE = re.compile(r"(?s)(?P<ticks>`{1,2})(?P<body>.*?)(?P=ticks)")
_URL_RE = re.compile(r"(?is)url\((.*?)\)")
_FORBIDDEN_TAGS = {
    "audio",
    "embed",
    "foreignobject",
    "iframe",
    "object",
    "script",
    "video",
}
_EXTERNAL_REFERENCE_ATTRIBUTES = {"href", "src"}
_PANDOC_IMAGE_FORMATS = {
    "pandoc_docx",
    "pandoc_epub",
    "pandoc_odt",
    "pandoc_pdf",
    "pandoc_pptx",
}
_MAX_IMAGE_EDGE = 4096
_MAX_IMAGE_PIXELS = 16_000_000
_MAX_SVG_BYTES = 5_000_000
_MAX_SVG_ELEMENTS = 100_000


@dataclass(frozen=True, slots=True)
class ExportedImageAsset:
    index: int
    digest: str
    svg_path: Path
    png_path: Path


@dataclass(frozen=True, slots=True)
class PreparedPandocDocument:
    text: str
    asset_dir: Path | None
    assets: tuple[ExportedImageAsset, ...]
    skipped_svg_count: int


@dataclass(frozen=True, slots=True)
class _SvgRegion:
    start: int
    end: int
    svg_text: str | None


def supports_document_assets(format_key: str) -> bool:
    return format_key in _PANDOC_IMAGE_FORMATS


def prepare_pandoc_document(text: str, output_path: str | Path) -> PreparedPandocDocument:
    """Extract valid SVG blocks, render PNG fallbacks, and rewrite document image links."""
    source = str(text or "")
    regions = _find_svg_regions(source)
    if not regions:
        return PreparedPandocDocument(source, None, (), 0)

    destination = Path(output_path).expanduser().resolve()
    document_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    asset_dir = destination.parent / f"{destination.stem}_assets_{document_digest}"
    assets: list[ExportedImageAsset] = []
    skipped = 0
    rewritten: list[str] = []
    cursor = 0

    for region in regions:
        rewritten.append(source[cursor:region.start])
        cursor = region.end
        if region.svg_text is None:
            skipped += 1
            continue
        try:
            svg_bytes = _validate_svg(region.svg_text)
            index = len(assets) + 1
            asset = _write_svg_asset(svg_bytes, asset_dir, index)
        except (ET.ParseError, OSError, RuntimeError, ValueError):
            skipped += 1
            continue
        assets.append(asset)
        image_path = asset.png_path.as_posix()
        rewritten.append(f"\n\n![](<{image_path}>)\n\n")

    rewritten.append(source[cursor:])
    if not assets and asset_dir.exists():
        try:
            asset_dir.rmdir()
        except OSError:
            pass
    return PreparedPandocDocument(
        text="".join(rewritten).strip(),
        asset_dir=asset_dir if assets else None,
        assets=tuple(assets),
        skipped_svg_count=skipped,
    )


def _find_svg_regions(source: str) -> list[_SvgRegion]:
    regions: list[_SvgRegion] = []
    excluded_spans: list[tuple[int, int]] = []

    for match in _CODE_FENCE_RE.finditer(source):
        excluded_spans.append((match.start(), match.end()))
        language = match.group(1).strip().split(maxsplit=1)[0].lower() if match.group(1).strip() else ""
        if language not in {"svg", "xml"}:
            continue
        inner = match.group(2)
        if "<svg" not in inner.lower() and "</svg" not in inner.lower():
            continue
        inner_regions = _scan_raw_svg_regions(inner, base_offset=0)
        complete = [region.svg_text for region in inner_regions if region.svg_text is not None]
        if len(complete) == 1 and all(region.svg_text is not None for region in inner_regions):
            regions.append(_SvgRegion(match.start(), match.end(), complete[0]))
        else:
            regions.append(_SvgRegion(match.start(), match.end(), None))

    for match in _INLINE_CODE_RE.finditer(source):
        span = (match.start(), match.end())
        if not any(start <= span[0] and span[1] <= end for start, end in excluded_spans):
            excluded_spans.append(span)

    cursor = 0
    for start, end in sorted(excluded_spans):
        if start < cursor:
            cursor = max(cursor, end)
            continue
        if cursor < start:
            regions.extend(_scan_raw_svg_regions(source[cursor:start], base_offset=cursor))
        cursor = end
    if cursor < len(source):
        regions.extend(_scan_raw_svg_regions(source[cursor:], base_offset=cursor))

    regions.sort(key=lambda region: region.start)
    return regions


def _scan_raw_svg_regions(text: str, *, base_offset: int) -> list[_SvgRegion]:
    regions: list[_SvgRegion] = []
    depth = 0
    outer_start: int | None = None

    for match in _SVG_TAG_RE.finditer(text):
        is_close = bool(match.group("close"))
        tag = match.group(0)
        if is_close:
            if depth == 0:
                regions.append(_SvgRegion(base_offset + match.start(), base_offset + match.end(), None))
                continue
            depth -= 1
            if depth == 0 and outer_start is not None:
                end = match.end()
                regions.append(
                    _SvgRegion(
                        base_offset + outer_start,
                        base_offset + end,
                        text[outer_start:end],
                    )
                )
                outer_start = None
            continue

        if depth == 0:
            outer_start = match.start()
        if tag.rstrip().endswith("/>"):
            if depth == 0 and outer_start is not None:
                regions.append(
                    _SvgRegion(
                        base_offset + outer_start,
                        base_offset + match.end(),
                        text[outer_start:match.end()],
                    )
                )
                outer_start = None
            continue
        depth += 1

    if depth > 0 and outer_start is not None:
        regions.append(_SvgRegion(base_offset + outer_start, base_offset + len(text), None))
    return regions


def _validate_svg(svg_text: str) -> bytes:
    source = str(svg_text or "").strip()
    source_bytes = source.encode("utf-8")
    if len(source_bytes) > _MAX_SVG_BYTES:
        raise ValueError("SVG source is too large")
    lowered = source.lower()
    if not source or "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("SVG document declarations are not allowed")

    root = ET.fromstring(source)
    if _local_name(root.tag) != "svg":
        raise ValueError("SVG root element is missing")

    for element_index, element in enumerate(root.iter(), start=1):
        if element_index > _MAX_SVG_ELEMENTS:
            raise ValueError("SVG contains too many elements")
        tag_name = _local_name(element.tag)
        if tag_name in _FORBIDDEN_TAGS:
            raise ValueError(f"Unsafe SVG element: {tag_name}")
        if tag_name == "style":
            style_text = "".join(element.itertext())
            lowered_style = style_text.lower()
            if "@import" in lowered_style:
                raise ValueError("External SVG styles are not allowed")
            for url_match in _URL_RE.finditer(style_text):
                target = url_match.group(1).strip().strip("'\"")
                if target and not target.startswith("#"):
                    raise ValueError(f"External SVG URL is not allowed: {target}")
        for raw_name, raw_value in element.attrib.items():
            name = _local_name(raw_name)
            value = str(raw_value or "").strip()
            lowered_value = value.lower()
            if name.startswith("on"):
                raise ValueError(f"Unsafe SVG event attribute: {name}")
            if name in _EXTERNAL_REFERENCE_ATTRIBUTES and value and not value.startswith("#"):
                raise ValueError(f"External SVG reference is not allowed: {value}")
            if "@import" in lowered_value:
                raise ValueError("External SVG styles are not allowed")
            for url_match in _URL_RE.finditer(value):
                target = url_match.group(1).strip().strip("'\"")
                if target and not target.startswith("#"):
                    raise ValueError(f"External SVG URL is not allowed: {target}")
    return source_bytes


def _local_name(name: str) -> str:
    return str(name).rsplit("}", 1)[-1].split(":", 1)[-1].lower()


def _write_svg_asset(svg_bytes: bytes, asset_dir: Path, index: int) -> ExportedImageAsset:
    digest = hashlib.sha256(svg_bytes).hexdigest()[:12]
    base_name = f"image_{index:03d}_{digest}"
    svg_path = asset_dir / f"{base_name}.svg"
    png_path = asset_dir / f"{base_name}.png"
    png_bytes = _render_svg_png(svg_bytes)

    asset_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes_atomically(svg_path, svg_bytes)
    _write_bytes_atomically(png_path, png_bytes)
    return ExportedImageAsset(index, digest, svg_path, png_path)


def _render_svg_png(svg_bytes: bytes) -> bytes:
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        raise ValueError("SVG renderer rejected the document")

    size = renderer.defaultSize()
    width = int(size.width())
    height = int(size.height())
    if width <= 0 or height <= 0:
        view_box = renderer.viewBoxF()
        width = int(math.ceil(view_box.width()))
        height = int(math.ceil(view_box.height()))
    if width <= 0 or height <= 0:
        raise ValueError("SVG has no renderable dimensions")

    scale = min(1.0, _MAX_IMAGE_EDGE / max(width, height))
    pixel_scale = math.sqrt(_MAX_IMAGE_PIXELS / max(1, width * height))
    scale = min(scale, pixel_scale)
    width = max(1, int(round(width * scale)))
    height = max(1, int(round(height * scale)))

    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    try:
        renderer.render(painter)
    finally:
        painter.end()

    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Unable to allocate PNG output buffer")
    try:
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Unable to encode rendered SVG as PNG")
        return bytes(buffer.data())
    finally:
        buffer.close()


def _write_bytes_atomically(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() == data:
            return
        raise RuntimeError(f"Asset hash collision: {path.name}")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

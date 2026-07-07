# coding: utf-8

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class OpenStaxSource:
    source_id: str
    name: str
    url: str
    license: str
    attribution: str


SOURCES = {
    "calculus_v1": OpenStaxSource(
        source_id="calculus_v1",
        name="OpenStax Calculus Volume 1",
        url="https://d3bxy9euw4e147.cloudfront.net/oscms-prodcms/media/documents/CalculusVolume1-OP.pdf",
        license="CC BY-NC-SA 4.0",
        attribution="OpenStax, Rice University; Gilbert Strang and Edwin Herman",
    ),
    "college_algebra": OpenStaxSource(
        source_id="college_algebra",
        name="OpenStax College Algebra",
        url="https://assets.openstax.org/oscms-prodcms/media/documents/CollegeAlgebra-OP.pdf",
        license="CC BY-NC-SA 4.0",
        attribution="OpenStax, Rice University; Jay Abramson",
    ),
}

DEFAULT_PAGES = {
    "calculus_v1": "40-89+120-169",
    "college_algebra": "60-109+180-229",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create MathCraft page-level manifest from OpenStax PDFs.")
    parser.add_argument("--data-root", default=r"E:\MathCraftBenchData")
    parser.add_argument("--output", default=r"E:\MathCraftBenchData\manifests\openstax_mixed_gpu_144dpi.jsonl")
    parser.add_argument(
        "--pages",
        default=",".join(f"{key}:{value}" for key, value in DEFAULT_PAGES.items()),
        help="Comma-separated page ranges, e.g. calculus_v1:120-139,college_algebra:80-99. Pages are 1-based PDF pages.",
    )
    parser.add_argument("--dpi", type=int, default=144)
    args = parser.parse_args(argv)

    data_root = Path(args.data_root)
    raw_dir = data_root / "raw" / "openstax"
    image_dir = data_root / "processed" / "openstax_pages"
    output = Path(args.output)
    raw_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    selected_pages = parse_page_specs(args.pages)
    count = 0
    with output.open("w", encoding="utf-8") as fh:
        for source_id, page_numbers in selected_pages.items():
            source = SOURCES[source_id]
            pdf_path = raw_dir / f"{source_id}.pdf"
            if not pdf_path.exists():
                print(f"[download] {source.name} -> {pdf_path}")
                urllib.request.urlretrieve(source.url, pdf_path)
            count += render_source_pages(
                source,
                pdf_path,
                image_dir / source_id,
                page_numbers,
                dpi=args.dpi,
                output_fh=fh,
            )

    print(f"wrote {count} OpenStax page manifest rows to {output}")
    return 0


def parse_page_specs(value: str) -> dict[str, list[int]]:
    selected: dict[str, list[int]] = {}
    for item in value.split(","):
        text = item.strip()
        if not text:
            continue
        if ":" not in text:
            raise ValueError(f"invalid page spec: {text}")
        source_id, range_text = text.split(":", 1)
        source_id = source_id.strip()
        if source_id not in SOURCES:
            raise ValueError(f"unknown OpenStax source: {source_id}")
        pages = parse_pages(range_text)
        selected[source_id] = pages
    return selected


def parse_pages(value: str) -> list[int]:
    pages: list[int] = []
    for part in re.split(r"[+;]", value.strip()):
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start = int(left)
            end = int(right)
            if end < start:
                raise ValueError(f"invalid page range: {part}")
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def render_source_pages(
    source: OpenStaxSource,
    pdf_path: Path,
    output_dir: Path,
    page_numbers: list[int],
    *,
    dpi: int,
    output_fh,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    count = 0
    for page_number in page_numbers:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError(
                f"{source.source_id}: page {page_number} outside 1..{document.page_count}"
            )
        page = document[page_number - 1]
        image_path = output_dir / f"{source.source_id}_p{page_number:04d}.png"
        if not image_path.exists():
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(image_path)
        item = {
            "id": f"openstax_{source.source_id}_p{page_number:04d}",
            "task": "mixed_page",
            "profile": "mixed",
            "image": str(image_path),
            "target_latex": "",
            "target_text": "",
            "source": source.name,
            "source_url": source.url,
            "license": source.license,
            "attribution": source.attribution,
            "page_number": page_number,
            "difficulty": "document_page",
            "tags": ["openstax", source.source_id, "mixed_page"],
        }
        output_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        count += 1
    document.close()
    return count


if __name__ == "__main__":
    raise SystemExit(main())

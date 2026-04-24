# coding: utf-8
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from core.mathcraft_document_engine import compose_mathcraft_markdown_pages
from mathcraft_ocr.debug_blocks import write_debug_blocks
from mathcraft_ocr.runtime import MathCraftRuntime
from mathcraft_ocr.serialization import mixed_result_to_json


DEFAULT_CASES_FROM = ROOT / "test_pdf" / "outputs" / "block_layout_regression_v3" / "summary.json"
DEFAULT_OUTPUT = ROOT / "test_pdf" / "outputs" / "block_layout_regression_v4"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MathCraft PDF block/layout regression.")
    parser.add_argument("--cases-from", type=Path, default=DEFAULT_CASES_FROM)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", default="auto", choices=["auto", "cpu", "gpu"])
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument(
        "--debug-only",
        action="store_true",
        help="Generate debug_blocks.png/html from existing structured.json files without rerunning OCR.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = _load_cases(args.cases_from)
    if args.case:
        selected = set(args.case)
        cases = [case for case in cases if str(case.get("case")) in selected]
    if args.limit > 0:
        cases = cases[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)

    runtime = None if args.debug_only else MathCraftRuntime(provider_preference=args.provider)
    summary: list[dict[str, Any]] = []
    for case in cases:
        case_name = str(case["case"])
        pdf_path = ROOT / "test_pdf" / str(case["pdf"])
        page_number = int(case["page"])
        case_dir = args.out / case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        image = _render_page(pdf_path, page_number, args.dpi)
        if args.debug_only:
            payload = json.loads((case_dir / "structured.json").read_text(encoding="utf-8"))
            seconds = 0.0
        else:
            assert runtime is not None
            start = time.perf_counter()
            result = runtime.recognize_mixed(image)
            seconds = time.perf_counter() - start
            payload = mixed_result_to_json(result)
            payload["page_index"] = page_number
            payload["image_size"] = [image.size[0], image.size[1]]
            payload["pdf"] = pdf_path.name
            (case_dir / "structured.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            markdown = compose_mathcraft_markdown_pages([payload])
            (case_dir / "document_engine.md").write_text(markdown, encoding="utf-8")

        write_debug_blocks(payload, case_dir, image=image)
        item = _summarize_case(case_name, pdf_path, page_number, payload, seconds, case_dir)
        summary.append(item)
        print(f"[OK] {case_name}: blocks={item['blocks']} seconds={seconds:.2f}")

    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"case summary must be a list: {path}")
    cases: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if {"case", "pdf", "page"} <= set(item):
            cases.append({"case": item["case"], "pdf": item["pdf"], "page": item["page"]})
    return cases


def _render_page(pdf_path: Path, page_number: int, dpi: int):
    try:
        import fitz
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("PDF regression rendering requires PyMuPDF and Pillow") from exc

    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def _summarize_case(
    case_name: str,
    pdf_path: Path,
    page_number: int,
    payload: dict[str, Any],
    seconds: float,
    case_dir: Path,
) -> dict[str, Any]:
    blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else []
    roles = Counter(str(block.get("role") or "paragraph") for block in blocks if isinstance(block, dict))
    flags: Counter[str] = Counter()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for flag in block.get("confidence_flags") or []:
            flags[str(flag)] += 1
    text = str(payload.get("text") or "")
    return {
        "case": case_name,
        "pdf": pdf_path.name,
        "page": page_number,
        "seconds": round(seconds, 2),
        "blocks": len(blocks),
        "roles": dict(roles),
        "flags": dict(flags),
        "provider": payload.get("provider"),
        "text_chars": len(text),
        "nonempty_lines": sum(1 for line in text.splitlines() if line.strip()),
        "out": str(case_dir / "document_engine.md"),
        "debug_png": str(case_dir / "debug_blocks.png"),
        "debug_html": str(case_dir / "debug_blocks.html"),
    }


if __name__ == "__main__":
    raise SystemExit(main())

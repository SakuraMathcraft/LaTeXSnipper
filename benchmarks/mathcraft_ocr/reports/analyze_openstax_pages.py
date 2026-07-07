# coding: utf-8

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze MathCraft OCR page-level OpenStax results.")
    parser.add_argument("--results", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    rows = _read_jsonl(Path(args.results))
    manifest = {str(row.get("id")): row for row in _read_jsonl(Path(args.manifest))}
    metrics = [_page_metrics(row, manifest.get(str(row.get("sample_id")), {})) for row in rows]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    page_csv = output_dir / "openstax_page_metrics.csv"
    summary_csv = output_dir / "openstax_summary.csv"
    report_md = output_dir / "openstax_report.md"
    _write_csv(page_csv, metrics)
    summary = _summary_rows(metrics)
    _write_csv(summary_csv, summary)
    _write_report(report_md, summary, metrics)

    print(f"wrote {page_csv}")
    print(f"wrote {summary_csv}")
    print(f"wrote {report_md}")
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _page_metrics(row: dict[str, Any], manifest_row: dict[str, Any]) -> dict[str, Any]:
    blocks = row.get("blocks") if isinstance(row.get("blocks"), list) else []
    text_blocks = [block for block in blocks if str(block.get("kind")) == "text"]
    formula_blocks = [block for block in blocks if str(block.get("kind")) != "text"]
    flags = Counter(
        flag
        for block in blocks
        for flag in (block.get("confidence_flags") or [])
        if isinstance(flag, str)
    )
    source_id = ""
    tags = manifest_row.get("tags")
    if isinstance(tags, list) and len(tags) > 1:
        source_id = str(tags[1])
    return {
        "sample_id": row.get("sample_id"),
        "source_id": source_id,
        "page_number": manifest_row.get("page_number"),
        "ok": bool(row.get("ok")),
        "empty": not bool(str(row.get("text", "")).strip()),
        "latency_ms": float(row.get("latency_ms") or 0.0),
        "text_length": len(str(row.get("text", ""))),
        "region_count": len(row.get("regions") or []),
        "block_count": len(blocks),
        "text_block_count": len(text_blocks),
        "formula_block_count": len(formula_blocks),
        "display_formula_count": sum(1 for block in formula_blocks if block.get("is_display")),
        "inline_formula_count": sum(1 for block in formula_blocks if block.get("is_display") is False),
        "low_score_blocks": flags.get("low_score", 0),
        "quality_flag_count": sum(flags.values()),
        "quality_flags": " ".join(sorted(flags)),
    }


def _summary_rows(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in metrics:
        grouped["all"].append(item)
        grouped[str(item.get("source_id") or "unknown")].append(item)
    rows: list[dict[str, Any]] = []
    for key in ["all", "calculus_v1", "college_algebra", "unknown"]:
        items = grouped.get(key)
        if not items:
            continue
        latencies = [float(item["latency_ms"]) for item in items if item["ok"]]
        rows.append(
            {
                "subset": key,
                "count": len(items),
                "ok": sum(1 for item in items if item["ok"]),
                "empty": sum(1 for item in items if item["empty"]),
                "avg_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
                "median_latency_ms": round(median(latencies), 3) if latencies else 0.0,
                "max_latency_ms": round(max(latencies), 3) if latencies else 0.0,
                "avg_blocks": round(mean(float(item["block_count"]) for item in items), 3),
                "avg_formula_blocks": round(mean(float(item["formula_block_count"]) for item in items), 3),
                "avg_low_score_blocks": round(mean(float(item["low_score_blocks"]) for item in items), 3),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    summary: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    lines = [
        "# MathCraft OCR on OpenStax Page Images",
        "",
        f"- Completed pages: {len(metrics)}",
        f"- Failures: {sum(1 for item in metrics if not item['ok'])}",
        f"- Empty outputs: {sum(1 for item in metrics if item['empty'])}",
        "",
        "| Subset | Count | Median Latency (ms) | Max Latency (ms) | Avg Blocks | Avg Formula Blocks |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        lines.append(
            "| {subset} | {count} | {median_latency_ms:.1f} | {max_latency_ms:.1f} | "
            "{avg_blocks:.1f} | {avg_formula_blocks:.1f} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

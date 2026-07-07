# coding: utf-8

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_unimer_results import (  # noqa: E402
    _compute_metrics,
    _read_jsonl,
    _read_manifest,
    _subset_rows,
    _write_examples,
    _write_subset_csv,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze MathCraft OCR results on MathWriting test.")
    parser.add_argument("--results", required=True, help="MathCraft JSONL result file.")
    parser.add_argument("--manifest", required=True, help="MathWriting test manifest JSONL file.")
    parser.add_argument("--output-dir", required=True, help="Directory for CSV/Markdown outputs.")
    args = parser.parse_args(argv)

    result_path = Path(args.results)
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _read_manifest(manifest_path)
    rows = _read_jsonl(result_path)
    metrics = _compute_metrics(rows, manifest)
    subset_rows = _subset_rows(metrics)

    csv_path = output_dir / "mathwriting_test_gpu_subset_metrics.csv"
    md_path = output_dir / "mathwriting_test_gpu_report.md"
    examples_path = output_dir / "mathwriting_test_gpu_examples.json"

    _write_subset_csv(csv_path, subset_rows)
    write_markdown(md_path, subset_rows, metrics)
    _write_examples(examples_path, metrics)

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print(f"wrote {examples_path}")
    return 0


def write_markdown(path: Path, subset_rows: list[dict], metrics: list[dict]) -> None:
    providers = Counter(str(item["provider_active"]) for item in metrics)
    lines = [
        "# MathCraft OCR on MathWriting Test",
        "",
        "Protocol: fixed MathWriting test split, offline raster images, normalized LaTeX labels as ground truth.",
        "",
        f"- Results: {len(metrics)}",
        f"- Providers: {dict(providers)}",
        f"- Failures: {sum(1 for item in metrics if not item['ok'])}",
        f"- Empty outputs: {sum(1 for item in metrics if item['empty'])}",
        "",
        "| Split | Count | Norm Exact | Compact Exact | Avg Sim | Median Sim | Sim >= .95 | P50 ms | P95 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in subset_rows:
        lines.append(
            "| {subset} | {count} | {norm_exact_rate:.2%} | {compact_exact_rate:.2%} | "
            "{avg_similarity:.4f} | {median_similarity:.4f} | {similarity_ge_095:.2%} | "
            "{latency_p50_ms:.1f} | {latency_p95_ms:.1f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "| Split | BLEU-4 | Avg Char NED | Median Char NED | Avg Token NED | Median Token NED |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in subset_rows:
        lines.append(
            "| {subset} | {bleu4:.4f} | {avg_char_ned:.4f} | {median_char_ned:.4f} | "
            "{avg_token_ned:.4f} | {median_token_ned:.4f} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

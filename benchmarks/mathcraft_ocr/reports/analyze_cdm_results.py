# coding: utf-8

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any


SUBSETS = ("all", "spe", "cpe", "sce", "hwe")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize official UniMERNet CDM results.")
    parser.add_argument("--metrics", required=True, help="Official CDM merged metrics_res.json.")
    parser.add_argument("--input", required=True, help="Official CDM input JSON used for the run.")
    parser.add_argument("--manifest", required=True, help="UniMER-Test manifest JSONL.")
    parser.add_argument("--shards", required=True, help="CDM shard summary CSV.")
    parser.add_argument("--output-dir", required=True, help="Directory for compact report tables.")
    args = parser.parse_args(argv)

    metrics_path = Path(args.metrics)
    input_path = Path(args.input)
    manifest_path = Path(args.manifest)
    shards_path = Path(args.shards)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = read_json(metrics_path)
    cdm_input = read_json(input_path)
    manifest = read_manifest(manifest_path)
    shard_rows = read_csv(shards_path)

    details = metrics.get("details", {})
    if not isinstance(details, dict):
        raise ValueError(f"CDM metrics has no details object: {metrics_path}")

    expected_by_subset: dict[str, set[str]] = {subset: set() for subset in SUBSETS}
    evaluated_by_subset: dict[str, list[float]] = {subset: [] for subset in SUBSETS}

    for row in cdm_input:
        sample_id = str(row["img_id"])
        subset = subset_for_sample(manifest, sample_id)
        expected_by_subset["all"].add(sample_id)
        if subset in expected_by_subset:
            expected_by_subset[subset].add(sample_id)

    for sample_id, sample_metrics in details.items():
        score = float(sample_metrics["F1_score"])
        subset = subset_for_sample(manifest, str(sample_id))
        evaluated_by_subset["all"].append(score)
        if subset in evaluated_by_subset:
            evaluated_by_subset[subset].append(score)

    subset_rows = [
        build_subset_row(
            subset=subset,
            expected_ids=expected_by_subset[subset],
            scores=evaluated_by_subset[subset],
        )
        for subset in SUBSETS
    ]

    total_expected = sum_int(shard_rows, "expected_rows")
    total_evaluated = sum_int(shard_rows, "evaluated_rows")
    total_skipped = sum_int(shard_rows, "skipped_rows")
    complete_shards = sum(1 for row in shard_rows if row.get("state") == "complete")
    run_rows = [
        {
            "metric": "mean_score",
            "value": metrics.get("mean_score", ""),
        },
        {
            "metric": "exp_rate",
            "value": metrics.get("exp_rate", ""),
        },
        {
            "metric": "expected_rows",
            "value": total_expected,
        },
        {
            "metric": "evaluated_rows",
            "value": total_evaluated,
        },
        {
            "metric": "skipped_rows",
            "value": total_skipped,
        },
        {
            "metric": "completed_shards",
            "value": complete_shards,
        },
        {
            "metric": "total_shards",
            "value": len(shard_rows),
        },
    ]

    write_csv(output_dir / "cdm_official_run_summary.csv", run_rows)
    write_csv(output_dir / "cdm_official_subset_metrics.csv", subset_rows)
    write_csv(output_dir / "cdm_official_shard_summary.csv", shard_rows)
    write_markdown_report(output_dir / "cdm_official_report.md", run_rows, subset_rows)

    print(f"wrote CDM summary tables to {output_dir}")
    return 0


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in read_jsonl(path)}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def subset_for_sample(manifest: dict[str, dict[str, Any]], sample_id: str) -> str:
    row = manifest.get(sample_id, {})
    tags = row.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            text = str(tag).lower()
            if text in SUBSETS and text != "all":
                return text
    return "unknown"


def build_subset_row(subset: str, expected_ids: set[str], scores: list[float]) -> dict[str, Any]:
    evaluated = len(scores)
    expected = len(expected_ids)
    return {
        "subset": subset,
        "expected_rows": expected,
        "evaluated_rows": evaluated,
        "skipped_rows": expected - evaluated,
        "mean_score": rounded(sum(scores) / evaluated) if evaluated else "",
        "exp_rate": rounded(sum(1 for score in scores if score == 1.0) / evaluated) if evaluated else "",
        "median_score": rounded(median(scores)) if evaluated else "",
        "p10_score": rounded(percentile(scores, 0.10)) if evaluated else "",
        "p90_score": rounded(percentile(scores, 0.90)) if evaluated else "",
    }


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def rounded(value: float) -> float:
    return round(value, 4)


def sum_int(rows: list[dict[str, str]], field: str) -> int:
    return sum(int(row.get(field, 0) or 0) for row in rows)


def write_markdown_report(path: Path, run_rows: list[dict[str, Any]], subset_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Official CDM UniMER-Test Report",
        "",
        "## Run Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {row['metric']} | {row['value']} |" for row in run_rows)
    lines.extend(
        [
            "",
            "## Subset Metrics",
            "",
            "| Subset | Expected | Evaluated | Skipped | Mean CDM | Exp Rate | Median | P10 | P90 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        "| {subset} | {expected_rows} | {evaluated_rows} | {skipped_rows} | {mean_score} | {exp_rate} | {median_score} | {p10_score} | {p90_score} |".format(
            **row
        )
        for row in subset_rows
    )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

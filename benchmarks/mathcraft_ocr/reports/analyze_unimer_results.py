# coding: utf-8

from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

try:
    from rapidfuzz.distance import Levenshtein as RF_LEVENSHTEIN
except ImportError:  # pragma: no cover - optional benchmark acceleration
    RF_LEVENSHTEIN = None


SPACE_RE = re.compile(r"\s+")
LATEX_SPACE_COMMAND_RE = re.compile(r"\\(?:!|,|;|:|quad\b|qquad\b)")
TOKEN_RE = re.compile(r"\\[A-Za-z]+|\\.|[A-Za-z]+|\d+|[^\s]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze MathCraft OCR results on UniMER-Test.")
    parser.add_argument("--results", required=True, help="MathCraft JSONL result file.")
    parser.add_argument("--manifest", required=True, help="UniMER-Test manifest JSONL file.")
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

    csv_path = output_dir / "unimer_test_gpu_subset_metrics.csv"
    md_path = output_dir / "unimer_test_gpu_report.md"
    examples_path = output_dir / "unimer_test_gpu_examples.json"

    _write_subset_csv(csv_path, subset_rows)
    _write_markdown(md_path, subset_rows, metrics)
    _write_examples(examples_path, metrics)

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print(f"wrote {examples_path}")
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            rows.append(row)
    return rows


def _read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(path)
    return {str(row.get("id", "")): row for row in rows}


def _compute_metrics(
    rows: list[dict[str, Any]],
    manifest: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        target_row = manifest.get(sample_id, {})
        tags = target_row.get("tags", [])
        subset = str(tags[1]) if isinstance(tags, list) and len(tags) > 1 else "unknown"
        subset_name = str(tags[2]) if isinstance(tags, list) and len(tags) > 2 else subset
        prediction = str(row.get("text", ""))
        target = str(target_row.get("target_latex", ""))
        norm_prediction = normalize_latex(prediction)
        norm_target = normalize_latex(target)
        compact_prediction = compact_latex(norm_prediction)
        compact_target = compact_latex(norm_target)
        prediction_tokens = tokenize_latex(norm_prediction)
        target_tokens = tokenize_latex(norm_target)
        char_edit_distance = edit_distance(compact_prediction, compact_target)
        char_ned = normalized_edit_distance(compact_prediction, compact_target)
        token_ed = edit_distance(prediction_tokens, target_tokens)
        token_ned = normalized_edit_distance(prediction_tokens, target_tokens)
        similarity = difflib.SequenceMatcher(
            None,
            compact_prediction,
            compact_target,
            autojunk=False,
        ).ratio()
        metrics.append(
            {
                "sample_id": sample_id,
                "subset": subset,
                "subset_name": subset_name,
                "ok": bool(row.get("ok")),
                "empty": not bool(prediction.strip()),
                "provider_active": row.get("provider_active"),
                "latency_ms": float(row.get("latency_ms") or 0.0),
                "score": row.get("score"),
                "prediction": prediction,
                "target": target,
                "norm_exact": norm_prediction == norm_target,
                "compact_exact": compact_prediction == compact_target,
                "char_edit_distance": char_edit_distance,
                "char_normalized_edit_distance": char_ned,
                "token_edit_distance": token_ed,
                "token_normalized_edit_distance": token_ned,
                "prediction_tokens": prediction_tokens,
                "target_tokens": target_tokens,
                "similarity": similarity,
                "prediction_length": len(compact_prediction),
                "target_length": len(compact_target),
            }
        )
    return metrics


def normalize_latex(value: str) -> str:
    text = SPACE_RE.sub(" ", str(value or "").strip())
    text = LATEX_SPACE_COMMAND_RE.sub("", text)
    return SPACE_RE.sub(" ", text).strip()


def compact_latex(value: str) -> str:
    return SPACE_RE.sub("", normalize_latex(value))


def tokenize_latex(value: str) -> list[str]:
    return TOKEN_RE.findall(normalize_latex(value))


def edit_distance(left: str | list[str], right: str | list[str]) -> int:
    if RF_LEVENSHTEIN is not None:
        return int(RF_LEVENSHTEIN.distance(left, right))
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            current.append(
                min(
                    current[j - 1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def normalized_edit_distance(left: str | list[str], right: str | list[str]) -> float:
    if RF_LEVENSHTEIN is not None:
        return float(RF_LEVENSHTEIN.normalized_distance(left, right))
    return edit_distance(left, right) / max(len(left), len(right), 1)


def corpus_bleu(predictions: list[list[str]], references: list[list[str]], max_order: int = 4) -> float:
    matches_by_order = [0] * max_order
    possible_matches_by_order = [0] * max_order
    prediction_length = 0
    reference_length = 0
    for prediction, reference in zip(predictions, references):
        prediction_length += len(prediction)
        reference_length += len(reference)
        reference_ngram_counts = _ngram_counts(reference, max_order)
        prediction_ngram_counts = _ngram_counts(prediction, max_order)
        overlap = {
            ngram: min(count, prediction_ngram_counts[ngram])
            for ngram, count in reference_ngram_counts.items()
            if ngram in prediction_ngram_counts
        }
        for ngram, count in overlap.items():
            matches_by_order[len(ngram) - 1] += count
        for order in range(1, max_order + 1):
            possible = len(prediction) - order + 1
            if possible > 0:
                possible_matches_by_order[order - 1] += possible
    precisions = [0.0] * max_order
    for i in range(max_order):
        if possible_matches_by_order[i] > 0:
            precisions[i] = matches_by_order[i] / possible_matches_by_order[i]
    if min(precisions) > 0:
        geo_mean = math.exp(sum(math.log(value) for value in precisions) / max_order)
    else:
        smooth_precisions = [
            (matches_by_order[i] + 1.0) / (possible_matches_by_order[i] + 1.0)
            if possible_matches_by_order[i] > 0
            else 0.0
            for i in range(max_order)
        ]
        geo_mean = math.exp(sum(math.log(max(value, 1e-12)) for value in smooth_precisions) / max_order)
    ratio = prediction_length / max(reference_length, 1)
    brevity_penalty = 1.0 if ratio > 1.0 else math.exp(1.0 - 1.0 / max(ratio, 1e-12))
    return brevity_penalty * geo_mean


def _ngram_counts(tokens: list[str], max_order: int) -> Counter[tuple[str, ...]]:
    counts: Counter[tuple[str, ...]] = Counter()
    for order in range(1, max_order + 1):
        for index in range(0, len(tokens) - order + 1):
            counts[tuple(tokens[index : index + order])] += 1
    return counts


def _subset_rows(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in metrics:
        groups[str(item["subset"])].append(item)
        groups["all"].append(item)

    rows: list[dict[str, Any]] = []
    for subset in _ordered_subsets(groups):
        items = groups[subset]
        latencies = [float(item["latency_ms"]) for item in items if item["ok"]]
        similarities = [float(item["similarity"]) for item in items]
        predictions = [item["prediction_tokens"] for item in items]
        references = [item["target_tokens"] for item in items]
        rows.append(
            {
                "subset": subset,
                "subset_name": _subset_name(subset, items),
                "count": len(items),
                "ok": sum(1 for item in items if item["ok"]),
                "fail": sum(1 for item in items if not item["ok"]),
                "empty": sum(1 for item in items if item["empty"]),
                "norm_exact": sum(1 for item in items if item["norm_exact"]),
                "norm_exact_rate": _rate(sum(1 for item in items if item["norm_exact"]), len(items)),
                "compact_exact": sum(1 for item in items if item["compact_exact"]),
                "compact_exact_rate": _rate(
                    sum(1 for item in items if item["compact_exact"]),
                    len(items),
                ),
                "bleu4": round(corpus_bleu(predictions, references), 6),
                "avg_char_ned": round(mean(float(item["char_normalized_edit_distance"]) for item in items), 6),
                "median_char_ned": round(median(float(item["char_normalized_edit_distance"]) for item in items), 6),
                "avg_token_ned": round(mean(float(item["token_normalized_edit_distance"]) for item in items), 6),
                "median_token_ned": round(median(float(item["token_normalized_edit_distance"]) for item in items), 6),
                "avg_similarity": round(mean(similarities), 6) if similarities else 0.0,
                "median_similarity": round(median(similarities), 6) if similarities else 0.0,
                "similarity_ge_090": _rate(sum(1 for value in similarities if value >= 0.90), len(items)),
                "similarity_ge_095": _rate(sum(1 for value in similarities if value >= 0.95), len(items)),
                "similarity_ge_098": _rate(sum(1 for value in similarities if value >= 0.98), len(items)),
                "latency_p50_ms": _percentile(latencies, 50),
                "latency_p90_ms": _percentile(latencies, 90),
                "latency_p95_ms": _percentile(latencies, 95),
            }
        )
    return rows


def _ordered_subsets(groups: dict[str, list[dict[str, Any]]]) -> list[str]:
    preferred = ["all", "spe", "cpe", "sce", "hwe", "unknown"]
    ordered = [subset for subset in preferred if subset in groups]
    ordered.extend(sorted(subset for subset in groups if subset not in set(ordered)))
    return ordered


def _subset_name(subset: str, items: list[dict[str, Any]]) -> str:
    if subset == "all":
        return "all"
    return str(items[0].get("subset_name") or subset) if items else subset


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((percentile / 100.0) * (len(ordered) - 1))
    index = max(0, min(index, len(ordered) - 1))
    return round(ordered[index], 3)


def _write_subset_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(
    path: Path,
    subset_rows: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> None:
    providers = Counter(str(item["provider_active"]) for item in metrics)
    lines = [
        "# MathCraft OCR on UniMER-Test",
        "",
        "Reported outputs are produced by the full MathCraft runtime, not raw decoder strings.",
        "",
        f"- Results: {len(metrics)}",
        f"- Providers: {dict(providers)}",
        f"- Failures: {sum(1 for item in metrics if not item['ok'])}",
        f"- Empty outputs: {sum(1 for item in metrics if item['empty'])}",
        "",
        "| Subset | Count | Norm Exact | Compact Exact | Avg Sim | Median Sim | Sim >= .95 | P50 ms | P95 ms |",
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
            "| Subset | BLEU-4 | Avg Char NED | Median Char NED | Avg Token NED | Median Token NED |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in subset_rows:
        lines.append(
            "| {subset} | {bleu4:.4f} | {avg_char_ned:.4f} | {median_char_ned:.4f} | "
            "{avg_token_ned:.4f} | {median_token_ned:.4f} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_examples(path: Path, metrics: list[dict[str, Any]]) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in metrics:
        groups[str(item["subset"])].append(item)

    payload: dict[str, Any] = {}
    for subset, items in sorted(groups.items()):
        payload[subset] = {
            "high_similarity_non_exact": [
                _example(item)
                for item in sorted(
                    (item for item in items if not item["compact_exact"]),
                    key=lambda item: float(item["similarity"]),
                    reverse=True,
                )[:5]
            ],
            "low_similarity": [
                _example(item)
                for item in sorted(items, key=lambda item: float(item["similarity"]))[:5]
            ],
        }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _example(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_id": item["sample_id"],
        "subset": item["subset"],
        "similarity": round(float(item["similarity"]), 6),
        "compact_exact": item["compact_exact"],
        "prediction": str(item["prediction"])[:1000],
        "target": str(item["target"])[:1000],
    }


if __name__ == "__main__":
    raise SystemExit(main())

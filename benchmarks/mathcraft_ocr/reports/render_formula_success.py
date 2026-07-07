# coding: utf-8

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any


TEX_TEMPLATE = r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,amsfonts,bm,mathrsfs,mathtools}
\pagestyle{empty}
\begin{document}
\[
%s
\]
\end{document}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure LaTeX render success for formula OCR results.")
    parser.add_argument("--results", required=True, help="MathCraft JSONL result file.")
    parser.add_argument("--manifest", required=True, help="Formula manifest JSONL file.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit.")
    parser.add_argument("--force", action="store_true", help="Recompute rows already present in the CSV.")
    args = parser.parse_args(argv)

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise FileNotFoundError("pdflatex was not found on PATH")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "formula_render_success_rows.csv"
    summary_path = output_dir / "formula_render_success_summary.csv"
    report_path = output_dir / "formula_render_success_report.md"

    manifest = read_manifest(Path(args.manifest))
    results = read_jsonl(Path(args.results))
    if args.limit > 0:
        results = results[: args.limit]

    rows = [] if args.force else read_existing_rows(rows_path)
    completed = {str(row["sample_id"]) for row in rows}
    pending = [row for row in results if str(row.get("sample_id", "")) not in completed]

    with tempfile.TemporaryDirectory(prefix="mathcraft_formula_render_") as tmp:
        work_root = Path(tmp)
        for index, result in enumerate(pending, start=1):
            sample_id = str(result.get("sample_id", ""))
            target_row = manifest.get(sample_id, {})
            subset = subset_for_manifest(target_row)
            prediction = str(result.get("text", ""))
            target = str(target_row.get("target_latex", ""))
            print(f"[render] {index}/{len(pending)} {sample_id}")
            pred = render_latex(prediction, work_root / f"{sample_id}_pred", pdflatex=pdflatex)
            gt = render_latex(target, work_root / f"{sample_id}_gt", pdflatex=pdflatex)
            rows.append(
                {
                    "sample_id": sample_id,
                    "subset": subset,
                    "prediction_render_ok": pred["ok"],
                    "target_render_ok": gt["ok"],
                    "both_render_ok": pred["ok"] and gt["ok"],
                    "prediction_error": pred["error"],
                    "target_error": gt["error"],
                }
            )
            write_rows(rows_path, rows)

    summary = summary_rows(rows)
    write_rows(summary_path, summary)
    write_report(report_path, summary)
    print(f"wrote {rows_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")
    return 0


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id", "")): row for row in read_jsonl(path)}


def read_existing_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def subset_for_manifest(row: dict[str, Any]) -> str:
    tags = row.get("tags", [])
    if isinstance(tags, list) and len(tags) > 1:
        return str(tags[1])
    return "unknown"


def render_latex(formula: str, work_dir: Path, *, pdflatex: str) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    tex_path = work_dir / "formula.tex"
    tex_path.write_text(TEX_TEMPLATE % formula, encoding="utf-8")
    try:
        process = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pdflatex timeout"}
    if process.returncode != 0:
        return {"ok": False, "error": short_error(process.stdout)}
    if not (work_dir / "formula.pdf").exists():
        return {"ok": False, "error": "pdflatex produced no PDF"}
    return {"ok": True, "error": ""}


def short_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    interesting = [line for line in lines if line.startswith("!") or "Error" in line]
    return " | ".join((interesting or lines)[-3:])[:500]


def summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped["all"].append(row)
        grouped[str(row["subset"])].append(row)
    output = []
    for subset in sorted(grouped, key=lambda value: (value != "all", value)):
        items = grouped[subset]
        output.append(
            {
                "subset": subset,
                "count": len(items),
                "prediction_render_ok": sum(as_bool(item["prediction_render_ok"]) for item in items),
                "prediction_render_rate": rate(
                    sum(as_bool(item["prediction_render_ok"]) for item in items),
                    len(items),
                ),
                "target_render_ok": sum(as_bool(item["target_render_ok"]) for item in items),
                "target_render_rate": rate(sum(as_bool(item["target_render_ok"]) for item in items), len(items)),
                "both_render_ok": sum(as_bool(item["both_render_ok"]) for item in items),
                "both_render_rate": rate(sum(as_bool(item["both_render_ok"]) for item in items), len(items)),
            }
        )
    return output


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Formula Render Success",
        "",
        "| Subset | Count | Prediction Render | Target Render | Both Render |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {subset} | {count} | {prediction_render_rate:.2%} | "
            "{target_render_rate:.2%} | {both_render_rate:.2%} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


if __name__ == "__main__":
    raise SystemExit(main())

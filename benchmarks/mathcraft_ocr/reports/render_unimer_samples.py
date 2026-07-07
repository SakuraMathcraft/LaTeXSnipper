# coding: utf-8

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

import cv2
import fitz
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_unimer_results import compact_latex, normalize_latex  # noqa: E402


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
    parser = argparse.ArgumentParser(
        description="Render selected UniMER-Test predictions and compute render-consistency fallback metrics."
    )
    parser.add_argument("--results", required=True, help="MathCraft JSONL result file.")
    parser.add_argument("--manifest", required=True, help="UniMER-Test manifest JSONL file.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--subset", default="all", help="Subset to render: all/spe/cpe/sce/hwe.")
    parser.add_argument("--per-subset", type=int, default=20, help="Max selected samples per subset.")
    parser.add_argument("--min-similarity", type=float, default=0.95)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--keep-images", action="store_true", help="Write rendered PNG pairs.")
    args = parser.parse_args(argv)

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        raise FileNotFoundError("pdflatex was not found on PATH")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "rendered_pairs"
    if args.keep_images:
        image_dir.mkdir(parents=True, exist_ok=True)

    manifest = _read_manifest(Path(args.manifest))
    rows = _read_jsonl(Path(args.results))
    candidates = _select_candidates(
        rows,
        manifest,
        subset_filter=args.subset,
        per_subset=args.per_subset,
        min_similarity=args.min_similarity,
    )

    render_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="mathcraft_render_") as tmp:
        work_root = Path(tmp)
        for index, item in enumerate(candidates, start=1):
            sample_id = item["sample_id"]
            print(f"[render] {index}/{len(candidates)} {sample_id}")
            pred = _render_latex(
                item["prediction"],
                work_root / f"{sample_id}_pred",
                pdflatex=pdflatex,
                dpi=args.dpi,
            )
            target = _render_latex(
                item["target"],
                work_root / f"{sample_id}_target",
                pdflatex=pdflatex,
                dpi=args.dpi,
            )
            consistency = {}
            if pred["ok"] and target["ok"]:
                consistency = compare_images(pred["image"], target["image"])
                if args.keep_images:
                    cv2.imwrite(str(image_dir / f"{sample_id}_pred.png"), pred["image"])
                    cv2.imwrite(str(image_dir / f"{sample_id}_target.png"), target["image"])
            render_rows.append(
                {
                    "sample_id": sample_id,
                    "subset": item["subset"],
                    "text_similarity": item["similarity"],
                    "compact_exact": item["compact_exact"],
                    "prediction_render_ok": pred["ok"],
                    "target_render_ok": target["ok"],
                    "both_render_ok": pred["ok"] and target["ok"],
                    "pixel_similarity": consistency.get("pixel_similarity"),
                    "global_ssim": consistency.get("global_ssim"),
                    "prediction_error": pred["error"],
                    "target_error": target["error"],
                    "prediction": item["prediction"],
                    "target": item["target"],
                }
            )

    rows_path = output_dir / "unimer_render_consistency_rows.csv"
    summary_path = output_dir / "unimer_render_consistency_summary.csv"
    report_path = output_dir / "unimer_render_consistency_report.md"
    _write_rows(rows_path, render_rows)
    summary_rows = _summary_rows(render_rows)
    _write_rows(summary_path, summary_rows)
    _write_report(report_path, summary_rows, render_rows)

    print(f"wrote {rows_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {report_path}")
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("id")): row for row in _read_jsonl(path)}


def _select_candidates(
    rows: list[dict[str, Any]],
    manifest: dict[str, dict[str, Any]],
    *,
    subset_filter: str,
    per_subset: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sample_id = str(row.get("sample_id", ""))
        target_row = manifest.get(sample_id, {})
        tags = target_row.get("tags", [])
        subset = str(tags[1]) if isinstance(tags, list) and len(tags) > 1 else "unknown"
        if subset_filter != "all" and subset != subset_filter:
            continue
        prediction = str(row.get("text", ""))
        target = str(target_row.get("target_latex", ""))
        compact_prediction = compact_latex(normalize_latex(prediction))
        compact_target = compact_latex(normalize_latex(target))
        if compact_prediction == compact_target:
            continue
        similarity = _sequence_similarity(compact_prediction, compact_target)
        if similarity < min_similarity:
            continue
        grouped[subset].append(
            {
                "sample_id": sample_id,
                "subset": subset,
                "similarity": similarity,
                "compact_exact": False,
                "prediction": prediction,
                "target": target,
            }
        )

    selected: list[dict[str, Any]] = []
    for subset in sorted(grouped):
        items = sorted(grouped[subset], key=lambda item: float(item["similarity"]), reverse=True)
        selected.extend(items[:per_subset])
    return selected


def _sequence_similarity(left: str, right: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _render_latex(
    formula: str,
    work_dir: Path,
    *,
    pdflatex: str,
    dpi: int,
) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    tex_path = work_dir / "formula.tex"
    tex_path.write_text(TEX_TEMPLATE % formula, encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                pdflatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                tex_path.name,
            ],
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
        return {"ok": False, "image": None, "error": "pdflatex timeout"}
    if proc.returncode != 0:
        return {"ok": False, "image": None, "error": _short_error(proc.stdout)}
    pdf_path = work_dir / "formula.pdf"
    if not pdf_path.exists():
        return {"ok": False, "image": None, "error": "pdflatex produced no PDF"}
    try:
        image = _pdf_to_image(pdf_path, dpi=dpi)
    except Exception as exc:
        return {"ok": False, "image": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "image": crop_ink(image), "error": ""}


def _pdf_to_image(path: Path, *, dpi: int) -> np.ndarray:
    document = fitz.open(path)
    page = document[0]
    zoom = dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height,
        pixmap.width,
        pixmap.n,
    )
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if pixmap.n == 3 else image
    document.close()
    return gray


def crop_ink(image: np.ndarray) -> np.ndarray:
    mask = image < 245
    points = np.argwhere(mask)
    if points.size == 0:
        return image
    top, left = points.min(axis=0)
    bottom, right = points.max(axis=0)
    margin = 8
    top = max(0, int(top) - margin)
    left = max(0, int(left) - margin)
    bottom = min(image.shape[0] - 1, int(bottom) + margin)
    right = min(image.shape[1] - 1, int(right) + margin)
    return image[top : bottom + 1, left : right + 1]


def compare_images(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    target_h = max(left.shape[0], right.shape[0], 1)
    target_w = max(left.shape[1], right.shape[1], 1)
    left_resized = cv2.resize(left, (target_w, target_h), interpolation=cv2.INTER_AREA)
    right_resized = cv2.resize(right, (target_w, target_h), interpolation=cv2.INTER_AREA)
    left_f = left_resized.astype(np.float32)
    right_f = right_resized.astype(np.float32)
    mae = float(np.mean(np.abs(left_f - right_f)))
    return {
        "pixel_similarity": round(max(0.0, 1.0 - mae / 255.0), 6),
        "global_ssim": round(global_ssim(left_f, right_f), 6),
    }


def global_ssim(left: np.ndarray, right: np.ndarray) -> float:
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    mu_x = float(left.mean())
    mu_y = float(right.mean())
    sigma_x = float(left.var())
    sigma_y = float(right.var())
    sigma_xy = float(((left - mu_x) * (right - mu_y)).mean())
    numerator = (2 * mu_x * mu_y + c1) * (2 * sigma_xy + c2)
    denominator = (mu_x**2 + mu_y**2 + c1) * (sigma_x + sigma_y + c2)
    return max(-1.0, min(1.0, numerator / denominator if denominator else 0.0))


def _short_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    interesting = [line for line in lines if line.startswith("!") or "Error" in line]
    return " | ".join((interesting or lines)[-3:])[:500]


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["subset"])].append(row)
        grouped["all"].append(row)
    summary: list[dict[str, Any]] = []
    for subset in ["all", "spe", "cpe", "sce", "hwe"]:
        items = grouped.get(subset, [])
        if not items:
            continue
        both = [item for item in items if item["both_render_ok"]]
        pixel = [float(item["pixel_similarity"]) for item in both if item["pixel_similarity"] is not None]
        ssim = [float(item["global_ssim"]) for item in both if item["global_ssim"] is not None]
        summary.append(
            {
                "subset": subset,
                "count": len(items),
                "prediction_render_ok": sum(1 for item in items if item["prediction_render_ok"]),
                "target_render_ok": sum(1 for item in items if item["target_render_ok"]),
                "both_render_ok": len(both),
                "both_render_rate": _rate(len(both), len(items)),
                "avg_pixel_similarity": round(mean(pixel), 6) if pixel else 0.0,
                "median_pixel_similarity": round(median(pixel), 6) if pixel else 0.0,
                "avg_global_ssim": round(mean(ssim), 6) if ssim else 0.0,
                "median_global_ssim": round(median(ssim), 6) if ssim else 0.0,
            }
        )
    return summary


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _write_report(
    path: Path,
    summary_rows: list[dict[str, Any]],
    render_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# UniMER Render Consistency Fallback",
        "",
        "This is a local render-consistency fallback, not CDM.",
        "",
        f"- Selected samples: {len(render_rows)}",
        "",
        "| Subset | Count | Both Render OK | Pixel Similarity | Global SSIM |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        lines.append(
            "| {subset} | {count} | {both_render_rate:.2%} | {median_pixel_similarity:.4f} | "
            "{median_global_ssim:.4f} |".format(**row)
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

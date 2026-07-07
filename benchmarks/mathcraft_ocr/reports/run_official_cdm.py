# coding: utf-8

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Shard:
    index: int
    start: int
    end: int
    rows: list[dict[str, str]]

    @property
    def name(self) -> str:
        return f"shard_{self.start:05d}_{self.end - 1:05d}"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Run the official UniMERNet CDM runtime in resumable shards."
    )
    parser.add_argument("--input", required=True, help="Official CDM JSON input.")
    parser.add_argument("--output-dir", required=True, help="Output directory for CDM shard runs.")
    parser.add_argument("--cdm-dir", required=True, help="Official UniMERNet cdm directory.")
    parser.add_argument("--python", required=True, help="Python executable for the official CDM runtime.")
    parser.add_argument("--path-prepend", default="", help="Extra PATH prefix for ImageMagick/Ghostscript/shims.")
    parser.add_argument("--shard-size", type=int, default=100)
    parser.add_argument("--pools", type=int, default=1)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-shards", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    cdm_dir = Path(args.cdm_dir)
    python_path = Path(args.python)

    validate_args(input_path, output_dir, cdm_dir, python_path, args.shard_size, args.pools)

    rows = read_cdm_input(input_path)
    selected_rows = select_rows(rows, args.start_offset, args.limit)
    shards = make_shards(selected_rows, args.start_offset, args.shard_size)
    if args.max_shards > 0:
        shards = shards[: args.max_shards]
    if not shards:
        raise SystemExit("No shards selected.")

    inputs_dir = output_dir / "inputs"
    summary_path = output_dir / "metrics_res.json"
    shard_csv_path = output_dir / "cdm_shard_summary.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)

    total_rows = sum(len(shard.rows) for shard in shards)
    print(
        f"[plan] input={input_path} rows={len(rows)} selected={total_rows} "
        f"shards={len(shards)} shardSize={args.shard_size} pools={args.pools}"
    )

    started_at = time.monotonic()
    processed_this_run = 0
    for shard in shards:
        shard_input = inputs_dir / f"{input_path.stem}_{shard.name}.json"
        write_shard_input(shard_input, shard.rows)
        metrics_path = shard_metrics_path(output_dir, shard_input)
        state = completed_state(metrics_path, len(shard.rows))
        if state == "complete" and not args.force:
            print(f"[skip] shard={shard.index}/{len(shards)} rows={len(shard.rows)} path={metrics_path}")
            write_combined_outputs(output_dir, input_path.stem, shards, shard_csv_path, summary_path)
            continue
        if state == "partial":
            print(f"[rerun] shard={shard.index}/{len(shards)} partial metrics={metrics_path}")

        before_percent = percent(shard.start - args.start_offset, total_rows)
        print(
            f"[run] shard={shard.index}/{len(shards)} offset={shard.start} "
            f"rows={len(shard.rows)} progress={before_percent}% -> {metrics_path.parent}"
        )
        shard_started_at = time.monotonic()
        run_official_cdm(
            python_path=python_path,
            cdm_dir=cdm_dir,
            input_path=shard_input,
            output_dir=output_dir,
            pools=args.pools,
            path_prepend=args.path_prepend,
        )
        metrics = read_metrics(metrics_path)
        write_completion_marker(metrics_path, len(shard.rows), metrics)
        elapsed = time.monotonic() - shard_started_at
        processed_this_run += len(shard.rows)
        if completed_state(metrics_path, len(shard.rows)) != "complete":
            raise RuntimeError(f"Official CDM shard did not finish cleanly: {metrics_path}")

        done_rows = min(total_rows, shard.end - args.start_offset)
        rows_per_second = speed(processed_this_run, time.monotonic() - started_at)
        eta_seconds = (total_rows - done_rows) / rows_per_second if rows_per_second > 0 else 0.0
        print(
            f"[done-shard] shard={shard.index}/{len(shards)} rows={len(shard.rows)} "
            f"elapsed={format_seconds(elapsed)} progress={percent(done_rows, total_rows)}% "
            f"speed={rows_per_second:.3f} rows/s eta={format_seconds(eta_seconds)}"
        )
        write_combined_outputs(output_dir, input_path.stem, shards, shard_csv_path, summary_path)

    combined = write_combined_outputs(output_dir, input_path.stem, shards, shard_csv_path, summary_path)
    print(
        f"[done] rows={combined['evaluated_rows']} mean_score={combined['mean_score']} "
        f"exp_rate={combined['exp_rate']} summary={summary_path}"
    )
    return 0


def validate_args(
    input_path: Path,
    output_dir: Path,
    cdm_dir: Path,
    python_path: Path,
    shard_size: int,
    pools: int,
) -> None:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not cdm_dir.exists():
        raise FileNotFoundError(cdm_dir)
    if not (cdm_dir / "evaluation.py").exists():
        raise FileNotFoundError(cdm_dir / "evaluation.py")
    if not python_path.exists():
        raise FileNotFoundError(python_path)
    if shard_size <= 0:
        raise ValueError("shard-size must be positive.")
    if pools <= 0:
        raise ValueError("pools must be positive.")
    output_dir.mkdir(parents=True, exist_ok=True)


def read_cdm_input(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise ValueError(f"CDM input must be a JSON array: {path}")
    rows: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"CDM row {index} is not an object.")
        rows.append(
            {
                "img_id": str(item.get("img_id", f"sample_{index}")),
                "gt": str(item["gt"]),
                "pred": str(item["pred"]),
            }
        )
    return rows


def select_rows(rows: list[dict[str, str]], start_offset: int, limit: int) -> list[dict[str, str]]:
    if start_offset < 0:
        raise ValueError("start-offset must be non-negative.")
    if limit < 0:
        raise ValueError("limit must be non-negative.")
    end = len(rows) if limit == 0 else min(len(rows), start_offset + limit)
    if start_offset >= end:
        return []
    return rows[start_offset:end]


def make_shards(rows: list[dict[str, str]], base_offset: int, shard_size: int) -> list[Shard]:
    shards: list[Shard] = []
    for local_start in range(0, len(rows), shard_size):
        local_end = min(len(rows), local_start + shard_size)
        shards.append(
            Shard(
                index=len(shards) + 1,
                start=base_offset + local_start,
                end=base_offset + local_end,
                rows=rows[local_start:local_end],
            )
        )
    return shards


def write_shard_input(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def shard_metrics_path(output_dir: Path, shard_input: Path) -> Path:
    return output_dir / shard_input.stem / "metrics_res.json"


def completed_state(metrics_path: Path, expected_rows: int) -> str:
    marker_path = completion_marker_path(metrics_path)
    if marker_path.exists():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return "partial"
        if int(marker.get("expected_rows", -1)) == expected_rows:
            return "complete"
        return "partial"

    if not metrics_path.exists():
        return "missing"
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return "partial"
    details = metrics.get("details", {})
    if isinstance(details, dict) and len(details) == expected_rows:
        return "complete"
    return "partial"


def read_metrics(metrics_path: Path) -> dict[str, Any]:
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    if not isinstance(metrics.get("details"), dict):
        raise ValueError(f"Official CDM metrics file has no details object: {metrics_path}")
    return metrics


def completion_marker_path(metrics_path: Path) -> Path:
    return metrics_path.parent / ".mathcraft_cdm_complete.json"


def write_completion_marker(metrics_path: Path, expected_rows: int, metrics: dict[str, Any]) -> None:
    details = metrics.get("details", {})
    marker = {
        "expected_rows": expected_rows,
        "evaluated_rows": len(details) if isinstance(details, dict) else 0,
        "metrics_path": str(metrics_path),
    }
    completion_marker_path(metrics_path).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_official_cdm(
    python_path: Path,
    cdm_dir: Path,
    input_path: Path,
    output_dir: Path,
    pools: int,
    path_prepend: str,
) -> None:
    env = os.environ.copy()
    if path_prepend:
        env["PATH"] = path_prepend + os.pathsep + env.get("PATH", "")
    command = [
        str(python_path),
        "evaluation.py",
        "-i",
        str(input_path),
        "-o",
        str(output_dir),
        "-p",
        str(pools),
    ]
    subprocess.run(command, cwd=cdm_dir, env=env, check=True)


def write_combined_outputs(
    output_dir: Path,
    input_stem: str,
    shards: list[Shard],
    shard_csv_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    shard_rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    scores: list[float] = []
    for shard in shards:
        shard_input = output_dir / "inputs" / f"{input_stem}_{shard.name}.json"
        metrics_path = shard_metrics_path(output_dir, shard_input)
        if not metrics_path.exists():
            shard_rows.append(shard_csv_row(shard, "missing", metrics_path, None))
            continue
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        shard_details = metrics.get("details", {})
        state = completed_state(metrics_path, len(shard.rows))
        shard_rows.append(shard_csv_row(shard, state, metrics_path, metrics))
        if not isinstance(shard_details, dict):
            continue
        for sample_id, sample_metrics in shard_details.items():
            details[sample_id] = sample_metrics
            try:
                scores.append(float(sample_metrics["F1_score"]))
            except (KeyError, TypeError, ValueError):
                pass

    summary = {
        "mean_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "exp_rate": round(sum(1 for score in scores if score == 1.0) / len(scores), 3) if scores else 0.0,
        "evaluated_rows": len(scores),
        "expected_rows": sum(len(shard.rows) for shard in shards),
        "completed_shards": sum(1 for row in shard_rows if row["state"] == "complete"),
        "total_shards": len(shards),
        "details": details,
    }
    write_shard_csv(shard_csv_path, shard_rows)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def shard_csv_row(
    shard: Shard,
    state: str,
    metrics_path: Path,
    metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    details = metrics.get("details", {}) if metrics else {}
    return {
        "shard": shard.index,
        "start": shard.start,
        "end_exclusive": shard.end,
        "expected_rows": len(shard.rows),
        "evaluated_rows": len(details) if isinstance(details, dict) else 0,
        "skipped_rows": len(shard.rows) - len(details) if isinstance(details, dict) else len(shard.rows),
        "state": state,
        "mean_score": metrics.get("mean_score", "") if metrics else "",
        "exp_rate": metrics.get("exp_rate", "") if metrics else "",
        "metrics_path": str(metrics_path),
    }


def write_shard_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "shard",
        "start",
        "end_exclusive",
        "expected_rows",
        "evaluated_rows",
        "skipped_rows",
        "state",
        "mean_score",
        "exp_rate",
        "metrics_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percent(done: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round(max(0, min(done, total)) / total * 100.0, 2)


def speed(done: int, elapsed_seconds: float) -> float:
    if done <= 0 or elapsed_seconds <= 0:
        return 0.0
    return done / elapsed_seconds


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# coding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mathcraft_ocr.runtime import MathCraftRuntime  # noqa: E402
from mathcraft_ocr.serialization import formula_result_to_json, mixed_result_to_json  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MathCraft OCR benchmark manifests.")
    parser.add_argument("--manifest", required=True, help="JSONL manifest path.")
    parser.add_argument("--output", required=True, help="JSONL result path.")
    parser.add_argument("--provider", default="auto", help="MathCraft provider preference.")
    parser.add_argument("--offset", type=int, default=0, help="Number of manifest rows to skip.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum rows to run. 0 means all rows.")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    samples = list(_read_jsonl(manifest_path))
    if args.offset < 0:
        raise ValueError("--offset must be non-negative")
    if args.limit < 0:
        raise ValueError("--limit must be non-negative")
    samples = samples[args.offset :]
    if args.limit:
        samples = samples[: args.limit]
    runtime = MathCraftRuntime(provider_preference=args.provider)

    with output_path.open("w", encoding="utf-8") as fh:
        for sample in samples:
            result = _run_sample(runtime, sample, args.provider, manifest_path.parent)
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
            fh.flush()

    print(f"wrote {len(samples)} results to {output_path}")
    return 0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            item = json.loads(text)
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no}: expected object")
            items.append(item)
    return items


def _run_sample(
    runtime: MathCraftRuntime,
    sample: dict[str, Any],
    provider_requested: str,
    manifest_dir: Path,
) -> dict[str, Any]:
    sample_id = str(sample.get("id", ""))
    task = str(sample.get("task", ""))
    profile = _profile_for_sample(sample)
    image_path = _resolve_path(str(sample.get("image", "")), manifest_dir)

    started = time.perf_counter()
    try:
        if profile == "formula":
            raw = runtime.recognize_formula(image_path)
            data = formula_result_to_json(raw)
            result = {
                "sample_id": sample_id,
                "task": task,
                "profile": profile,
                "image": str(image_path),
                "engine": "mathcraft_ocr",
                "provider_requested": provider_requested,
                "provider_active": data.get("provider"),
                "ok": True,
                "latency_ms": _elapsed_ms(started),
                "text": str(data.get("text", "")),
                "score": data.get("score"),
                "regions": [],
                "blocks": [],
                "errors": [],
            }
        else:
            if profile == "text":
                raw = runtime.recognize_text(image_path)
            else:
                raw = runtime.recognize_mixed(image_path)
            data = mixed_result_to_json(raw)
            result = {
                "sample_id": sample_id,
                "task": task,
                "profile": profile,
                "image": str(image_path),
                "engine": "mathcraft_ocr",
                "provider_requested": provider_requested,
                "provider_active": data.get("provider"),
                "ok": True,
                "latency_ms": _elapsed_ms(started),
                "text": str(data.get("text", "")),
                "score": None,
                "regions": data.get("regions", []),
                "blocks": data.get("blocks", []),
                "errors": [],
            }
    except Exception as exc:
        result = {
            "sample_id": sample_id,
            "task": task,
            "profile": profile,
            "image": str(image_path),
            "engine": "mathcraft_ocr",
            "provider_requested": provider_requested,
            "provider_active": None,
            "ok": False,
            "latency_ms": _elapsed_ms(started),
            "text": "",
            "score": None,
            "regions": [],
            "blocks": [],
            "errors": [f"{type(exc).__name__}: {exc}", traceback.format_exc()],
        }
    return result


def _profile_for_sample(sample: dict[str, Any]) -> str:
    profile = str(sample.get("profile", "") or "").strip().lower()
    if profile in {"formula", "text", "mixed"}:
        return profile
    task = str(sample.get("task", "") or "").strip().lower()
    if task == "formula":
        return "formula"
    if task == "text":
        return "text"
    return "mixed"


def _resolve_path(value: str, manifest_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (manifest_dir / path).resolve()


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


if __name__ == "__main__":
    raise SystemExit(main())

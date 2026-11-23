"""Measure warm v2 formula inference on single images and batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mathcraft_ocr.adapters.formula_recognizer import (  # noqa: E402
    recognize_formula_images,
)
from mathcraft_ocr.providers import detect_providers  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--images-dir", type=Path)
    parser.add_argument("--image", action="append", default=[], type=Path)
    parser.add_argument("--provider", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--native-dir", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.repeats, args.warmup, args.batch_size, args.max_new_tokens) < 1:
        parser.error("Repeats, warmup, batch size and token limit must be positive")
    import onnxruntime as ort

    dll_handle = None
    if args.native_dir is not None:
        native_dir = str(args.native_dir.resolve())
        if os.name == "nt":
            dll_handle = os.add_dll_directory(native_dir)
        ort.preload_dlls(directory=native_dir)

    paths = list(args.image)
    if args.images_dir is not None:
        paths.extend(
            path
            for path in sorted(args.images_dir.iterdir())
            if path.suffix.lower()
            in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
        )
    paths = list(dict.fromkeys(path.resolve(strict=True) for path in paths))
    if not paths:
        parser.error("At least one image is required")
    images = []
    for path in paths:
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    provider = detect_providers(args.provider)
    report = {
        "provider": provider.active_provider,
        "device": provider.device_name,
        "ort": ort.__version__,
        "repeats": args.repeats,
        "warmup": args.warmup,
        "max_new_tokens": args.max_new_tokens,
        "model_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(args.model_dir.glob("*.onnx"))
        },
        "images": [
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in paths
        ],
        "cases": [],
    }
    cases = [[index] for index in range(len(images))]
    cases += [
        list(range(start, min(start + args.batch_size, len(images))))
        for start in range(0, len(images), args.batch_size)
        if min(args.batch_size, len(images) - start) > 1
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for indices in cases:
        batch = [images[index] for index in indices]
        timings = []
        expected = None
        for iteration in range(args.warmup + args.repeats):
            started = time.perf_counter()
            result = recognize_formula_images(
                batch, args.model_dir, provider, max_new_tokens=args.max_new_tokens
            )
            elapsed = (time.perf_counter() - started) * 1000
            if expected is None:
                expected = result
            elif [item[0] for item in result] != [item[0] for item in expected]:
                raise AssertionError(
                    f"Formula text changed across repeated calls: {indices}"
                )
            if iteration >= args.warmup:
                timings.append(elapsed)
        row = {
            "images": indices,
            "batch_size": len(batch),
            "output": expected,
            "median_ms": statistics.median(timings),
            "p95_ms": sorted(timings)[math.ceil(0.95 * len(timings)) - 1],
            "formulas_per_second": len(batch) * 1000 / statistics.mean(timings),
            "samples_ms": timings,
        }
        report["cases"].append(row)
        print(
            json.dumps({key: value for key, value in row.items() if key != "output"}),
            flush=True,
        )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if dll_handle is not None:
        dll_handle.close()


if __name__ == "__main__":
    main()

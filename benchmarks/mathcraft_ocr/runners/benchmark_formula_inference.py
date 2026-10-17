"""Compare warm formula inference, including changing batch sizes and exact text."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mathcraft_ocr.adapters import formula_recognizer  # noqa: E402
from mathcraft_ocr.providers import detect_providers  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--images-dir", type=Path)
    parser.add_argument("--image", action="append", default=[], type=Path)
    parser.add_argument("--provider", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--native-dir", type=Path)
    parser.add_argument(
        "--reference",
        type=Path,
        help="Directory containing reference formula_recognizer.py and formula_inference.py.",
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.repeats, args.warmup, args.batch_size, args.max_new_tokens) < 1:
        parser.error("Repeats, warmup, batch size and token limit must be positive")
    handles = []
    if args.native_dir is not None:
        if os.name == "nt":
            handles.append(os.add_dll_directory(str(args.native_dir.resolve())))
        import onnxruntime as ort

        ort.preload_dlls(directory=str(args.native_dir.resolve()))
    implementations = {"current": formula_recognizer.recognize_formula_images}
    if args.reference is not None:
        inference_spec = importlib.util.spec_from_file_location(
            "mathcraft_ocr.adapters._benchmark_inference",
            args.reference / "formula_inference.py",
        )
        if inference_spec is None or inference_spec.loader is None:
            raise ValueError("Cannot load the reference inference implementation")
        inference = importlib.util.module_from_spec(inference_spec)
        inference_spec.loader.exec_module(inference)
        spec = importlib.util.spec_from_file_location(
            "mathcraft_ocr.adapters._benchmark_reference",
            args.reference / "formula_recognizer.py",
        )
        if spec is None or spec.loader is None:
            raise ValueError("Cannot load the reference implementation")
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        reference.__dict__["FormulaDecoder"] = inference.FormulaDecoder
        reference.__dict__["encode_formula"] = inference.encode_formula
        reference.__dict__["_load_processor"] = formula_recognizer._load_processor
        implementations = {
            "reference": reference.recognize_formula_images,
            **implementations,
        }
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
    import onnxruntime as ort

    report = {
        "provider": provider.active_provider,
        "device": provider.device_name,
        "python": sys.version,
        "ort": ort.__version__,
        "repeats": args.repeats,
        "warmup": args.warmup,
        "max_new_tokens": args.max_new_tokens,
        "implementation_sha256": hashlib.sha256(
            Path(formula_recognizer.__file__).read_bytes()
        ).hexdigest(),
        "device_io_sha256": hashlib.sha256(
            (ROOT / "mathcraft_ocr/adapters/formula_inference.py").read_bytes()
        ).hexdigest(),
        "reference_sha256": (
            {
                name: hashlib.sha256((args.reference / name).read_bytes()).hexdigest()
                for name in ("formula_recognizer.py", "formula_inference.py")
            }
            if args.reference is not None
            else None
        ),
        "model_sha256": {
            name: hashlib.sha256((args.model_dir / name).read_bytes()).hexdigest()
            for name in ("encoder_model.onnx", "decoder_model.onnx")
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
        timings = {name: [] for name in implementations}
        expected = None
        for iteration in range(args.warmup + args.repeats):
            order = list(implementations)
            if iteration % 2:
                order.reverse()
            for name in order:
                started = time.perf_counter()
                result = implementations[name](
                    batch, args.model_dir, provider, max_new_tokens=args.max_new_tokens
                )
                elapsed = (time.perf_counter() - started) * 1000
                if expected is None:
                    expected = result
                if [item[0] for item in result] != [item[0] for item in expected]:
                    raise AssertionError(f"Formula text changed: {indices}, {name}")
                np.testing.assert_allclose(
                    [item[1] for item in result],
                    [item[1] for item in expected],
                    rtol=1e-6,
                    atol=1e-7,
                    err_msg=f"Confidence changed: {indices}, {name}",
                )
                if iteration >= args.warmup:
                    timings[name].append(elapsed)
        row = {
            "images": indices,
            "batch_size": len(batch),
            "output": expected,
            "timing": {
                name: {
                    "median_ms": statistics.median(values),
                    "p95_ms": sorted(values)[math.ceil(0.95 * len(values)) - 1],
                    "samples_ms": values,
                }
                for name, values in timings.items()
            },
        }
        if args.reference is not None:
            row["reduction_percent"] = 100 * (
                1
                - row["timing"]["current"]["median_ms"]
                / row["timing"]["reference"]["median_ms"]
            )
        report["cases"].append(row)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps({key: value for key, value in row.items() if key != "output"}),
            flush=True,
        )


if __name__ == "__main__":
    main()

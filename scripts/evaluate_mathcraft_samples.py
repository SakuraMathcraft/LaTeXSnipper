# coding: utf-8
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mathcraft_ocr.latex_quality import latex_quality_flags
from mathcraft_ocr.runtime import MathCraftRuntime
from mathcraft_ocr.serialization import formula_result_to_json, mixed_result_to_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MathCraft OCR sample regression checks.")
    parser.add_argument("--samples-dir", default=str(ROOT / "test_samples"))
    parser.add_argument("--output-dir", default=str(ROOT / ".tmp" / "mathcraft_sample_regression"))
    parser.add_argument("--provider", default="cpu")
    args = parser.parse_args(argv)

    samples_dir = Path(args.samples_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime = MathCraftRuntime(provider_preference=args.provider)
    summary = []
    failures: list[str] = []
    for image_path in sorted(samples_dir.glob("*.png"), key=lambda item: item.name):
        profile = "mixed" if "混合" in image_path.stem else "formula"
        if profile == "formula":
            result = runtime.recognize_formula(image_path)
            data = formula_result_to_json(result)
        else:
            result = runtime.recognize_mixed(image_path)
            data = mixed_result_to_json(result)

        text = str(data.get("text", ""))
        data["profile"] = profile
        data["image"] = str(image_path)
        data["quality_flags"] = list(latex_quality_flags(text))
        (output_dir / f"{image_path.stem}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / f"{image_path.stem}.txt").write_text(text, encoding="utf-8")

        item = {
            "file": image_path.name,
            "profile": profile,
            "provider": data.get("provider"),
            "quality_flags": data["quality_flags"],
            "text": text,
        }
        summary.append(item)
        failures.extend(_sample_failures(item))

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"sample regression OK: {len(summary)} images -> {output_dir}")
    return 0


def _sample_failures(item: dict) -> list[str]:
    name = str(item["file"])
    text = str(item["text"])
    profile = str(item["profile"])
    quality_flags = set(item.get("quality_flags", []))
    failures: list[str] = []

    if "混合" in name and profile != "mixed":
        failures.append(f"{name}: expected mixed profile")
    if "混合" not in name and profile != "formula":
        failures.append(f"{name}: expected formula profile")
    if name == "分号-等号公式.png" and r"\begin{aligned}" in text:
        failures.append(f"{name}: compact fraction expression was split into aligned rows")
    if "对齐" in name and r"\begin{aligned}" in text and "&" not in text:
        failures.append(f"{name}: aligned formula has no alignment tabs")
    if quality_flags & {"duplicate_relation", "repeated_token_run", "excessive_repeated_token"}:
        failures.append(f"{name}: severe quality flags {sorted(quality_flags)}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())

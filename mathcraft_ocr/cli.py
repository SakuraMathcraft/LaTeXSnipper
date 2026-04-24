# coding: utf-8

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .serialization import (
    cache_state_to_json,
    doctor_report_to_json,
    formula_result_to_json,
    mixed_result_to_json,
    warmup_plan_to_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mathcraft")
    sub = parser.add_subparsers(dest="command", required=True)

    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("check")

    doctor = sub.add_parser("doctor")
    doctor.add_argument("--provider", default="auto")

    warmup = sub.add_parser("warmup")
    warmup.add_argument("--profile", default="formula")
    warmup.add_argument("--provider", default="auto")

    ocr = sub.add_parser("ocr")
    ocr.add_argument("image")
    ocr.add_argument("--profile", choices=("formula", "text", "mixed"), default="mixed")
    ocr.add_argument("--provider", default="auto")
    ocr.add_argument("--output", "-o", default="")
    ocr.add_argument("--json", action="store_true", dest="as_json")

    worker = sub.add_parser("worker")
    worker.add_argument("--provider", default="auto")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "models" and args.models_command == "check":
        from .runtime import MathCraftRuntime

        runtime = MathCraftRuntime()
        data = {
            key: cache_state_to_json(state)
            for key, state in runtime.check_models().items()
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "doctor":
        from .runtime import MathCraftRuntime

        runtime = MathCraftRuntime(provider_preference=args.provider)
        report = runtime.doctor()
        data = doctor_report_to_json(report)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "warmup":
        from .runtime import MathCraftRuntime

        runtime = MathCraftRuntime(provider_preference=args.provider)
        plan = runtime.warmup(profile=args.profile)
        data = warmup_plan_to_json(plan)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "ocr":
        from .runtime import MathCraftRuntime

        runtime = MathCraftRuntime(provider_preference=args.provider)
        profile = str(args.profile).strip().lower()
        if profile == "formula":
            result = runtime.recognize_formula(args.image)
            data = formula_result_to_json(result)
            text = result.text
        elif profile == "text":
            result = runtime.recognize_text(args.image)
            data = mixed_result_to_json(result)
            text = result.text
        else:
            result = runtime.recognize_mixed(args.image)
            data = mixed_result_to_json(result)
            text = result.text
        if args.output:
            Path(args.output).write_text(
                json.dumps(data, ensure_ascii=False, indent=2) if args.as_json else text,
                encoding="utf-8",
            )
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2) if args.as_json else text)
        return 0

    if args.command == "worker":
        from .worker import serve_jsonl

        return serve_jsonl(provider_preference=args.provider)

    parser.error("unsupported command")
    return 2

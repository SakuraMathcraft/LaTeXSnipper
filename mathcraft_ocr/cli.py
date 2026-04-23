# coding: utf-8

from __future__ import annotations

import argparse
import json

from .runtime import MathCraftRuntime
from .serialization import cache_state_to_json, doctor_report_to_json, warmup_plan_to_json
from .worker import serve_jsonl


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

    worker = sub.add_parser("worker")
    worker.add_argument("--provider", default="auto")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "models" and args.models_command == "check":
        runtime = MathCraftRuntime()
        data = {
            key: cache_state_to_json(state)
            for key, state in runtime.check_models().items()
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "doctor":
        runtime = MathCraftRuntime(provider_preference=args.provider)
        report = runtime.doctor()
        data = doctor_report_to_json(report)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "warmup":
        runtime = MathCraftRuntime(provider_preference=args.provider)
        plan = runtime.warmup(profile=args.profile)
        data = warmup_plan_to_json(plan)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.command == "worker":
        return serve_jsonl(provider_preference=args.provider)

    parser.error("unsupported command")
    return 2

# coding: utf-8

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from typing import TextIO

from .runtime import MathCraftRuntime
from .serialization import doctor_report_to_json, formula_result_to_json, mixed_result_to_json, warmup_plan_to_json


class MathCraftWorker:
    def __init__(
        self,
        *,
        provider_preference: str = "auto",
        runtime: MathCraftRuntime | None = None,
    ) -> None:
        self.runtime = runtime or MathCraftRuntime(provider_preference=provider_preference)

    def handle(self, request: dict) -> dict:
        request_id = request.get("id")
        try:
            result = self._handle_result(request)
            return {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }

    def _handle_result(self, request: dict) -> dict:
        action = str(request.get("action", "")).strip()
        if action == "doctor":
            return doctor_report_to_json(self.runtime.doctor())
        if action == "warmup":
            profile = str(request.get("profile", "formula"))
            return warmup_plan_to_json(self.runtime.warmup(profile))
        if action == "recognize_formula":
            image = _require_image(request)
            max_new_tokens = int(request.get("max_new_tokens", 256))
            return formula_result_to_json(
                self.runtime.recognize_formula(image, max_new_tokens=max_new_tokens)
            )
        if action == "recognize_text":
            image = _require_image(request)
            min_text_score = float(request.get("min_text_score", 0.45))
            return mixed_result_to_json(
                self.runtime.recognize_text(
                    image,
                    min_text_score=min_text_score,
                )
            )
        if action == "recognize_mixed":
            image = _require_image(request)
            min_text_score = float(request.get("min_text_score", 0.45))
            return mixed_result_to_json(
                self.runtime.recognize_mixed(
                    image,
                    min_text_score=min_text_score,
                )
            )
        if action == "shutdown":
            return {"shutdown": True}
        raise ValueError(f"unsupported worker action: {action}")


def serve_jsonl(
    *,
    provider_preference: str = "auto",
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    log_stream: TextIO | None = None,
) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    log_stream = log_stream or sys.stderr
    worker = MathCraftWorker(provider_preference=provider_preference)

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as exc:
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        else:
            with contextlib.redirect_stdout(log_stream):
                response = worker.handle(request)
        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()
        if response.get("ok") and response.get("result", {}).get("shutdown"):
            return 0
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mathcraft-worker")
    parser.add_argument("--provider", default="auto")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return serve_jsonl(provider_preference=args.provider)


def _require_image(request: dict):
    image = request.get("image")
    if image is None:
        raise ValueError("request field 'image' is required")
    return image


if __name__ == "__main__":
    raise SystemExit(main())

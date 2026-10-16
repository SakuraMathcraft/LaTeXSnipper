# coding: utf-8

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import traceback
from pathlib import Path
from typing import TextIO

from .runtime import FORMULA_MAX_NEW_TOKENS, MathCraftRuntime
from .manifest import load_manifest
from .protocol import WORKER_PROTOCOL, MODEL_FORMAT, validate_request
from .native_libraries import audit_private_gpu_libraries
from .serialization import doctor_report_to_json, formula_result_to_json, mixed_result_to_json, warmup_plan_to_json


_PROVIDER_HELP = "auto, cpu, gpu, cuda, tensorrt, directml, coreml, or openvino"


class MathCraftWorker:
    def __init__(
        self,
        *,
        provider_preference: str = "auto",
        runtime: MathCraftRuntime | None = None,
        native_dir: Path | None = None,
    ) -> None:
        self.runtime = runtime or MathCraftRuntime(provider_preference=provider_preference)
        self.native_dir = native_dir

    def handle(self, request: dict) -> dict:
        request_id = request.get('id') if isinstance(request, dict) else None
        try:
            validate_request(request)
            result = self._handle_result(request)
            if self.native_dir is not None and (request.get('action', '').startswith('recognize_') or (request.get('action') == 'warmup' and result.get('ready'))):
                result['native_modules'] = audit_private_gpu_libraries(self.native_dir)
            return {"protocol": WORKER_PROTOCOL, "id": request_id, "ok": True, "result": result}
        except Exception as exc:
            return {
                "protocol": WORKER_PROTOCOL,
                "id": request_id,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            }

    def _handle_result(self, request: dict) -> dict:
        action = str(request.get("action", "")).strip()
        if action == 'hello':
            import onnxruntime

            return {'worker_protocol': WORKER_PROTOCOL, 'model_format': MODEL_FORMAT,
                    'python_version': '.'.join(map(str, sys.version_info[:3])), 'ort_version': onnxruntime.__version__}
        if action == "doctor":
            return doctor_report_to_json(self.runtime.doctor())
        if action == "warmup":
            profile = str(request.get("profile", "formula"))
            return warmup_plan_to_json(self.runtime.warmup(profile))
        if action == "recognize_formula":
            image = _require_image(request)
            max_new_tokens = int(request.get("max_new_tokens", FORMULA_MAX_NEW_TOKENS))
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
            max_formula_new_tokens = int(request.get("max_formula_new_tokens", FORMULA_MAX_NEW_TOKENS))
            return mixed_result_to_json(
                self.runtime.recognize_mixed(
                    image,
                    min_text_score=min_text_score,
                    max_formula_new_tokens=max_formula_new_tokens,
                )
            )
        if action == "shutdown":
            return {"shutdown": True}
        raise ValueError(f"unsupported worker action: {action}")


def serve_jsonl(
    *,
    provider_preference: str = "auto",
    models_dir: str | None = None,
    manifest_path: str | None = None,
    cache_dir: str | None = None,
    native_dir: str | None = None,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    log_stream: TextIO | None = None,
) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    log_stream = log_stream or sys.stderr
    if native_dir is not None:
        import onnxruntime

        onnxruntime.preload_dlls(directory=native_dir)
    runtime = MathCraftRuntime(provider_preference=provider_preference, bundled_models_dir=models_dir,
                               manifest=load_manifest(manifest_path), cache_dir=cache_dir)
    worker = MathCraftWorker(runtime=runtime, native_dir=Path(native_dir) if native_dir else None)

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except Exception as exc:
            response = {
                "protocol": WORKER_PROTOCOL,
                "id": None,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
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
    parser.add_argument("--provider", default="auto", help=_PROVIDER_HELP)
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

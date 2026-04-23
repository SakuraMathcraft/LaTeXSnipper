# coding: utf-8

from __future__ import annotations

from .results import Box4P, FormulaRecognitionResult, MathCraftBlock, MixedRecognitionResult, OCRRegion


def box_to_json(box: Box4P) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in box]


def block_to_json(block: MathCraftBlock) -> dict:
    return {
        "kind": block.kind,
        "box": box_to_json(block.box),
        "text": block.text,
        "score": block.score,
    }


def region_to_json(region: OCRRegion) -> dict:
    return {
        "box": box_to_json(region.box),
        "text": region.text,
        "score": region.score,
    }


def formula_result_to_json(result: FormulaRecognitionResult) -> dict:
    return {
        "text": result.text,
        "score": result.score,
        "provider": result.provider,
    }


def mixed_result_to_json(result: MixedRecognitionResult) -> dict:
    return {
        "text": result.text,
        "regions": [region_to_json(region) for region in result.regions],
        "blocks": [block_to_json(block) for block in result.blocks],
        "provider": result.provider,
    }


def provider_info_to_json(provider_info) -> dict:
    return {
        "available_providers": list(provider_info.available_providers),
        "active_provider": provider_info.active_provider,
        "device": provider_info.device,
        "gpu_requested": provider_info.gpu_requested,
        "gpu_runtime_ok": provider_info.gpu_runtime_ok,
        "cpu_fallback": provider_info.cpu_fallback,
    }


def cache_state_to_json(state) -> dict:
    return {
        "model_id": state.model_id,
        "path": str(state.model_dir),
        "exists": state.exists,
        "complete": state.complete,
        "missing_files": list(state.missing_files),
    }


def warmup_plan_to_json(plan) -> dict:
    return {
        "profile": plan.profile,
        "required_models": list(plan.required_models),
        "missing_models": list(plan.missing_models),
        "unsupported_models": list(plan.unsupported_models),
        "component_statuses": [
            {
                "model_id": item.model_id,
                "ready": item.ready,
                "detail": item.detail,
            }
            for item in plan.component_statuses
        ],
        "ready": plan.ready,
        "provider_info": provider_info_to_json(plan.provider_info),
    }


def doctor_report_to_json(report) -> dict:
    return {
        "python_executable": report.python_executable,
        "cache_dir": str(report.cache_dir),
        "manifest_version": report.manifest_version,
        "supported_runtimes": report.supported_runtimes,
        "provider_info": provider_info_to_json(report.provider_info),
        "cache_states": {
            key: cache_state_to_json(state)
            for key, state in report.cache_states.items()
        },
    }

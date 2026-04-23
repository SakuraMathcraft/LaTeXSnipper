# coding: utf-8
# ruff: noqa: E402

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mathcraft_ocr.manifest import load_manifest
import mathcraft_ocr.runtime as runtime_mod
from mathcraft_ocr.errors import ModelCacheError
from mathcraft_ocr.layout import merge_blocks_text, split_text_box_around_formulas
from mathcraft_ocr.results import FormulaRecognitionResult, MathCraftBlock, MixedRecognitionResult
from mathcraft_ocr.runtime import (
    EN_TEXT_DETECTOR_ID,
    EN_TEXT_RECOGNIZER_ID,
    FORMULA_DETECTOR_ID,
    FORMULA_RECOGNIZER_ID,
    MathCraftRuntime,
    TEXT_DETECTOR_ID,
    TEXT_RECOGNIZER_ID,
)
from mathcraft_ocr.worker import MathCraftWorker


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _touch_model(root: Path, manifest, model_id: str) -> None:
    spec = manifest.models[model_id]
    for file_spec in spec.files:
        _touch(root / model_id / file_spec.path)


def test_manifest_loads_expected_models() -> None:
    manifest = load_manifest()
    expected = {
        FORMULA_DETECTOR_ID,
        FORMULA_RECOGNIZER_ID,
        TEXT_DETECTOR_ID,
        TEXT_RECOGNIZER_ID,
        EN_TEXT_DETECTOR_ID,
        EN_TEXT_RECOGNIZER_ID,
    }
    assert expected.issubset(manifest.models.keys())


def test_cache_inspection_marks_incomplete_model() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _touch(root / FORMULA_RECOGNIZER_ID / "encoder_model.onnx")
        runtime = MathCraftRuntime(cache_dir=root, manifest=manifest, provider_preference="cpu")
        state = runtime.check_models()[FORMULA_RECOGNIZER_ID]
        assert state.exists is True
        assert state.complete is False
        assert "decoder_model.onnx" in state.missing_files


def test_formula_warmup_plan_reports_missing_models() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runtime = MathCraftRuntime(
            cache_dir=root,
            manifest=manifest,
            provider_preference="cpu",
        )
        plan = runtime.warmup("formula")
        assert plan.profile == "formula"
        assert FORMULA_DETECTOR_ID in plan.missing_models
        assert FORMULA_RECOGNIZER_ID in plan.missing_models
        assert plan.ready is False
        assert plan.unsupported_models == ()


def test_mixed_profile_declares_real_required_models() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu")
        plan = runtime.warmup("mixed")
        assert plan.required_models == (
            FORMULA_DETECTOR_ID,
            FORMULA_RECOGNIZER_ID,
            TEXT_DETECTOR_ID,
            TEXT_RECOGNIZER_ID,
        )


def test_table_profile_reports_removed_runtime() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest)
        try:
            runtime.warmup("table")
        except ModelCacheError:
            pass
        else:
            raise AssertionError("table profile should not be available in ONNX-only MathCraft")


def test_formula_warmup_succeeds_with_stubbed_onnx_handlers() -> None:
    manifest = load_manifest()
    old_handlers = dict(runtime_mod.ONNX_WARMUP_HANDLERS)
    calls = []
    runtime_mod.ONNX_WARMUP_HANDLERS = {
        FORMULA_DETECTOR_ID: lambda model_dir, provider_info: calls.append(
            ("mfd", Path(model_dir).name)
        ),
        FORMULA_RECOGNIZER_ID: lambda model_dir, provider_info: calls.append(
            ("mfr", Path(model_dir).name)
        ),
        TEXT_DETECTOR_ID: old_handlers[TEXT_DETECTOR_ID],
        TEXT_RECOGNIZER_ID: old_handlers[TEXT_RECOGNIZER_ID],
        EN_TEXT_DETECTOR_ID: old_handlers[EN_TEXT_DETECTOR_ID],
        EN_TEXT_RECOGNIZER_ID: old_handlers[EN_TEXT_RECOGNIZER_ID],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / FORMULA_DETECTOR_ID / "mathcraft-mfd-1.5.onnx")
            _touch_model(root, manifest, FORMULA_RECOGNIZER_ID)
            runtime = MathCraftRuntime(cache_dir=root, manifest=manifest, provider_preference="cpu")
            plan = runtime.warmup("formula")
            assert plan.ready is True
            assert plan.missing_models == ()
            assert plan.unsupported_models == ()
            assert ("mfd", FORMULA_DETECTOR_ID) in calls
            assert ("mfr", FORMULA_RECOGNIZER_ID) in calls
    finally:
        runtime_mod.ONNX_WARMUP_HANDLERS = old_handlers


def test_recognize_formula_uses_formula_adapter() -> None:
    manifest = load_manifest()
    old_warmup = MathCraftRuntime.warmup
    old_recognize = runtime_mod.recognize_formula_image
    try:
        def _fake_warmup(self, profile: str = "formula"):
            report = self.get_runtime_info()
            return runtime_mod.WarmupPlan(
                profile=profile,
                required_models=(FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID),
                missing_models=(),
                unsupported_models=(),
                component_statuses=(),
                provider_info=report.provider_info,
                ready=True,
            )

        MathCraftRuntime.warmup = _fake_warmup
        runtime_mod.recognize_formula_image = (
            lambda image, model_dir, provider_info, max_new_tokens=256: ("x+y", 0.91)
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu")
            result = runtime.recognize_formula(np.zeros((32, 64, 3), dtype=np.uint8))
            assert isinstance(result, FormulaRecognitionResult)
            assert result.text == "x+y"
            assert result.score == 0.91
    finally:
        MathCraftRuntime.warmup = old_warmup
        runtime_mod.recognize_formula_image = old_recognize


def test_recognize_mixed_uses_text_pipeline() -> None:
    manifest = load_manifest()
    old_warmup = MathCraftRuntime.warmup
    old_warmup_selected = MathCraftRuntime._warmup_selected_models
    old_select = MathCraftRuntime._select_mixed_text_models
    old_detect = runtime_mod.detect_text_boxes
    old_detect_formula = runtime_mod.detect_formula_boxes
    old_recognize_lines = runtime_mod.recognize_pp_text_lines
    old_crop = runtime_mod.get_rotate_crop_image
    try:
        def _fake_warmup(self, profile: str = "mixed"):
            report = self.get_runtime_info()
            return runtime_mod.WarmupPlan(
                profile=profile,
                required_models=(
                    FORMULA_DETECTOR_ID,
                    FORMULA_RECOGNIZER_ID,
                    EN_TEXT_DETECTOR_ID,
                    EN_TEXT_RECOGNIZER_ID,
                    TEXT_DETECTOR_ID,
                    TEXT_RECOGNIZER_ID,
                ),
                missing_models=(),
                unsupported_models=(),
                component_statuses=(),
                provider_info=report.provider_info,
                ready=True,
            )

        MathCraftRuntime.warmup = _fake_warmup
        MathCraftRuntime._warmup_selected_models = (
            lambda self, profile, model_ids: _fake_warmup(self, profile)
        )
        MathCraftRuntime._select_mixed_text_models = lambda self, ocr_profile: (
            TEXT_DETECTOR_ID,
            TEXT_RECOGNIZER_ID,
            runtime_mod.recognize_pp_text_lines,
        )
        runtime_mod.detect_text_boxes = (
            lambda image, model_dir, provider_info: (
                np.asarray(
                    [
                        [[0, 0], [10, 0], [10, 10], [0, 10]],
                        [[20, 20], [40, 20], [40, 30], [20, 30]],
                    ],
                    dtype=np.float32,
                ),
                (0.9, 0.8),
            )
        )
        runtime_mod.detect_formula_boxes = lambda image, model_dir, provider_info: ()
        runtime_mod.get_rotate_crop_image = (
            lambda image, box: np.zeros((8, 8, 3), dtype=np.uint8)
        )
        runtime_mod.recognize_pp_text_lines = (
            lambda crops, model_dir, provider_info: [("alpha", 0.95), ("beta", 0.88)]
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu")
            result = runtime.recognize_mixed(np.zeros((32, 64, 3), dtype=np.uint8))
            assert isinstance(result, MixedRecognitionResult)
            assert result.text == "alpha\nbeta"
            assert len(result.regions) == 2
            assert len(result.blocks) == 2
            assert result.blocks[0].kind == "text"
            assert result.regions[0].text == "alpha"
    finally:
        MathCraftRuntime.warmup = old_warmup
        MathCraftRuntime._warmup_selected_models = old_warmup_selected
        MathCraftRuntime._select_mixed_text_models = old_select
        runtime_mod.detect_text_boxes = old_detect
        runtime_mod.detect_formula_boxes = old_detect_formula
        runtime_mod.recognize_pp_text_lines = old_recognize_lines
        runtime_mod.get_rotate_crop_image = old_crop


def test_layout_splits_text_box_around_formula() -> None:
    text_box = ((0.0, 0.0), (100.0, 0.0), (100.0, 20.0), (0.0, 20.0))
    formula_box = ((40.0, 2.0), (60.0, 2.0), (60.0, 18.0), (40.0, 18.0))
    segments = split_text_box_around_formulas(text_box, (formula_box,))
    assert len(segments) == 2
    assert segments[0].box == ((0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0))
    assert segments[1].box == ((60.0, 0.0), (100.0, 0.0), (100.0, 20.0), (60.0, 20.0))


def test_layout_merges_inline_formula_with_text() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0)),
            text="let",
            score=0.9,
        ),
        MathCraftBlock(
            kind="embedding",
            box=((40.0, 0.0), (70.0, 0.0), (70.0, 20.0), (40.0, 20.0)),
            text="x ^ { 2 }",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((80.0, 0.0), (120.0, 0.0), (120.0, 20.0), (80.0, 20.0)),
            text="work",
            score=0.9,
        ),
    )
    assert merge_blocks_text(blocks) == "let $x ^ { 2 }$ work"


def test_worker_serializes_formula_result() -> None:
    class _FakeRuntime:
        def recognize_formula(self, image, *, max_new_tokens=256):
            assert image == "sample.png"
            assert max_new_tokens == 12
            return FormulaRecognitionResult(
                text="x+y",
                score=0.9,
                provider="CPUExecutionProvider",
            )

    worker = MathCraftWorker(runtime=_FakeRuntime())
    response = worker.handle(
        {
            "id": "1",
            "action": "recognize_formula",
            "image": "sample.png",
            "max_new_tokens": 12,
        }
    )
    assert response["ok"] is True
    assert response["id"] == "1"
    assert response["result"]["text"] == "x+y"
    assert response["result"]["provider"] == "CPUExecutionProvider"


def test_worker_reports_unsupported_action() -> None:
    worker = MathCraftWorker(runtime=object())  # type: ignore[arg-type]
    response = worker.handle({"id": "bad", "action": "missing"})
    assert response["ok"] is False
    assert response["id"] == "bad"
    assert response["error"]["type"] == "ValueError"


def main() -> None:
    tests = [
        test_manifest_loads_expected_models,
        test_cache_inspection_marks_incomplete_model,
        test_formula_warmup_plan_reports_missing_models,
        test_mixed_profile_declares_real_required_models,
        test_table_profile_reports_removed_runtime,
        test_formula_warmup_succeeds_with_stubbed_onnx_handlers,
        test_recognize_formula_uses_formula_adapter,
        test_recognize_mixed_uses_text_pipeline,
        test_layout_splits_text_box_around_formula,
        test_layout_merges_inline_formula_with_text,
        test_worker_serializes_formula_result,
        test_worker_reports_unsupported_action,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} tests OK")


if __name__ == "__main__":
    main()

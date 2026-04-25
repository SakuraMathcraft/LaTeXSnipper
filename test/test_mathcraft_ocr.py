# coding: utf-8
# ruff: noqa: E402

from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mathcraft_ocr.manifest import load_manifest
import mathcraft_ocr.hardware as hardware_mod
import mathcraft_ocr.runtime as runtime_mod
from mathcraft_ocr.errors import ModelCacheError
from mathcraft_ocr.hardware import HardwareInfo, choose_rec_batch_num
from mathcraft_ocr.layout import (
    annotate_blocks,
    is_informative_ocr_box,
    merge_blocks_text,
    resolve_formula_text_conflicts,
    split_text_box_around_formulas,
)
from mathcraft_ocr.providers import ProviderInfo
from mathcraft_ocr.results import FormulaRecognitionResult, MathCraftBlock, MixedRecognitionResult
from mathcraft_ocr.serialization import block_to_json
from mathcraft_ocr.cache import resolve_model_roots
from mathcraft_ocr.runtime import (
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
            auto_download=False,
        )
        plan = runtime.warmup("formula")
        assert plan.profile == "formula"
        assert FORMULA_DETECTOR_ID in plan.missing_models
        assert FORMULA_RECOGNIZER_ID in plan.missing_models
        assert plan.ready is False
        assert plan.unsupported_models == ()


def test_warmup_auto_downloads_missing_models_before_handlers() -> None:
    manifest = load_manifest()
    old_download = runtime_mod.download_model_archive
    old_handlers = dict(runtime_mod.ONNX_WARMUP_HANDLERS)
    downloaded = []
    warmed = []

    def _fake_download(spec, *, target_root, timeout=120, source_overrides=None):
        downloaded.append((spec.model_id, timeout))
        _touch_model(Path(target_root), manifest, spec.model_id)
        return Path(target_root) / spec.model_id

    try:
        runtime_mod.download_model_archive = _fake_download
        runtime_mod.ONNX_WARMUP_HANDLERS = {
            FORMULA_DETECTOR_ID: lambda model_dir, provider_info: warmed.append(Path(model_dir).name),
            FORMULA_RECOGNIZER_ID: lambda model_dir, provider_info: warmed.append(Path(model_dir).name),
            TEXT_DETECTOR_ID: old_handlers[TEXT_DETECTOR_ID],
            TEXT_RECOGNIZER_ID: old_handlers[TEXT_RECOGNIZER_ID],
        }
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu")
            plan = runtime.warmup("formula")
            assert plan.ready is True
            assert downloaded == [(FORMULA_DETECTOR_ID, 120), (FORMULA_RECOGNIZER_ID, 120)]
            assert warmed == [FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID]
            assert len(plan.cache_events) == 4
            assert FORMULA_RECOGNIZER_ID in plan.cache_events[2]
            assert "missing:" in plan.cache_events[2]
    finally:
        runtime_mod.download_model_archive = old_download
        runtime_mod.ONNX_WARMUP_HANDLERS = old_handlers


def test_mixed_profile_declares_real_required_models() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu", auto_download=False)
        plan = runtime.warmup("mixed")
        assert plan.required_models == (
            FORMULA_DETECTOR_ID,
            FORMULA_RECOGNIZER_ID,
            TEXT_DETECTOR_ID,
            TEXT_RECOGNIZER_ID,
        )


def test_text_profile_declares_text_models_only() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu", auto_download=False)
        plan = runtime.warmup("text")
        assert plan.required_models == (
            TEXT_DETECTOR_ID,
            TEXT_RECOGNIZER_ID,
        )
        assert FORMULA_DETECTOR_ID not in plan.required_models
        assert FORMULA_RECOGNIZER_ID not in plan.required_models


def test_table_profile_reports_removed_runtime() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as tmp:
        runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, auto_download=False)
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
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / FORMULA_DETECTOR_ID / "mathcraft-mfd.onnx")
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


def test_successful_warmup_plan_is_cached_per_profile() -> None:
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
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_model(root, manifest, FORMULA_DETECTOR_ID)
            _touch_model(root, manifest, FORMULA_RECOGNIZER_ID)
            runtime = MathCraftRuntime(cache_dir=root, manifest=manifest, provider_preference="cpu")
            first = runtime.warmup("formula")
            second = runtime.warmup("formula")
            assert first.ready is True
            assert second is first
            assert calls == [
                ("mfd", FORMULA_DETECTOR_ID),
                ("mfr", FORMULA_RECOGNIZER_ID),
            ]
    finally:
        runtime_mod.ONNX_WARMUP_HANDLERS = old_handlers


def test_failed_warmup_plan_is_not_cached() -> None:
    manifest = load_manifest()
    old_handlers = dict(runtime_mod.ONNX_WARMUP_HANDLERS)
    calls = []

    def _fail(model_dir, provider_info):
        calls.append(Path(model_dir).name)
        raise RuntimeError("warmup failed")

    runtime_mod.ONNX_WARMUP_HANDLERS = {
        FORMULA_DETECTOR_ID: _fail,
        FORMULA_RECOGNIZER_ID: old_handlers[FORMULA_RECOGNIZER_ID],
        TEXT_DETECTOR_ID: old_handlers[TEXT_DETECTOR_ID],
        TEXT_RECOGNIZER_ID: old_handlers[TEXT_RECOGNIZER_ID],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_model(root, manifest, FORMULA_DETECTOR_ID)
            _touch_model(root, manifest, FORMULA_RECOGNIZER_ID)
            runtime = MathCraftRuntime(cache_dir=root, manifest=manifest, provider_preference="cpu")
            first = runtime.warmup("formula")
            second = runtime.warmup("formula")
            assert first.ready is False
            assert second.ready is False
            assert calls == [FORMULA_DETECTOR_ID, FORMULA_DETECTOR_ID]
    finally:
        runtime_mod.ONNX_WARMUP_HANDLERS = old_handlers


def test_runtime_prefers_complete_bundled_models_over_empty_user_cache() -> None:
    manifest = load_manifest()
    with tempfile.TemporaryDirectory() as bundled_tmp, tempfile.TemporaryDirectory() as user_tmp:
        bundled_root = Path(bundled_tmp)
        user_root = Path(user_tmp)
        _touch_model(bundled_root, manifest, FORMULA_DETECTOR_ID)
        runtime = MathCraftRuntime(
            cache_dir=user_root,
            bundled_models_dir=bundled_root,
            manifest=manifest,
            provider_preference="cpu",
        )
        state = runtime.check_models()[FORMULA_DETECTOR_ID]
        assert state.complete is True
        assert state.model_dir == bundled_root / FORMULA_DETECTOR_ID
        assert not (user_root / FORMULA_DETECTOR_ID).exists()


def test_env_bundled_models_root_precedes_user_cache() -> None:
    with tempfile.TemporaryDirectory() as bundled_tmp, tempfile.TemporaryDirectory() as user_tmp:
        bundled_root = Path(bundled_tmp)
        user_root = Path(user_tmp)
        old_value = os.environ.get("MATHCRAFT_BUNDLED_MODELS_DIR")
        os.environ["MATHCRAFT_BUNDLED_MODELS_DIR"] = str(bundled_root)
        try:
            roots = resolve_model_roots(cache_dir=user_root)
        finally:
            if old_value is None:
                os.environ.pop("MATHCRAFT_BUNDLED_MODELS_DIR", None)
            else:
                os.environ["MATHCRAFT_BUNDLED_MODELS_DIR"] = old_value
        assert roots[0] == bundled_root
        assert roots[1] == user_root


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
        runtime_mod.detect_text_boxes = (
            lambda image, model_dir, provider_info, **kwargs: (
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
            lambda crops, model_dir, provider_info, **kwargs: [("alpha", 0.95), ("beta", 0.88)]
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
        runtime_mod.detect_text_boxes = old_detect
        runtime_mod.detect_formula_boxes = old_detect_formula
        runtime_mod.recognize_pp_text_lines = old_recognize_lines
        runtime_mod.get_rotate_crop_image = old_crop


def test_recognize_text_skips_formula_pipeline() -> None:
    manifest = load_manifest()
    old_warmup_selected = MathCraftRuntime._warmup_selected_models
    old_detect = runtime_mod.detect_text_boxes
    old_detect_formula = runtime_mod.detect_formula_boxes
    old_recognize_lines = runtime_mod.recognize_pp_text_lines
    old_crop = runtime_mod.get_rotate_crop_image
    try:
        def _fake_warmup_selected(self, profile: str, model_ids):
            report = self.get_runtime_info()
            assert profile == "text"
            assert FORMULA_DETECTOR_ID not in model_ids
            assert FORMULA_RECOGNIZER_ID not in model_ids
            return runtime_mod.WarmupPlan(
                profile=profile,
                required_models=tuple(model_ids),
                missing_models=(),
                unsupported_models=(),
                component_statuses=(),
                provider_info=report.provider_info,
                ready=True,
            )

        MathCraftRuntime._warmup_selected_models = _fake_warmup_selected
        runtime_mod.detect_formula_boxes = (
            lambda image, model_dir, provider_info: (_ for _ in ()).throw(
                AssertionError("formula detector should not run in text mode")
            )
        )
        runtime_mod.detect_text_boxes = (
            lambda image, model_dir, provider_info, **kwargs: (
                np.asarray([[[0, 0], [12, 0], [12, 8], [0, 8]]], dtype=np.float32),
                (0.9,),
            )
        )
        runtime_mod.get_rotate_crop_image = (
            lambda image, box: np.zeros((8, 8, 3), dtype=np.uint8)
        )
        runtime_mod.recognize_pp_text_lines = (
            lambda crops, model_dir, provider_info, **kwargs: [("plain text", 0.96)]
        )
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MathCraftRuntime(cache_dir=tmp, manifest=manifest, provider_preference="cpu")
            result = runtime.recognize_text(np.zeros((32, 64, 3), dtype=np.uint8))
            assert isinstance(result, MixedRecognitionResult)
            assert result.text == "plain text"
            assert len(result.blocks) == 1
            assert result.blocks[0].kind == "text"
    finally:
        MathCraftRuntime._warmup_selected_models = old_warmup_selected
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


def test_layout_annotates_blocks_with_page_aware_reading_order() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((620.0, 100.0), (760.0, 100.0), (760.0, 120.0), (620.0, 120.0)),
            text="right one",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 200.0), (240.0, 200.0), (240.0, 220.0), (100.0, 220.0)),
            text="left two",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((620.0, 200.0), (760.0, 200.0), (760.0, 220.0), (620.0, 220.0)),
            text="right two",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 100.0), (240.0, 100.0), (240.0, 120.0), (100.0, 120.0)),
            text="left one",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=3)
    assert [block.text for block in ordered] == [
        "left one",
        "left two",
        "right one",
        "right two",
    ]
    assert [block.reading_order for block in ordered] == [0, 1, 2, 3]
    assert all(block.page_index == 3 for block in ordered)


def test_layout_keeps_centered_display_formula_in_main_flow() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((100.0, 100.0), (240.0, 100.0), (240.0, 120.0), (100.0, 120.0)),
            text="left one",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((620.0, 100.0), (760.0, 100.0), (760.0, 120.0), (620.0, 120.0)),
            text="right one",
            score=0.9,
        ),
        MathCraftBlock(
            kind="isolated",
            box=((420.0, 150.0), (580.0, 150.0), (580.0, 190.0), (420.0, 190.0)),
            text="x = y",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 220.0), (240.0, 220.0), (240.0, 240.0), (100.0, 240.0)),
            text="left two",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=1)
    assert [block.text for block in ordered] == [
        "left one",
        "x = y",
        "left two",
        "right one",
    ]
    assert ordered[1].is_display is True


def test_layout_marks_roles_columns_and_paragraphs() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((380.0, 30.0), (620.0, 30.0), (620.0, 50.0), (380.0, 50.0)),
            text="CHAPTER 3. GROUPS 34",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 120.0), (360.0, 120.0), (360.0, 150.0), (100.0, 150.0)),
            text="1 Introduction",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 220.0), (480.0, 220.0), (480.0, 245.0), (100.0, 245.0)),
            text="This paragraph continues",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 252.0), (520.0, 252.0), (520.0, 277.0), (100.0, 277.0)),
            text="on the next line.",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((480.0, 1150.0), (520.0, 1150.0), (520.0, 1170.0), (480.0, 1170.0)),
            text="34",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=2)
    by_text = {block.text: block for block in ordered}
    assert by_text["CHAPTER 3. GROUPS 34"].role == "header"
    assert by_text["34"].role == "page_number"
    assert by_text["1 Introduction"].role == "heading"
    assert by_text["This paragraph continues"].role == "paragraph"
    assert by_text["This paragraph continues"].paragraph_id == by_text["on the next line."].paragraph_id
    assert by_text["This paragraph continues"].column == 0


def test_layout_keeps_two_columns_separate_when_formulas_overlap_vertically() -> None:
    blocks = (
        MathCraftBlock(
            kind="isolated",
            box=((100.0, 200.0), (490.0, 200.0), (490.0, 520.0), (100.0, 520.0)),
            text=r"\begin{aligned} x &= y \end{aligned}",
            score=0.9,
        ),
        MathCraftBlock(
            kind="isolated",
            box=((505.0, 220.0), (920.0, 220.0), (920.0, 500.0), (505.0, 500.0)),
            text=r"\begin{aligned} a &= b \end{aligned}",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=1)
    assert [block.column for block in ordered] == [0, 1]
    assert [block.line_id for block in ordered] == [0, 1]
    assert all(block.is_display for block in ordered)


def test_layout_keeps_single_column_inline_formula_line_across_midline() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((100.0, 200.0), (560.0, 200.0), (560.0, 230.0), (100.0, 230.0)),
            text="Let",
            score=0.9,
        ),
        MathCraftBlock(
            kind="embedding",
            box=((560.0, 200.0), (700.0, 200.0), (700.0, 230.0), (560.0, 230.0)),
            text="x \\in X",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((700.0, 200.0), (920.0, 200.0), (920.0, 230.0), (700.0, 230.0)),
            text="be compact.",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=1)
    assert len({block.line_id for block in ordered}) == 1
    assert all(block.column == 0 for block in ordered)
    assert merge_blocks_text(ordered) == "Let $x \\in X$ be compact."


def test_layout_marks_formula_adjacent_short_text_as_anchor_or_label() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((100.0, 120.0), (170.0, 120.0), (170.0, 145.0), (100.0, 145.0)),
            text="where",
            score=0.9,
        ),
        MathCraftBlock(
            kind="isolated",
            box=((180.0, 150.0), (520.0, 150.0), (520.0, 300.0), (180.0, 300.0)),
            text=r"\begin{aligned} x &= y \end{aligned}",
            score=0.9,
            source="formula_rec",
        ),
        MathCraftBlock(
            kind="text",
            box=((540.0, 190.0), (585.0, 190.0), (585.0, 215.0), (540.0, 215.0)),
            text="(16)",
            score=0.9,
        ),
    )
    resolved = resolve_formula_text_conflicts(blocks, image_size=(1000, 1200))
    ordered = annotate_blocks(resolved, image_size=(1000, 1200), page_index=1)
    by_text = {block.text: block for block in ordered}
    assert by_text["where"].role == "formula_anchor"
    assert by_text["(16)"].role == "formula_label"
    assert by_text[r"\begin{aligned} x &= y \end{aligned}"].is_display is True


def test_layout_marks_journal_running_header() -> None:
    blocks = (
        MathCraftBlock(
            kind="text",
            box=((100.0, 35.0), (310.0, 35.0), (310.0, 62.0), (100.0, 62.0)),
            text="AUTHOR et al.: TITLE",
            score=0.9,
        ),
        MathCraftBlock(
            kind="text",
            box=((100.0, 160.0), (340.0, 160.0), (340.0, 190.0), (100.0, 190.0)),
            text="Body starts here.",
            score=0.9,
        ),
    )
    ordered = annotate_blocks(blocks, image_size=(1000, 1200), page_index=2)
    by_text = {block.text: block for block in ordered}
    assert by_text["AUTHOR et al.: TITLE"].role == "header"
    assert "AUTHOR et al.: TITLE" not in merge_blocks_text(ordered)


def test_informative_ocr_box_rejects_blank_and_tiny_crops() -> None:
    blank = np.full((64, 64, 3), 255, dtype=np.uint8)
    ink = blank.copy()
    ink[20:40, 20:44] = 0
    assert not is_informative_ocr_box(
        blank,
        ((10.0, 10.0), (40.0, 10.0), (40.0, 40.0), (10.0, 40.0)),
    )
    assert not is_informative_ocr_box(
        ink,
        ((20.0, 20.0), (22.0, 20.0), (22.0, 22.0), (20.0, 22.0)),
    )
    assert is_informative_ocr_box(
        ink,
        ((18.0, 18.0), (46.0, 18.0), (46.0, 42.0), (18.0, 42.0)),
    )


def test_block_serialization_preserves_structured_fields() -> None:
    block = MathCraftBlock(
        kind="isolated",
        box=((10.0, 20.0), (90.0, 20.0), (90.0, 50.0), (10.0, 50.0)),
        text="x = y",
        score=0.91,
        source="formula_rec",
        page_index=2,
        image_size=(100, 200),
        line_id=4,
        reading_order=7,
        is_display=True,
        role="formula",
        column=0,
        paragraph_id=3,
        confidence_flags=("display_formula", "low_score"),
    )
    payload = block_to_json(block)
    assert payload["source"] == "formula_rec"
    assert payload["page_index"] == 2
    assert payload["image_size"] == [100, 200]
    assert payload["line_id"] == 4
    assert payload["reading_order"] == 7
    assert payload["is_display"] is True
    assert payload["role"] == "formula"
    assert payload["column"] == 0
    assert payload["paragraph_id"] == 3
    assert payload["confidence_flags"] == ["display_formula", "low_score"]


def test_hardware_batch_policy_prefers_larger_gpu_batches() -> None:
    provider = ProviderInfo(
        available_providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
        active_provider="CUDAExecutionProvider",
        device="gpu",
        gpu_requested=True,
        gpu_runtime_ok=True,
        cpu_fallback=False,
    )
    assert choose_rec_batch_num(
        provider,
        HardwareInfo(
            logical_processors=12,
            total_memory_mb=24000,
            free_memory_mb=12000,
            gpu_name="NVIDIA",
            gpu_total_memory_mb=6141,
            gpu_free_memory_mb=5103,
            gpu_driver_version="595.97",
        ),
    ) == 12


def test_hardware_batch_policy_uses_total_vram_when_free_vram_unknown() -> None:
    provider = ProviderInfo(
        available_providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
        active_provider="CUDAExecutionProvider",
        device="gpu",
        gpu_requested=True,
        gpu_runtime_ok=True,
        cpu_fallback=False,
    )
    assert choose_rec_batch_num(
        provider,
        HardwareInfo(
            logical_processors=12,
            total_memory_mb=24000,
            free_memory_mb=12000,
            gpu_name="NVIDIA GeForce RTX 4050 Laptop GPU",
            gpu_total_memory_mb=4095,
            gpu_free_memory_mb=0,
            gpu_driver_version="32.0.15.9597",
        ),
    ) == 8


def test_hardware_video_controller_payload_parser() -> None:
    name, total_mb, driver = hardware_mod._parse_video_controller_payload(
        {
            "Name": "NVIDIA GeForce RTX 4050 Laptop GPU",
            "AdapterRAM": 4293918720,
            "DriverVersion": "32.0.15.9597",
        }
    )
    assert name == "NVIDIA GeForce RTX 4050 Laptop GPU"
    assert total_mb == 4095
    assert driver == "32.0.15.9597"


def test_hardware_batch_policy_keeps_cpu_batches_moderate() -> None:
    provider = ProviderInfo(
        available_providers=("CPUExecutionProvider",),
        active_provider="CPUExecutionProvider",
        device="cpu",
        gpu_requested=False,
        gpu_runtime_ok=False,
        cpu_fallback=False,
    )
    assert choose_rec_batch_num(
        provider,
        HardwareInfo(
            logical_processors=12,
            total_memory_mb=24000,
            free_memory_mb=12000,
        ),
    ) == 8


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
        test_warmup_auto_downloads_missing_models_before_handlers,
        test_mixed_profile_declares_real_required_models,
        test_text_profile_declares_text_models_only,
        test_table_profile_reports_removed_runtime,
        test_formula_warmup_succeeds_with_stubbed_onnx_handlers,
        test_successful_warmup_plan_is_cached_per_profile,
        test_failed_warmup_plan_is_not_cached,
        test_runtime_prefers_complete_bundled_models_over_empty_user_cache,
        test_recognize_formula_uses_formula_adapter,
        test_recognize_mixed_uses_text_pipeline,
        test_recognize_text_skips_formula_pipeline,
        test_layout_splits_text_box_around_formula,
        test_layout_merges_inline_formula_with_text,
        test_layout_annotates_blocks_with_page_aware_reading_order,
        test_layout_keeps_centered_display_formula_in_main_flow,
        test_layout_marks_roles_columns_and_paragraphs,
        test_layout_keeps_two_columns_separate_when_formulas_overlap_vertically,
        test_layout_keeps_single_column_inline_formula_line_across_midline,
        test_layout_marks_formula_adjacent_short_text_as_anchor_or_label,
        test_layout_marks_journal_running_header,
        test_informative_ocr_box_rejects_blank_and_tiny_crops,
        test_block_serialization_preserves_structured_fields,
        test_hardware_batch_policy_prefers_larger_gpu_batches,
        test_hardware_batch_policy_uses_total_vram_when_free_vram_unknown,
        test_hardware_video_controller_payload_parser,
        test_hardware_batch_policy_keeps_cpu_batches_moderate,
        test_worker_serializes_formula_result,
        test_worker_reports_unsupported_action,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} tests OK")


if __name__ == "__main__":
    main()

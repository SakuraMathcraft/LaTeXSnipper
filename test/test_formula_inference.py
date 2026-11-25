"""Test greedy decoding across the two v2 cache contracts."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import numpy as np
import pytest

from mathcraft_ocr.adapters.formula_inference import CpuDecoder
from mathcraft_ocr.adapters.formula_recognizer import _generate_formula_tokens


class ScriptedDecoder:
    def __init__(self, finishes, *, compact):
        self.finishes = np.asarray(finishes)
        self.batches = []
        self.allow_compaction = compact

    def compact(self, rows):
        if self.allow_compaction:
            self.finishes = self.finishes[rows]
        return self.allow_compaction

    def step(self, ids, position):
        self.batches.append(len(ids))
        return np.where(position < self.finishes, 4, 2), np.full(len(ids), 0.75)


@pytest.mark.parametrize("finishes", [(1, 3), (3, 1), (3, 3), (4, 2, 1)])
def test_shrinking_active_batch_preserves_token_sequences(finishes):
    shrinking = ScriptedDecoder(finishes, compact=True)
    fixed = ScriptedDecoder(finishes, compact=False)
    args = dict(
        batch_size=len(finishes), decoder_start_id=2, eos_id=2, max_new_tokens=8
    )
    expected = _generate_formula_tokens(shrinking, **args)
    actual = _generate_formula_tokens(fixed, **args)
    assert actual[0] == expected[0] == [[4] * count for count in finishes]
    assert actual[1] == expected[1] == [[0.75] * count for count in finishes]
    assert actual[2].tolist() == expected[2].tolist() == [False] * len(finishes)
    assert fixed.batches == [len(finishes)] * (max(finishes) + 1)
    assert sum(shrinking.batches) == sum(finishes) + len(finishes)


def test_token_loop_and_budget_are_enforced_for_a_fixed_batch():
    decoder = ScriptedDecoder((100,), compact=False)
    args = dict(batch_size=1, decoder_start_id=2, eos_id=2)
    tokens, _, repeated = _generate_formula_tokens(decoder, **args, max_new_tokens=80)
    assert tokens == [[4]]
    assert repeated.tolist() == [True]
    tokens, _, repeated = _generate_formula_tokens(decoder, **args, max_new_tokens=3)
    assert tokens == [[4, 4, 4]]
    assert repeated.tolist() == [False]


def test_cpu_feeds_next_cache_and_compacts_cross_and_self_attention():
    class Stage:
        def __init__(self, input_name, output_name, result):
            self.input_name = input_name
            self.output_name = output_name
            self.result = result

        def get_inputs(self):
            return [SimpleNamespace(name=self.input_name)]

        def get_outputs(self):
            return [SimpleNamespace(name=self.output_name)]

        def run(self, _outputs, inputs):
            assert set(inputs) == {self.input_name}
            return [self.result]

    class Step:
        def get_inputs(self):
            return [SimpleNamespace(name="past_self_key.0")]

        def run(self, outputs, inputs):
            assert outputs == ["logits", "present_self_key.0"]
            past = inputs["past_self_key.0"]
            batch = len(inputs["input_ids"])
            assert batch == len(inputs["cross_key.0"]) == len(past)
            present = np.concatenate(
                (past, np.ones((batch, 8, 1, 32), np.float32)), axis=2
            )
            return np.tile(
                np.array([[0.0, 1.0]], dtype=np.float32), (batch, 1)
            ), present

    images = np.zeros((2, 3, 384, 384), dtype=np.float32)
    encoder = Stage("pixel_values", "hidden", np.zeros((2, 578, 384), dtype=np.float32))
    cross = Stage("hidden", "cross_key.0", np.zeros((2, 8, 578, 32), dtype=np.float32))
    decoder = CpuDecoder((encoder, cross, Step()), images)
    tokens, confidence = decoder.step(np.zeros((2, 1), dtype=np.int64), 0)
    assert tokens.tolist() == [1, 1]
    np.testing.assert_allclose(confidence, 1.0 / (1.0 + np.exp(-1.0)))
    decoder.compact(np.array([1]))
    decoder.step(np.ones((1, 1), dtype=np.int64), 1)
    assert decoder.cache["cross_key.0"].shape == (1, 8, 578, 32)
    assert decoder.cache["past_self_key.0"].shape == (1, 8, 2, 32)


@pytest.mark.parametrize("dynamic_fp32", [False, True])
def test_cache_row_selection_preserves_each_cache_layout(dynamic_fp32):
    if importlib.util.find_spec("onnxruntime") is None:
        pytest.skip("ONNX Runtime is unavailable")
    # Load the native runtime in its own process, like the desktop OCR worker.
    code = dedent("""\
        import sys
        import numpy as np
        import onnxruntime as ort

        sys.path.insert(0, sys.argv[1])
        from mathcraft_ocr.adapters.formula_model import cache_row_selection_model

        dynamic_fp32 = sys.argv[2] == "True"
        dtype = np.float32 if dynamic_fp32 else np.float16
        session = ort.InferenceSession(
            cache_row_selection_model(2, 1, dynamic_fp32=dynamic_fp32),
            providers=["CPUExecutionProvider"]
        )
        cross_key = np.arange(24, dtype=dtype).reshape(3, 2, 2, 2)
        cross_value = cross_key + 100
        self_cache = (
            cross_key + 200 if dynamic_fp32
            else np.arange(48, dtype=dtype).reshape(2, 3, 2, 2, 2)
        )
        rows = np.array([0, 2], dtype=np.int64)
        selected = session.run(None, {
            "rows": rows, "cache_0": cross_key, "cache_1": cross_value, "cache_2": self_cache,
        })
        np.testing.assert_array_equal(selected[0], cross_key[rows])
        np.testing.assert_array_equal(selected[1], cross_value[rows])
        np.testing.assert_array_equal(
            selected[2], self_cache[rows] if dynamic_fp32 else self_cache[:, rows]
        )
        """)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-c",
            code,
            str(Path(__file__).parents[1]),
            str(dynamic_fp32),
        ],
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr

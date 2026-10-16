# pyright: reportMissingImports=false

import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def _nonblank_test_image() -> Image.Image:
    image = Image.new("RGB", (64, 32), "white")
    for x in range(8, 56):
        image.putpixel((x, 16), (0, 0, 0))
    return image


class TestMathcraftBackend(unittest.TestCase):
    def test_worker_handshake_is_available_to_diagnostics_until_stopped(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        hello = {'worker_protocol': 1, 'model_format': 1, 'python_version': '3.11.17', 'ort_version': '1.26.0'}
        responses = [
            {'protocol': 1, 'id': 'mathcraft-1', 'ok': True, 'result': hello},
            {'protocol': 1, 'id': 'mathcraft-2', 'ok': True, 'result': {'ready': True}},
        ]
        wrapper._worker = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('\n'.join(json.dumps(item) for item in responses) + '\n'))
        wrapper._ensure_worker = lambda: True
        try:
            assert wrapper._send_worker_request({'action': 'warmup'}) == {'ready': True}
            assert wrapper.runtime_info == hello
        finally:
            wrapper._worker = None
            wrapper.stop()
        assert wrapper.runtime_info == {}

    def test_unknown_modes_are_rejected(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        with self.assertRaises(ValueError):
            wrapper._mode_for_model("unknown_mode")

    def test_model_wrapper_uses_extended_formula_decode_budget(self):
        from backend.mathcraft.model import (
            FORMULA_RECOGNITION_MAX_NEW_TOKENS,
            ModelWrapper,
        )

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("formula")
        requests = []

        def _fake_request(payload, timeout_sec=300.0):
            requests.append(dict(payload))
            return {"text": "x", "score": 0.9}

        wrapper._send_worker_request = _fake_request
        wrapper.predict_result(_nonblank_test_image(), model_name="mathcraft")

        self.assertEqual(
            requests[-1]["max_new_tokens"], FORMULA_RECOGNITION_MAX_NEW_TOKENS
        )

    def test_model_wrapper_uses_extended_mixed_formula_decode_budget(self):
        from backend.mathcraft.model import (
            FORMULA_RECOGNITION_MAX_NEW_TOKENS,
            ModelWrapper,
        )

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("mixed")
        requests = []

        def _fake_request(payload, timeout_sec=600.0):
            requests.append(dict(payload))
            return {"text": "x"}

        wrapper._send_worker_request = _fake_request
        wrapper.predict_result(_nonblank_test_image(), model_name="mathcraft_mixed")

        self.assertEqual(
            requests[-1]["max_formula_new_tokens"],
            FORMULA_RECOGNITION_MAX_NEW_TOKENS,
        )

    def test_model_wrapper_skips_near_blank_images_before_worker_request(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("formula")

        def _fail_request(*_args, **_kwargs):
            raise AssertionError("blank images should not be sent to MathCraft worker")

        wrapper._send_worker_request = _fail_request
        result = wrapper.predict_result(
            Image.new("RGB", (128, 64), "white"), model_name="mathcraft"
        )

        self.assertEqual(result["text"], "")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["empty_reason"], "empty_image")

    def test_model_wrapper_filters_degenerate_formula_decoder_loop(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("formula")
        repeated = (
            r"\fbox { \displaystyle \partial _ { \phi } "
            + (r"\chi _ { \pm } " * 30)
            + "}"
        )

        def _fake_request(_payload, timeout_sec=300.0):
            return {"text": repeated, "score": 0.91}

        image = _nonblank_test_image()
        wrapper._send_worker_request = _fake_request
        result = wrapper.predict_result(image, model_name="mathcraft")

        self.assertEqual(result["text"], "")
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["empty_reason"], "degenerate_formula_output")

    def test_model_wrapper_keeps_non_degenerate_formula_text(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("formula")

        def _fake_request(_payload, timeout_sec=300.0):
            return {"text": r"\int _ { 0 } ^ { 1 } x ^ { 2 } dx", "score": 0.91}

        image = _nonblank_test_image()
        wrapper._send_worker_request = _fake_request
        result = wrapper.predict_result(image, model_name="mathcraft")

        self.assertEqual(result["text"], r"\int _ { 0 } ^ { 1 } x ^ { 2 } dx")
        self.assertNotIn("empty_reason", result)

    def test_model_wrapper_predict_empty_hint_has_no_render_brackets(self):
        from backend.mathcraft.model import ModelWrapper

        wrapper = ModelWrapper(auto_warmup=False)
        wrapper._ready_modes.add("formula")

        self.assertEqual(
            wrapper.predict(
                Image.new("RGB", (128, 64), "white"), model_name="mathcraft"
            ),
            "未识别到公式内容",
        )

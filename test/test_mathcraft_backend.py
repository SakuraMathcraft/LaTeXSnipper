# pyright: reportMissingImports=false

import io
import json
import sys
import time
import unittest
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
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
        hello = {
            "worker_protocol": 1,
            "model_format": 1,
            "python_version": "3.11.17",
            "ort_version": "1.26.0",
        }
        responses = [
            {"protocol": 1, "id": "mathcraft-1", "ok": True, "result": hello},
            {"protocol": 1, "id": "mathcraft-2", "ok": True, "result": {"ready": True}},
        ]
        wrapper._worker = SimpleNamespace(
            stdin=io.StringIO(),
            stdout=io.StringIO(
                "\n".join(json.dumps(item) for item in responses) + "\n"
            ),
        )
        wrapper._ensure_worker = lambda: True
        try:
            assert wrapper._send_worker_request({"action": "warmup"}) == {"ready": True}
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


@pytest.mark.parametrize("blocked_action", ["hello", "warmup", "recognize_text"])
def test_stopping_worker_cancels_inflight_work_and_allows_recovery(
    tmp_path, monkeypatch, caplog, blocked_action
):
    from backend.mathcraft.model import ModelWrapper

    marker = tmp_path / "request-started"
    code = """
import json, sys, time
from pathlib import Path
marker = Path(sys.argv[1])
for line in sys.stdin:
    request = json.loads(line)
    action = request['action']
    if action == sys.argv[2] and not marker.exists():
        marker.write_text(action, encoding='utf-8')
        time.sleep(30)
    if action == 'hello':
        result = {'worker_protocol': 1, 'model_format': 1}
    elif action == 'warmup':
        result = {'ready': True, 'provider_info': {'active_provider': 'CPUExecutionProvider'}}
    else:
        result = {'text': 'recovered'}
    print(json.dumps({'protocol': 1, 'id': request['id'], 'ok': True, 'result': result}), flush=True)
"""
    wrapper = ModelWrapper(auto_warmup=False)
    monkeypatch.setattr(
        wrapper,
        "_worker_argv",
        lambda: [
            sys.executable,
            "-X",
            "utf8",
            "-u",
            "-c",
            code,
            str(marker),
            blocked_action,
        ],
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        operation = (
            (lambda: wrapper.predict_result(_nonblank_test_image(), "mathcraft_text"))
            if blocked_action == "recognize_text"
            else lambda: wrapper.warmup("mathcraft_text")
        )
        future = pool.submit(operation)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists(), (
                "Worker did not reach the requested cancellation stage"
            )
            wrapper.stop()
            with pytest.raises(CancelledError):
                future.result(timeout=3)
            assert not wrapper.is_ready() and not wrapper.is_model_ready(
                "mathcraft_text"
            )
            assert wrapper.get_failure_info() == {} and wrapper.get_error() is None
            assert "预热失败" not in caplog.text
            assert (
                wrapper.predict_result(_nonblank_test_image(), "mathcraft_text")["text"]
                == "recovered"
            )
        finally:
            wrapper.stop()


def test_unexpected_worker_exit_is_still_reported_as_failure(monkeypatch, caplog):
    from backend.mathcraft.model import ModelWrapper

    wrapper = ModelWrapper(auto_warmup=False)
    monkeypatch.setattr(
        wrapper,
        "_worker_argv",
        lambda: [sys.executable, "-X", "utf8", "-c", "import sys; sys.exit(1)"],
    )
    try:
        assert not wrapper.warmup("mathcraft_text")
        assert wrapper.get_error() and wrapper.get_failure_info()
        assert "预热失败" in caplog.text and "exit_code=1" in caplog.text
    finally:
        wrapper.stop()

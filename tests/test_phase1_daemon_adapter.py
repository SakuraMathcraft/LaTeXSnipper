import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.proc = type("P", (), {"pid": 1234})()
        self.started = False
        self.stopped = False
        self.calls = []
        self.last_error = None

    def start(self, timeout_sec: float = 15.0) -> bool:
        self.started = True
        return True

    def stop(self, force: bool = False) -> None:
        self.stopped = True

    def request(self, method, params=None, timeout_sec=30.0, autostart=True):
        self.calls.append((method, params or {}))
        if method == "warmup":
            return {"ok": True, "ready": True}
        if method == "predict_image":
            return {"ok": True, "result": "ok-formula"}
        if method == "shutdown":
            return {"ok": True}
        if method == "health":
            return {"ok": True, "ready": True}
        return {"ok": False, "error": "unknown method", "error_type": "NotImplementedError"}

    def submit_task(self, kind, params=None, timeout_sec=15.0):
        self.calls.append(("task_submit", {"kind": kind, "params": params or {}}))
        return "task-1"

    def wait_task(
        self,
        task_id,
        timeout_sec=300.0,
        poll_interval_sec=0.2,
        progress_cb=None,
        cancel_cb=None,
    ):
        if callable(progress_cb):
            progress_cb(1, 1, {"status": "success"})
        return {"status": "success", "output": {"result": "ok-formula", "content": "ok-pdf"}}

    def cancel_task(self, task_id, timeout_sec=5.0):
        self.calls.append(("task_cancel", {"task_id": task_id}))
        return True


class Phase1DaemonAdapterTests(unittest.TestCase):
    def test_adapter_warmup_predict_and_shutdown(self):
        with mock.patch("backend.model_daemon_adapter.LocalDaemonClient", _FakeClient):
            from backend.model_daemon_adapter import DaemonModelWrapper

            w = DaemonModelWrapper("pix2text")
            self.assertTrue(w.is_ready())
            out = w.predict(Image.new("RGB", (2, 2), "white"), model_name="pix2text")
            self.assertEqual(out, "ok-formula")
            pdf = w.predict_pdf(
                pdf_path="dummy.pdf",
                max_pages=1,
                model_name="pix2text_mixed",
                output_format="markdown",
                dpi=200,
            )
            self.assertEqual(pdf, "ok-pdf")
            w._stop_pix2text_worker()
            self.assertFalse(w.is_ready())


if __name__ == "__main__":
    unittest.main()

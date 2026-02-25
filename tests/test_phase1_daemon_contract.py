import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from PIL import Image

import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backend.daemon_protocol import recv_line, send_line
from backend.daemon_server import _RequestHandler, _State, _ThreadingTCPServer


class _FakeWrapper:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.ready = False
        self.last_used_model = None

    def is_ready(self) -> bool:
        return bool(self.ready)

    def get_status_text(self) -> str:
        return "model ready" if self.ready else "model not loaded"

    def _lazy_load_pix2text(self) -> bool:
        self.ready = True
        return True

    def predict(self, pil_img: Image.Image, model_name: str = "pix2text") -> str:
        self.last_used_model = model_name
        w, h = pil_img.size
        return f"pred:{model_name}:{w}x{h}"


class Phase1DaemonContractTests(unittest.TestCase):
    def _rpc(self, host: str, port: int, token: str, method: str, params=None):
        with socket.create_connection((host, port), timeout=3.0) as sock:
            send_line(
                sock,
                {
                    "token": token,
                    "method": method,
                    "params": params or {},
                },
            )
            return recv_line(sock)

    def test_health_warmup_predict_shutdown(self):
        state = _State(model_name="pix2text", token="secret", wrapper=_FakeWrapper("pix2text"))
        with _ThreadingTCPServer(("127.0.0.1", 0), _RequestHandler) as srv:
            state.server_ref = srv
            srv.state = state  # type: ignore[attr-defined]
            host, port = srv.server_address
            t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            t.start()
            try:
                health = self._rpc(host, port, "secret", "health")
                self.assertTrue(health["ok"])
                self.assertFalse(health["ready"])

                warmup = self._rpc(host, port, "secret", "warmup")
                self.assertTrue(warmup["ok"])
                self.assertTrue(warmup["ready"])

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    image_path = tmp.name
                try:
                    img = Image.new("RGB", (4, 3), "white")
                    img.save(image_path, format="PNG")
                    pred = self._rpc(
                        host,
                        port,
                        "secret",
                        "predict_image",
                        {"image_path": image_path, "model_name": "pix2text_mixed"},
                    )
                    self.assertTrue(pred["ok"])
                    self.assertEqual(pred["result"], "pred:pix2text_mixed:4x3")
                finally:
                    try:
                        os.unlink(image_path)
                    except Exception:
                        pass

                shutdown = self._rpc(host, port, "secret", "shutdown")
                self.assertTrue(shutdown["ok"])
            finally:
                try:
                    state.stop()
                except Exception:
                    pass
                srv.shutdown()
                t.join(timeout=1.5)
                srv.server_close()

    def test_unauthorized_and_missing_image_error(self):
        state = _State(model_name="pix2text", token="secret", wrapper=_FakeWrapper("pix2text"))
        with _ThreadingTCPServer(("127.0.0.1", 0), _RequestHandler) as srv:
            state.server_ref = srv
            srv.state = state  # type: ignore[attr-defined]
            host, port = srv.server_address
            t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            t.start()
            try:
                unauthorized = self._rpc(host, port, "wrong-token", "health")
                self.assertFalse(unauthorized["ok"])
                self.assertEqual(unauthorized.get("error_type"), "PermissionError")

                missing = self._rpc(
                    host,
                    port,
                    "secret",
                    "predict_image",
                    {"image_path": "Z:/__not_exists__.png", "model_name": "pix2text"},
                )
                self.assertFalse(missing["ok"])
                self.assertEqual(missing.get("error_type"), "FileNotFoundError")
            finally:
                try:
                    state.stop()
                except Exception:
                    pass
                srv.shutdown()
                t.join(timeout=1.5)
                srv.server_close()

    def test_task_queue_predict_image(self):
        state = _State(model_name="pix2text", token="secret", wrapper=_FakeWrapper("pix2text"))
        with _ThreadingTCPServer(("127.0.0.1", 0), _RequestHandler) as srv:
            state.server_ref = srv
            srv.state = state  # type: ignore[attr-defined]
            host, port = srv.server_address
            t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            t.start()
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    image_path = tmp.name
                try:
                    img = Image.new("RGB", (7, 5), "white")
                    img.save(image_path, format="PNG")
                    submit = self._rpc(
                        host,
                        port,
                        "secret",
                        "task_submit",
                        {"kind": "predict_image", "params": {"image_path": image_path, "model_name": "pix2text"}},
                    )
                    self.assertTrue(submit["ok"])
                    task_id = submit.get("task_id")
                    self.assertTrue(task_id)

                    status = {}
                    for _ in range(40):
                        status = self._rpc(host, port, "secret", "task_status", {"task_id": task_id})
                        self.assertTrue(status["ok"])
                        if status.get("task", {}).get("status") == "success":
                            break
                    self.assertEqual(status.get("task", {}).get("status"), "success")
                    out = status.get("task", {}).get("output", {})
                    self.assertEqual(out.get("result"), "pred:pix2text:7x5")
                finally:
                    try:
                        os.unlink(image_path)
                    except Exception:
                        pass
            finally:
                try:
                    state.stop()
                except Exception:
                    pass
                srv.shutdown()
                t.join(timeout=1.5)
                srv.server_close()


if __name__ == "__main__":
    unittest.main()

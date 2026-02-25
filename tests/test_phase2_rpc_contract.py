import json
import socket
import threading
import unittest
from pathlib import Path

import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backend.daemon_protocol import recv_line, send_line
from backend.daemon_server import _RequestHandler, _State, _ThreadingTCPServer
from backend.rpc_contract import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    METHOD_HEALTH,
    METHOD_TASK_CANCEL,
    METHOD_TASK_STATUS,
    METHOD_TASK_SUBMIT,
    METHODS,
    TASK_KINDS,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_ERROR,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
    method_params_required,
)


class _DummyWrapper:
    def is_ready(self):
        return True

    def get_status_text(self):
        return "ok"

    def _lazy_load_pix2text(self):
        return True

    def predict(self, pil_img, model_name="pix2text"):
        return "ok"


class Phase2RpcContractTests(unittest.TestCase):
    def test_contract_json_file_exists(self):
        p = Path("contracts/daemon_rpc_contract.v1.json")
        self.assertTrue(p.exists())
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), CONTRACT_NAME)
        self.assertEqual(data.get("version"), CONTRACT_VERSION)
        self.assertIn("methods", data.get("enums", {}))

    def test_frozen_enums_and_required_params(self):
        self.assertIn(METHOD_HEALTH, METHODS)
        self.assertIn(METHOD_TASK_SUBMIT, METHODS)
        self.assertIn(METHOD_TASK_STATUS, METHODS)
        self.assertIn(METHOD_TASK_CANCEL, METHODS)

        self.assertIn("predict_image", TASK_KINDS)
        self.assertIn("predict_pdf", TASK_KINDS)

        self.assertEqual(method_params_required(METHOD_TASK_SUBMIT), ("kind", "params"))
        self.assertEqual(method_params_required(METHOD_TASK_STATUS), ("task_id",))
        self.assertEqual(method_params_required(METHOD_TASK_CANCEL), ("task_id",))

        # task status freeze
        statuses = {
            TASK_STATUS_QUEUED,
            TASK_STATUS_RUNNING,
            TASK_STATUS_SUCCESS,
            TASK_STATUS_ERROR,
            TASK_STATUS_CANCELLED,
        }
        self.assertEqual(len(statuses), 5)

    def test_health_returns_contract_version(self):
        state = _State(model_name="pix2text", token="s", wrapper=_DummyWrapper())
        with _ThreadingTCPServer(("127.0.0.1", 0), _RequestHandler) as srv:
            state.server_ref = srv
            srv.state = state  # type: ignore[attr-defined]
            host, port = srv.server_address
            t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
            t.start()
            try:
                with socket.create_connection((host, port), timeout=3.0) as sock:
                    send_line(sock, {"token": "s", "method": METHOD_HEALTH, "params": {}})
                    resp = recv_line(sock)
                self.assertTrue(resp.get("ok"))
                contract = resp.get("contract", {})
                self.assertEqual(contract.get("name"), CONTRACT_NAME)
                self.assertEqual(contract.get("version"), CONTRACT_VERSION)
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

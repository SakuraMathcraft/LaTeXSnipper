# coding: utf-8

from __future__ import annotations

import json
import urllib.error
import urllib.request

from integration.office import OfficeBridgeServer
from integration.office.bridge_auth import OfficeBridgeAuth
from integration.office.bridge_contracts import OfficeBridgeError


def test_office_bridge_auth_requires_bearer_token() -> None:
    auth = OfficeBridgeAuth("secret-token")

    assert auth.verify_authorization("Bearer secret-token")
    assert not auth.verify_authorization(None)
    assert not auth.verify_authorization("secret-token")
    assert not auth.verify_authorization("Bearer wrong-token")


def test_office_bridge_health_and_config() -> None:
    server = OfficeBridgeServer(auth=OfficeBridgeAuth("test-token"))
    server.start()
    try:
        health = _get_json(f"{server.base_url}/health")
        assert health["ok"] is True
        assert health["result"] == {"name": "LaTeXSnipper Office Bridge"}

        config = _get_json(f"{server.base_url}/config")
        assert config["ok"] is True
        assert config["result"]["bridge_url"] == server.base_url
        assert config["result"]["token"] == "test-token"

    finally:
        server.stop()


def test_office_bridge_default_host_reports_loopback_url() -> None:
    server = OfficeBridgeServer(port=0, auth=OfficeBridgeAuth("test-token"))
    server.start()
    try:
        assert server.base_url.startswith("http://127.0.0.1:")
    finally:
        server.stop()


def test_office_bridge_localhost_host_reports_localhost_url() -> None:
    server = OfficeBridgeServer(host="localhost", port=0, auth=OfficeBridgeAuth("test-token"))
    server.start()
    try:
        assert server.base_url.startswith("http://localhost:")
        health = _get_json(f"{server.base_url}/health")
        assert health["ok"] is True
    finally:
        server.stop()


def test_office_bridge_screenshot_ocr_uses_injected_service() -> None:
    class RecognitionService:
        def recognition_status(self) -> dict:
            return {"state": "recognizing"}

        def recognize_screenshot(self, payload: dict) -> dict:
            assert payload["timeout"] == 10
            return {"latex": "x^2"}

        def cancel_screenshot(self) -> dict:
            return {"canceled": True}

    server = OfficeBridgeServer(
        auth=OfficeBridgeAuth("test-token"),
        recognition_service=RecognitionService(),
    )
    server.start()
    try:
        status = _post_json(
            f"{server.base_url}/recognition/status",
            {},
            token="test-token",
        )
        assert status["status"] == 200
        assert status["payload"]["result"]["state"] == "recognizing"

        result = _post_json(
            f"{server.base_url}/recognize/screenshot",
            {"timeout": 10},
            token="test-token",
        )
        assert result["status"] == 200
        assert result["payload"]["result"]["latex"] == "x^2"

        canceled = _post_json(
            f"{server.base_url}/recognize/screenshot/cancel",
            {},
            token="test-token",
        )
        assert canceled["status"] == 200
        assert canceled["payload"]["result"]["canceled"] is True
    finally:
        server.stop()


def test_office_bridge_screenshot_ocr_returns_contract_errors() -> None:
    class RecognitionService:
        def recognize_screenshot(self, _payload: dict) -> dict:
            raise OfficeBridgeError(
                408,
                "screenshot_ocr_timeout",
                "Screenshot OCR timed out. Start Screenshot OCR again and complete a screenshot in LaTeXSnipper.",
            )

    server = OfficeBridgeServer(
        auth=OfficeBridgeAuth("test-token"),
        recognition_service=RecognitionService(),
    )
    server.start()
    try:
        result = _post_json(
            f"{server.base_url}/recognize/screenshot",
            {"timeout": 10},
            token="test-token",
        )
        assert result["status"] == 408
        assert result["payload"]["error"]["code"] == "screenshot_ocr_timeout"
        assert "Start Screenshot OCR again" in result["payload"]["error"]["message"]
    finally:
        server.stop()


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {
                "status": response.status,
                "payload": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "payload": json.loads(exc.read().decode("utf-8")),
        }

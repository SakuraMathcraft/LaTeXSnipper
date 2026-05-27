# coding: utf-8

from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

import pytest

from integration.office import OfficeBridgeServer
from integration.office.bridge_auth import OfficeBridgeAuth
from integration.office.conversion_service import OfficeConversionService


def test_office_bridge_auth_requires_bearer_token() -> None:
    auth = OfficeBridgeAuth("secret-token")

    assert auth.verify_authorization("Bearer secret-token")
    assert not auth.verify_authorization(None)
    assert not auth.verify_authorization("secret-token")
    assert not auth.verify_authorization("Bearer wrong-token")


def test_office_conversion_service_uses_injected_converters() -> None:
    service = OfficeConversionService(
        normalize_latex=lambda value: value.strip("$"),
        latex_to_omml=lambda value: f"<omml>{value}</omml>",
        latex_to_svg=lambda value: f"<svg>{value}</svg>",
    )

    result = service.convert({"latex": "$x^2$", "targets": ["omml", "svg"]})

    assert result["latex"] == "x^2"
    assert result["omml"] == "<omml>x^2</omml>"
    assert result["svg"] == "<svg>x^2</svg>"
    assert result["warnings"] == []


def test_office_conversion_service_rejects_unknown_targets() -> None:
    service = OfficeConversionService()

    with pytest.raises(ValueError, match="unsupported conversion target"):
        service.convert({"latex": "x", "targets": ["docx"]})


def test_office_bridge_health_and_authenticated_conversion() -> None:
    service = OfficeConversionService(
        normalize_latex=lambda value: value,
        latex_to_omml=lambda value: f"<omml>{value}</omml>",
        latex_to_svg=lambda value: f"<svg>{value}</svg>",
    )
    server = OfficeBridgeServer(auth=OfficeBridgeAuth("test-token"), conversion_service=service)
    server.start()
    try:
        health = _get_json(f"{server.base_url}/health")
        assert health["ok"] is True
        assert health["result"] == {"name": "LaTeXSnipper Office Bridge"}

        config = _get_json(f"{server.base_url}/config")
        assert config["ok"] is True
        assert config["result"]["bridge_url"] == server.base_url
        assert config["result"]["token"] == "test-token"

        unauth = _post_json(f"{server.base_url}/convert/latex", {"latex": "x"})
        assert unauth["status"] == 401
        assert unauth["payload"]["error"]["code"] == "unauthorized"

        converted = _post_json(
            f"{server.base_url}/convert/latex",
            {"latex": "x", "targets": ["omml", "svg"]},
            token="test-token",
        )
        assert converted["status"] == 200
        assert converted["payload"]["result"]["omml"] == "<omml>x</omml>"
        assert converted["payload"]["result"]["svg"] == "<svg>x</svg>"
    finally:
        server.stop()


def test_office_bridge_screenshot_ocr_uses_injected_service() -> None:
    class RecognitionService:
        def recognition_status(self) -> dict:
            return {"state": "recognizing"}

        def recognize_screenshot(self, payload: dict) -> dict:
            assert payload["timeout"] == 10
            return {"latex": "x^2"}

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
    finally:
        server.stop()


def test_office_bridge_serves_installed_addin_site(tmp_path: Path) -> None:
    (tmp_path / "taskpane.html").write_text("<html>office</html>", encoding="utf-8")
    server = OfficeBridgeServer(site_root=tmp_path)
    server.start()
    try:
        with urllib.request.urlopen(f"{server.base_url}/taskpane.html?host=word", timeout=5) as response:
            assert response.read().decode("utf-8") == "<html>office</html>"
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

from __future__ import annotations

from pathlib import Path
import sys

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_external_model_defaults_match_ollama_url() -> None:
    from backend.external_model.schemas import ExternalModelConfig, load_config_from_mapping

    assert ExternalModelConfig().normalized_provider() == "ollama"

    config = load_config_from_mapping({})
    assert config.normalized_provider() == "ollama"
    assert config.normalized_base_url() == "http://127.0.0.1:11434"


def test_default_external_model_connection_uses_ollama_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.external_model.client import ExternalModelClient
    from backend.external_model.schemas import load_config_from_mapping

    requested_urls: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"models": [{"name": "qwen2.5vl:7b"}]}

    def fake_get(url: str, **_kwargs):
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    config = load_config_from_mapping({"external_model_model_name": "qwen2.5vl:7b"})

    ok, _message = ExternalModelClient(config).test_connection()

    assert ok is True
    assert requested_urls == ["http://127.0.0.1:11434/api/tags"]


def test_mineru_health_check_rejects_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.external_model.errors import ExternalModelConnectionError
    from backend.external_model.mineru_client import MineruClient
    from backend.external_model.schemas import ExternalModelConfig

    def fake_get(url: str, **_kwargs):
        response = requests.Response()
        response.status_code = 404
        response.url = url
        response._content = b'{"detail":"missing"}'
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    config = ExternalModelConfig(provider="mineru", base_url="http://127.0.0.1:8000")

    with pytest.raises(ExternalModelConnectionError, match="接口路径不存在"):
        MineruClient(config).test_connection()

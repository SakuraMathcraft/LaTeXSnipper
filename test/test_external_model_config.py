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


def test_external_model_api_key_is_saved_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.external_model import schemas
    from backend.external_model.schemas import ExternalModelConfig, load_config_from_mapping

    monkeypatch.setattr(schemas, "encrypt_secret", lambda value: f"enc:{value}")
    monkeypatch.setattr(schemas, "decrypt_secret", lambda value: value.removeprefix("enc:"))

    data = ExternalModelConfig(api_key="secret-token").to_mapping()

    assert data["external_model_api_key_enc"] == "enc:secret-token"
    assert "external_model_api_key" not in data
    assert load_config_from_mapping(data).normalized_api_key() == "secret-token"
    assert load_config_from_mapping({"external_model_api_key": "legacy-token"}).normalized_api_key() == ""


def test_openai_compatible_400_includes_response_detail() -> None:
    from backend.external_model.client import ExternalModelClient
    from backend.external_model.schemas import ExternalModelConfig

    response = requests.Response()
    response.status_code = 400
    response._content = b'{"error":{"message":"image input is not supported by this model"}}'
    error = requests.HTTPError(response=response)
    message = ExternalModelClient(ExternalModelConfig())._format_request_error(
        error,
        "外部模型请求",
        "https://api.example.com/v1/chat/completions",
    )

    assert "接口返回 400" in message
    assert "image input is not supported" in message


def test_openai_compatible_text_only_schema_error_is_clear() -> None:
    from backend.external_model.client import ExternalModelClient
    from backend.external_model.schemas import ExternalModelConfig

    response = requests.Response()
    response.status_code = 400
    response._content = (
        b'{"error":{"message":"Failed to deserialize the JSON body into the target type: '
        b"messages[0]: unknown variant `image_url`, expected `text` at line 1 column 54657\"}}"
    )
    error = requests.HTTPError(response=response)
    message = ExternalModelClient(ExternalModelConfig())._format_request_error(
        error,
        "外部模型请求",
        "https://api.example.com/v1/chat/completions",
    )

    assert "不支持图片输入" in message
    assert "服务端信息" not in message


def test_openai_compatible_accepts_base_url_with_v1_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.external_model.client import ExternalModelClient
    from backend.external_model.schemas import load_config_from_mapping

    requested_urls: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"id": "vision-model"}]}

    def fake_get(url: str, **_kwargs):
        requested_urls.append(url)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    config = load_config_from_mapping(
        {
            "external_model_provider": "openai_compatible",
            "external_model_base_url": "https://openrouter.ai/api/v1",
            "external_model_model_name": "vision-model",
        }
    )

    ok, _message = ExternalModelClient(config).test_connection()

    assert ok is True
    assert requested_urls == ["https://openrouter.ai/api/v1/models"]


def test_recommended_presets_only_include_strong_vision_options() -> None:
    from backend.external_model.presets import PRESET_ITEMS

    preset_ids = [key for key, _label in PRESET_ITEMS]

    assert preset_ids == ["glm_ocr", "paddleocr_vl", "qwen_vl", "mineru_native"]
    assert "ollama_vision" not in preset_ids


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

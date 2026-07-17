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


@pytest.mark.parametrize(
    ("prompt_template", "output_mode"),
    [
        ("ocr_formula_v1", "latex"),
        ("ocr_markdown_v1", "markdown"),
        ("ocr_text_v1", "text"),
        ("ocr_handwriting_mixed_v1", "markdown"),
        ("ocr_document_page_v1", "markdown"),
        ("ocr_document_latex_v1", "latex"),
    ],
)
def test_prompt_template_is_the_output_contract(prompt_template: str, output_mode: str) -> None:
    from backend.external_model.schemas import ExternalModelConfig

    config = ExternalModelConfig(prompt_template=prompt_template)

    assert config.resolved_output_mode() == output_mode


def test_unknown_prompt_template_is_rejected() -> None:
    from backend.external_model.schemas import ExternalModelConfig

    with pytest.raises(ValueError):
        ExternalModelConfig(prompt_template="unknown").resolved_output_mode()


def test_custom_prompt_replaces_template_text_without_changing_result_type() -> None:
    from backend.external_model.prompts import build_prompt
    from backend.external_model.schemas import ExternalModelConfig

    config = ExternalModelConfig(
        prompt_template="ocr_markdown_v1",
        custom_prompt="Return the requested document structure.",
    )

    assert build_prompt(config) == "Return the requested document structure."
    assert config.resolved_output_mode() == "markdown"


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
    assert load_config_from_mapping({"external_model_api_key": "plaintext-token"}).normalized_api_key() == ""


def test_external_connection_signature_ignores_unused_mineru_model_name() -> None:
    from backend.external_model import ExternalModelConfig, external_config_signature

    first = ExternalModelConfig(provider="mineru", model_name="unused-a")
    second = ExternalModelConfig(provider="mineru", model_name="unused-b")

    assert external_config_signature(first) == external_config_signature(second)


def test_external_connection_signature_tracks_openai_model_name() -> None:
    from backend.external_model import ExternalModelConfig, external_config_signature

    first = ExternalModelConfig(provider="openai_compatible", model_name="vision-a")
    second = ExternalModelConfig(provider="openai_compatible", model_name="vision-b")

    assert external_config_signature(first) != external_config_signature(second)


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
    from backend.external_model.presets import PRESETS, PRESET_ITEMS

    preset_ids = [key for key, _label in PRESET_ITEMS]

    assert preset_ids == ["glm_ocr", "paddleocr_vl", "qwen_vl", "mineru_local"]
    assert "ollama_vision" not in preset_ids
    assert PRESETS["paddleocr_vl"] == {
        "label": "PaddleOCR-VL (FastDeploy)",
        "provider": "openai_compatible",
        "base_url": "http://127.0.0.1:8185",
        "model_name": "PaddlePaddle/PaddleOCR-VL",
        "prompt_template": "ocr_markdown_v1",
        "hint": "适用于 FastDeploy OpenAI API Server；端口和模型名需与实际启动参数一致。",
    }


def test_selecting_external_model_does_not_warn_before_configuration() -> None:
    source = (SRC / "ui" / "model_runtime_controller.py").read_text(encoding="utf-8")
    external_branch = source.split('if m == "external_model":', 1)[1].split("return", 1)[0]

    assert "set_model_status" in external_branch
    assert "InfoBar.warning" not in external_branch


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


def test_mineru_health_check_message_does_not_claim_parse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.external_model.mineru_client import MineruClient
    from backend.external_model.schemas import ExternalModelConfig

    class Response:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())

    ok, message = MineruClient(ExternalModelConfig(provider="mineru")).test_connection()

    assert ok is True
    assert message == "MinerU 健康检查通过: /health"


def test_mineru_parse_mode_consumes_native_structure_without_parse_prompt() -> None:
    from backend.external_model.document_pipeline import ExternalDocumentPipeline
    from backend.external_model.prompts import PROMPTS
    from backend.external_model.schemas import ExternalModelConfig, ExternalModelResult

    assert "ocr_document_parse_v1" not in PROMPTS
    pipeline = ExternalDocumentPipeline(
        ExternalModelConfig(provider="mineru"),
        output_format="markdown",
        document_mode="parse",
    )
    result = ExternalModelResult(
        provider="mineru",
        structured_payload={
            "pages": [
                {
                    "page": 1,
                    "blocks": [{"type": "paragraph", "text": "Native MinerU content"}],
                }
            ]
        },
    )

    page = pipeline.process_result(result, 1)

    assert page is not None
    assert page.content == "Native MinerU content"

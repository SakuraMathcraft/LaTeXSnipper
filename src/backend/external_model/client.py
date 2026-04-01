import base64
from io import BytesIO

import requests

from .errors import (
    ExternalModelConfigError,
    ExternalModelConnectionError,
    ExternalModelResponseError,
)
from .mineru_client import MineruClient
from .prompts import build_prompt
from .schemas import ExternalModelConfig, ExternalModelResult


class ExternalModelClient:
    def __init__(self, config: ExternalModelConfig):
        self.config = config

    def _validate_config(self) -> tuple[str, str]:
        provider = self.config.normalized_provider()
        base_url = self.config.normalized_base_url()
        model_name = self.config.normalized_model_name()
        if not base_url:
            raise ExternalModelConfigError("外部模型地址为空，请先填写 Base URL。")
        if provider != "mineru" and not model_name:
            raise ExternalModelConfigError("模型名为空，请先填写本地服务中的模型名称。")
        return provider, model_name

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = self.config.normalized_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _image_to_base64(self, image) -> str:
        buf = BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def test_connection(self) -> tuple[bool, str]:
        provider, model_name = self._validate_config()
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        if provider == "mineru":
            return MineruClient(self.config).test_connection()
        try:
            if provider == "ollama":
                resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
                resp.raise_for_status()
                raw = resp.json()
                names = self._extract_ollama_model_names(raw)
            else:
                resp = requests.get(f"{base_url}/v1/models", headers=self._headers(), timeout=timeout)
                resp.raise_for_status()
                raw = resp.json()
                names = self._extract_openai_model_names(raw)
        except requests.RequestException as e:
            raise ExternalModelConnectionError(f"无法连接到本地服务: {e}") from e
        except ValueError as e:
            raise ExternalModelResponseError(f"接口返回的不是有效 JSON: {e}") from e

        if not names:
            raise ExternalModelResponseError("接口已连接，但未能读取到可用模型列表。")
        if model_name not in names:
            preview = ", ".join(names[:8])
            if len(names) > 8:
                preview += " ..."
            raise ExternalModelConfigError(
                f"模型名不存在: {model_name}\n当前可用模型: {preview}"
            )
        return True, f"连接成功，已找到模型 {model_name}。"

    def predict(self, image) -> ExternalModelResult:
        provider, model_name = self._validate_config()
        if provider == "mineru":
            image_b64 = self._image_to_base64(image)
            return MineruClient(self.config).predict(image_b64)
        if provider == "ollama":
            return self._predict_ollama(image, model_name)
        return self._predict_openai_compatible(image, model_name)

    def _predict_openai_compatible(self, image, model_name: str) -> ExternalModelResult:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        image_b64 = self._image_to_base64(image)
        prompt = build_prompt(self.config)
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        try:
            resp = requests.post(
                f"{base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
        except requests.RequestException as e:
            raise ExternalModelConnectionError(f"外部模型请求失败: {e}") from e
        except ValueError as e:
            raise ExternalModelResponseError(f"接口返回的不是有效 JSON: {e}") from e
        text = self._extract_openai_content(raw)
        return self._build_result(text, raw)

    def _predict_ollama(self, image, model_name: str) -> ExternalModelResult:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        image_b64 = self._image_to_base64(image)
        payload = {
            "model": model_name,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": build_prompt(self.config),
                    "images": [image_b64],
                }
            ],
        }
        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
        except requests.RequestException as e:
            raise ExternalModelConnectionError(f"外部模型请求失败: {e}") from e
        except ValueError as e:
            raise ExternalModelResponseError(f"接口返回的不是有效 JSON: {e}") from e
        text = self._extract_ollama_content(raw)
        return self._build_result(text, raw)

    def _build_result(self, text: str, raw: dict) -> ExternalModelResult:
        content = (text or "").strip()
        if not content:
            raise ExternalModelResponseError("识别结果为空")
        output_mode = self.config.normalized_output_mode()
        return ExternalModelResult(
            text=content if output_mode == "text" else content,
            latex=content if output_mode == "latex" else "",
            markdown=content if output_mode == "markdown" else "",
            provider=self.config.normalized_provider(),
            model_name=self.config.normalized_model_name(),
            raw=raw if isinstance(raw, dict) else None,
        )

    def _extract_openai_content(self, raw: dict) -> str:
        try:
            choices = raw.get("choices") or []
            message = choices[0].get("message") or {}
            content = message.get("content")
        except Exception as e:
            raise ExternalModelResponseError(f"接口返回格式不受支持: {e}") from e
        return self._flatten_content(content)

    def _extract_ollama_content(self, raw: dict) -> str:
        try:
            message = raw.get("message") or {}
            content = message.get("content") or raw.get("response") or ""
        except Exception as e:
            raise ExternalModelResponseError(f"接口返回格式不受支持: {e}") from e
        return self._flatten_content(content)

    def _flatten_content(self, content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "\n".join(parts).strip()
        raise ExternalModelResponseError("接口返回的 content 字段格式不受支持。")

    def _extract_ollama_model_names(self, raw: dict) -> list[str]:
        items = raw.get("models") or []
        names = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        return names

    def _extract_openai_model_names(self, raw: dict) -> list[str]:
        items = raw.get("data") or []
        names = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if model_id:
                names.append(model_id)
        return names

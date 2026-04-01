import requests

from .errors import ExternalModelConnectionError, ExternalModelResponseError
from .schemas import ExternalModelConfig, ExternalModelResult


class MineruClient:
    def __init__(self, config: ExternalModelConfig):
        self.config = config

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = self.config.normalized_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def test_connection(self) -> tuple[bool, str]:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        endpoint = self.config.normalized_mineru_test_endpoint()
        url = f"{base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=timeout)
            if resp.status_code >= 500:
                resp.raise_for_status()
        except requests.RequestException as e:
            raise ExternalModelConnectionError(f"MinerU 连通性检查失败: {e}") from e
        return True, f"MinerU 连通成功: {endpoint}"

    def predict(self, image_b64: str) -> ExternalModelResult:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        endpoint = self.config.normalized_mineru_endpoint()
        model_name = self.config.normalized_model_name()
        output_mode = self.config.normalized_output_mode()
        payload = {
            "image_base64": image_b64,
            "mode": self.config.normalized_mineru_mode(),
            "output": output_mode,
        }
        if model_name:
            payload["model"] = model_name
        try:
            resp = requests.post(
                f"{base_url}{endpoint}",
                headers=self._headers(),
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json()
        except requests.RequestException as e:
            raise ExternalModelConnectionError(f"MinerU 请求失败: {e}") from e
        except ValueError as e:
            raise ExternalModelResponseError(f"MinerU 返回的不是有效 JSON: {e}") from e

        text = self._extract_text(raw)
        if not text:
            raise ExternalModelResponseError("MinerU 识别结果为空")

        return ExternalModelResult(
            text=text if output_mode == "text" else text,
            latex=text if output_mode == "latex" else "",
            markdown=text if output_mode == "markdown" else "",
            provider="mineru",
            model_name=model_name or "mineru",
            raw=raw if isinstance(raw, dict) else None,
        )

    def _extract_text(self, raw: dict) -> str:
        if not isinstance(raw, dict):
            raise ExternalModelResponseError("MinerU 返回格式不受支持")

        candidates = [
            raw.get("markdown"),
            raw.get("latex"),
            raw.get("text"),
            raw.get("result"),
            raw.get("content"),
            raw.get("output"),
        ]
        data = raw.get("data")
        if isinstance(data, dict):
            candidates.extend([
                data.get("markdown"),
                data.get("latex"),
                data.get("text"),
                data.get("content"),
                data.get("result"),
            ])

        for item in candidates:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""

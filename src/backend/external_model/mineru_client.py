import base64

import requests
from urllib.parse import urlparse

from .errors import ExternalModelConnectionError, ExternalModelResponseError
from .schemas import ExternalModelConfig, ExternalModelResult


class MineruClient:
    def __init__(self, config: ExternalModelConfig):
        self.config = config

    def _headers(self, include_content_type: bool = True) -> dict:
        headers = {"Content-Type": "application/json"} if include_content_type else {}
        api_key = self.config.normalized_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _format_request_error(self, e: requests.RequestException, action: str, url: str) -> str:
        parsed = urlparse(url or "")
        host = parsed.hostname or "未知地址"
        port = parsed.port
        endpoint = parsed.path or "/"
        target = f"{host}:{port}" if port else host

        if isinstance(e, requests.Timeout):
            return f"{action}超时，请检查服务响应速度或适当提高超时设置。"
        if isinstance(e, requests.ConnectionError):
            return f"无法连接到 {target}，请确认 MinerU 服务已启动，地址和端口填写正确。"

        resp = getattr(e, "response", None)
        if resp is not None:
            code = int(getattr(resp, "status_code", 0) or 0)
            if code == 401:
                return "MinerU 认证失败，请检查 API Key。"
            if code == 403:
                return "MinerU 访问被拒绝，请检查权限配置。"
            if code == 404:
                return f"MinerU 接口路径不存在：{endpoint}，请检查接口路径配置。"
            if code == 429:
                return "MinerU 请求过于频繁，请稍后重试。"
            if 500 <= code < 600:
                return f"MinerU 服务端返回 {code}，请稍后重试或检查服务日志。"
            return f"{action}失败，接口返回 {code}。"

        return f"{action}失败，请检查服务地址、接口路径和网络连接。"

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
            raise ExternalModelConnectionError(self._format_request_error(e, "MinerU 连通性检查", url)) from e
        return True, f"MinerU 连通成功: {endpoint}"

    def predict(self, image_b64: str) -> ExternalModelResult:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        endpoint = self.config.normalized_mineru_endpoint()
        model_name = self.config.normalized_model_name()
        output_mode = self.config.normalized_output_mode()
        url = f"{base_url}{endpoint}"

        try:
            if endpoint.rstrip("/").endswith("/file_parse"):
                image_bytes = base64.b64decode(image_b64.encode("ascii"))
                # Prefer GPU-heavy backends by default, and gracefully fallback.
                backend_candidates = ["vlm-auto-engine", "hybrid-auto-engine", "pipeline"]
                parse_mode = "parse" in str(getattr(self.config, "prompt_template", "") or "").strip().lower()
                resp = None
                last_error: requests.RequestException | None = None
                for backend in backend_candidates:
                    data = {
                        "backend": backend,
                        "parse_method": "auto",
                        "formula_enable": "true",
                        "table_enable": "true",
                        "return_md": "true",
                        "return_middle_json": "true",
                        "return_model_output": "false",
                        "return_content_list": "false",
                        "return_images": "true" if parse_mode else "false",
                        "response_format_zip": "false",
                    }
                    try:
                        resp = requests.post(
                            url,
                            headers=self._headers(include_content_type=False),
                            files=[("files", ("image.png", image_bytes, "image/png"))],
                            data=data,
                            timeout=timeout,
                        )
                        resp.raise_for_status()
                        break
                    except requests.RequestException as e:
                        last_error = e
                        resp = None
                        continue

                if resp is None:
                    assert last_error is not None
                    raise last_error
            else:
                payload = {
                    "image_base64": image_b64,
                    "mode": self.config.normalized_mineru_mode(),
                    "output": output_mode,
                }
                if model_name:
                    payload["model"] = model_name
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=timeout,
                )

            resp.raise_for_status()
            raw = resp.json()
        except requests.RequestException as e:
            raise ExternalModelConnectionError(self._format_request_error(e, "MinerU 请求", url)) from e
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
            structured_payload=self._extract_structured_payload(raw),
        )

    def _extract_text(self, raw: dict) -> str:
        def _walk(node, depth: int = 0) -> str:
            if depth > 8:
                return ""
            if isinstance(node, str):
                text = node.strip()
                return text if text else ""
            if isinstance(node, dict):
                direct_keys = (
                    "markdown",
                    "md_content",
                    "md",
                    "latex",
                    "text",
                    "result",
                    "content",
                    "output",
                )
                for key in direct_keys:
                    value = node.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

                priority_keys = (
                    "data",
                    "results",
                    "result",
                    "outputs",
                    "documents",
                    "files",
                    "items",
                    "pages",
                    "content_list",
                )
                for key in priority_keys:
                    if key not in node:
                        continue
                    text = _walk(node.get(key), depth + 1)
                    if text:
                        return text

                for value in node.values():
                    text = _walk(value, depth + 1)
                    if text:
                        return text
                return ""

            if isinstance(node, list):
                for item in node:
                    text = _walk(item, depth + 1)
                    if text:
                        return text
            return ""

        text = _walk(raw)
        if text:
            return text
        if not isinstance(raw, (dict, list)):
            raise ExternalModelResponseError("MinerU 返回格式不受支持")
        return ""

    def _extract_structured_payload(self, raw: dict) -> dict | None:
        if isinstance(raw, list):
            return {"items": raw}
        if not isinstance(raw, dict):
            return None
        data = raw.get("data")
        if isinstance(data, dict):
            if any(key in data for key in ("pages", "blocks", "assets", "images", "tables", "elements", "items", "content_list")):
                return data
        if any(key in raw for key in ("pages", "blocks", "assets", "images", "tables", "elements", "items", "content_list")):
            return raw
        return None

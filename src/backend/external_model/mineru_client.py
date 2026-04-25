import base64
from pathlib import Path
from urllib.parse import urlparse

import requests

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

    def _format_request_error(self, exc: requests.RequestException, action: str, url: str) -> str:
        parsed = urlparse(url or "")
        host = parsed.hostname or "unknown host"
        port = parsed.port
        endpoint = parsed.path or "/"
        target = f"{host}:{port}" if port else host

        if isinstance(exc, requests.Timeout):
            return f"{action}超时，请检查 MinerU 服务状态或提高超时时间。"
        if isinstance(exc, requests.ConnectionError):
            return f"无法连接到 {target}，请确认 MinerU 服务已启动，地址和端口填写正确。"

        resp = getattr(exc, "response", None)
        if resp is not None:
            code = int(getattr(resp, "status_code", 0) or 0)
            if code == 401:
                return "MinerU 认证失败，请检查 API Key。"
            if code == 403:
                return "MinerU 访问被拒绝，请检查权限配置。"
            if code == 404:
                return f"MinerU 接口路径不存在：{endpoint}，请检查解析接口路径配置。"
            if code == 409:
                detail = self._response_detail(resp)
                if detail:
                    return f"MinerU 解析任务失败：{detail}"
                return "MinerU 解析任务失败，请检查 MinerU 模型配置和服务日志。"
            if code == 429:
                return "MinerU 请求过于频繁，请稍后重试。"
            if 500 <= code < 600:
                return f"MinerU 服务端返回 {code}，请检查服务日志。"
            return f"{action}失败，接口返回 {code}。"

        return f"{action}失败，请检查服务地址、接口路径和网络连接。"

    def _response_detail(self, resp: requests.Response) -> str:
        try:
            raw = resp.json()
        except Exception:
            text = str(getattr(resp, "text", "") or "").strip()
            return text[:500]
        if isinstance(raw, dict):
            for key in ("detail", "message", "error", "msg"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:500]
            return str(raw)[:500]
        return str(raw)[:500]

    def test_connection(self) -> tuple[bool, str]:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        endpoint = self.config.normalized_mineru_test_endpoint()
        url = f"{base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=timeout)
            if resp.status_code >= 500:
                resp.raise_for_status()
        except requests.RequestException as exc:
            raise ExternalModelConnectionError(self._format_request_error(exc, "MinerU 连通性检查", url)) from exc
        return True, f"MinerU 连通成功: {endpoint}"

    def _file_parse_data(self, backend: str, start_page_id: int = 0, end_page_id: int = 99999) -> dict:
        return {
            "backend": backend,
            "parse_method": "auto",
            "formula_enable": "true",
            "table_enable": "true",
            "return_md": "true",
            "return_middle_json": "true",
            "return_model_output": "false",
            "return_content_list": "true",
            "return_images": "true",
            "response_format_zip": "false",
            "start_page_id": str(max(int(start_page_id), 0)),
            "end_page_id": str(max(int(end_page_id), 0)),
        }

    def _post_file_parse(
        self,
        filename: str,
        payload: bytes,
        content_type: str,
        start_page_id: int = 0,
        end_page_id: int = 99999,
    ) -> dict:
        base_url = self.config.normalized_base_url()
        timeout = self.config.normalized_timeout()
        endpoint = self.config.normalized_mineru_endpoint()
        url = f"{base_url}{endpoint}"
        backend_candidates = ("pipeline", "hybrid-auto-engine", "vlm-auto-engine")
        last_error: requests.RequestException | None = None

        for backend in backend_candidates:
            try:
                resp = requests.post(
                    url,
                    headers=self._headers(include_content_type=False),
                    files=[("files", (filename, payload, content_type))],
                    data=self._file_parse_data(backend, start_page_id, end_page_id),
                    timeout=timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except ValueError as exc:
                raise ExternalModelResponseError(f"MinerU 返回的不是有效 JSON: {exc}") from exc
            except requests.RequestException as exc:
                resp = getattr(exc, "response", None)
                status_code = int(getattr(resp, "status_code", 0) or 0) if resp is not None else 0
                if status_code and status_code < 500 and status_code != 429:
                    raise ExternalModelConnectionError(
                        self._format_request_error(exc, "MinerU 请求", url)
                    ) from exc
                last_error = exc

        assert last_error is not None
        raise ExternalModelConnectionError(
            self._format_request_error(last_error, "MinerU 请求", url)
        ) from last_error

    def predict(self, image_b64: str) -> ExternalModelResult:
        try:
            image_bytes = base64.b64decode(image_b64.encode("ascii"))
        except Exception as exc:
            raise ExternalModelResponseError(f"MinerU 图片编码失败: {exc}") from exc
        raw = self._post_file_parse("image.png", image_bytes, "image/png")
        return self._build_result(raw, self.config.normalized_output_mode())

    def parse_pdf(self, pdf_path: str, max_pages: int) -> ExternalModelResult:
        path = Path(pdf_path)
        if not path.is_file():
            raise ExternalModelResponseError(f"PDF 文件不存在: {path}")
        page_count = max(int(max_pages or 1), 1)
        raw = self._post_file_parse(
            path.name,
            path.read_bytes(),
            "application/pdf",
            start_page_id=0,
            end_page_id=page_count - 1,
        )
        return self._build_result(raw, self.config.normalized_output_mode())

    def _build_result(self, raw: dict, output_mode: str) -> ExternalModelResult:
        text = self._extract_text(raw)
        if not text:
            raise ExternalModelResponseError("MinerU 识别结果为空")
        return ExternalModelResult(
            text=text,
            latex=text if output_mode == "latex" else "",
            markdown=text if output_mode == "markdown" else "",
            provider="mineru",
            model_name="mineru",
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

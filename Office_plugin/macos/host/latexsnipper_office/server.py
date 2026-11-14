"""Loopback HTTPS host for the macOS Office add-in.

Static routes serve the add-in pages, the shared Office editor and MathJax.
``/api`` routes give those pages the native services that the Windows plugin
gets from .NET: system font outlines, MathML to OMML, typography settings and
the Automation API recognition client. API calls must be same-origin and carry
``X-LaTeXSnipper-Office``, which a cross-site page cannot send without a CORS
preflight this server never grants.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import ssl
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from latexsnipper_office.assets import OfficeAddinAssets
from latexsnipper_office.certificate import LocalCertificate

logger = logging.getLogger(f"latexsnipper.{__name__}")

DEFAULT_PORT = 28766
API_HEADER = "X-LaTeXSnipper-Office"
MAX_BODY_BYTES = 4 * 1024 * 1024
TYPOGRAPHY_ADAPTER_PATH = "/renderer/typography-adapter.js"
_JOB_PATH = re.compile(r"^/api/recognition/jobs/([A-Za-z0-9_-]{1,128})$")
_SETTINGS_PATH = re.compile(r"^/api/settings/(word|powerpoint)(?:/(import|export))?$")
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".txt": "text/plain; charset=utf-8",
}


class OfficeApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class OfficeAddinServices(Protocol):
    def catalog(self) -> dict[str, Any]: ...

    def font_outlines(self, runs: list[dict[str, Any]]) -> dict[str, Any]: ...

    def mathml_to_omml(self, mathml: str, typography: dict[str, Any]) -> str: ...

    def load_settings(self, host: str) -> dict[str, Any]: ...

    def save_settings(self, host: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def import_settings(self, host: str) -> dict[str, Any]: ...

    def export_settings(self, host: str) -> dict[str, Any]: ...

    def recognition_config(self) -> dict[str, Any]: ...

    def create_next_result_job(self, timeout: int) -> dict[str, Any]: ...

    def recognition_job(self, job_id: str) -> dict[str, Any]: ...

    def cancel_recognition_job(self, job_id: str) -> dict[str, Any]: ...

    def write_word_variables(self, marker: Any, values: Any) -> dict[str, Any]: ...


class OfficeAddinServer:
    def __init__(
        self,
        *,
        assets: OfficeAddinAssets,
        certificate: LocalCertificate,
        services: OfficeAddinServices,
        port: int = DEFAULT_PORT,
        host: str = "127.0.0.1",
    ) -> None:
        self.assets = assets
        self.certificate = certificate
        self.services = services
        self.port = port
        self.host = host
        self._server: _OfficeHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"https://localhost:{self.port}"

    @property
    def running(self) -> bool:
        return self._server is not None

    def static_roots(self) -> dict[str, Path]:
        return {
            "/addin/": self.assets.web,
            "/shared/": self.assets.shared_editor,
            "/mathjax/": self.assets.mathjax,
            "/support/": self.assets.support,
        }

    def start(self) -> None:
        if self._server is not None:
            return
        self.assets.validate()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(
            str(self.certificate.certificate), str(self.certificate.private_key)
        )
        server = _OfficeHTTPServer((self.host, self.port), _OfficeRequestHandler, self)
        server.socket = context.wrap_socket(
            server.socket, server_side=True, do_handshake_on_connect=False
        )
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="LaTeXSnipper Office add-in", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)


class _OfficeHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, office: OfficeAddinServer) -> None:
        self.office = office
        super().__init__(address, handler)

    def handle_error(self, request, client_address) -> None:
        # TLS handshakes from probes and closed tabs are routine; never print tracebacks.
        return


class _OfficeRequestHandler(BaseHTTPRequestHandler):
    server: _OfficeHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "LaTeXSnipperOffice/1"
    sys_version = ""
    timeout = 60

    def log_message(self, format: str, *args) -> None:
        return

    def setup(self) -> None:
        super().setup()
        try:
            self.connection.do_handshake()
        except (ssl.SSLError, OSError):
            self.close_connection = True
            raise ConnectionAbortedError from None

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionError, TimeoutError, ssl.SSLError):
            self.close_connection = True

    # Routing -----------------------------------------------------------------

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:
        self._send_error(OfficeApiError(403, "forbidden", "不允许跨源访问。"))

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
        # Keep-alive reuses this handler: read this request's body before
        # anything else so a later request never sees it, or misses its own.
        self._body: dict[str, Any] | None = None
        self._body_error: OfficeApiError | None = None
        try:
            self._body = self._read_body()
        except OfficeApiError as error:
            self._body_error = error
        try:
            self._check_host()
            if path.startswith("/api/"):
                self._check_api_request()
                self._send_json(HTTPStatus.OK, self._api(method, path))
                return
            if method not in {"GET", "HEAD"}:
                raise OfficeApiError(405, "method_not_allowed", "不支持的请求方法。")
            self._serve_static(path, head=method == "HEAD")
        except OfficeApiError as error:
            self._send_error(error)
        except Exception:
            logger.exception("request failed: %s %s", method, path)
            self._send_error(
                OfficeApiError(500, "internal_error", "LaTeXSnipper 处理请求失败。")
            )

    def _api(self, method: str, path: str) -> dict[str, Any]:
        if method == "GET" and path == "/api/health":
            return {"ok": True}
        services = self.server.office.services
        routes: dict[tuple[str, str], Callable[[], dict[str, Any]]] = {
            ("GET", "/api/catalog"): services.catalog,
            ("POST", "/api/font-outlines"): lambda: services.font_outlines(
                _require_list(self._json_body(), "runs")
            ),
            ("POST", "/api/omml"): lambda: {
                "omml": services.mathml_to_omml(
                    _require_string(self._json_body(), "mathml"),
                    self._json_body().get("typography"),
                )
            },
            ("POST", "/api/word/variables"): lambda: services.write_word_variables(
                self._json_body().get("marker"), self._json_body().get("values")
            ),
            ("GET", "/api/recognition/config"): services.recognition_config,
            ("POST", "/api/recognition/next"): lambda: services.create_next_result_job(
                _timeout(self._json_body())
            ),
        }
        route = routes.get((method, path))
        if route is not None:
            return route()
        if match := _JOB_PATH.match(path):
            job_id = match.group(1)
            if method == "GET":
                return services.recognition_job(job_id)
            if method == "DELETE":
                return services.cancel_recognition_job(job_id)
        if match := _SETTINGS_PATH.match(path):
            host, action = match.group(1), match.group(2)
            if action is None and method == "GET":
                return services.load_settings(host)
            if action is None and method == "PUT":
                return services.save_settings(host, self._json_body())
            if action == "import" and method == "POST":
                return services.import_settings(host)
            if action == "export" and method == "POST":
                return services.export_settings(host)
        raise OfficeApiError(404, "not_found", "接口不存在。")

    # Guards ------------------------------------------------------------------

    def _origins(self) -> set[str]:
        port = self.server.office.port
        return {f"https://localhost:{port}", f"https://127.0.0.1:{port}"}

    def _check_host(self) -> None:
        port = self.server.office.port
        if self.headers.get("Host") not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
            raise OfficeApiError(421, "misdirected", "请求主机无效。")

    def _check_api_request(self) -> None:
        if self.headers.get(API_HEADER) != "1":
            raise OfficeApiError(403, "forbidden", "缺少 Office 加载项请求标记。")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self._origins():
            raise OfficeApiError(403, "forbidden", "不允许跨源访问。")

    # Bodies ------------------------------------------------------------------

    def _read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self.close_connection = True
            raise OfficeApiError(400, "invalid_request", "请求长度无效。") from None
        if length < 0 or length > MAX_BODY_BYTES:
            # The unread body would corrupt the next request on this connection.
            self.close_connection = True
            raise OfficeApiError(413, "payload_too_large", "请求内容过大。")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise OfficeApiError(
                400, "invalid_request", "请求不是有效的 JSON。"
            ) from None
        if not isinstance(payload, dict):
            raise OfficeApiError(400, "invalid_request", "请求必须是 JSON 对象。")
        return payload

    def _json_body(self) -> dict[str, Any]:
        if self._body_error is not None:
            raise self._body_error
        return self._body or {}

    # Responses ---------------------------------------------------------------

    def _serve_static(self, path: str, *, head: bool) -> None:
        target = self._static_target(path)
        if target is None or not target.is_file():
            raise OfficeApiError(404, "not_found", "文件不存在。")
        data = b"" if head else target.read_bytes()
        content_type = _CONTENT_TYPES.get(target.suffix.lower()) or (
            mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header(
            "Content-Length", str(target.stat().st_size if head else len(data))
        )
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _static_target(self, path: str) -> Path | None:
        office = self.server.office
        if path == TYPOGRAPHY_ADAPTER_PATH:
            return office.assets.typography_adapter
        for prefix, root in office.static_roots().items():
            if path.startswith(prefix):
                return _safe_child(root, unquote(path[len(prefix) :]))
        return None

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, error: OfficeApiError) -> None:
        try:
            self._send_json(
                HTTPStatus(error.status),
                {"error": {"code": error.code, "message": error.message}},
            )
        except (ConnectionError, TimeoutError, ssl.SSLError, ValueError):
            self.close_connection = True


def _safe_child(root: Path, relative: str) -> Path | None:
    parts = [part for part in relative.split("/") if part]
    if not parts or any(
        part in {".", ".."} or "\\" in part or "\x00" in part for part in parts
    ):
        return None
    base = root.resolve()
    target = base.joinpath(*parts).resolve()
    return target if target.is_relative_to(base) else None


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OfficeApiError(400, "invalid_request", f"缺少字段：{key}")
    return value


def _require_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if (
        not isinstance(value, list)
        or len(value) > 512
        or not all(isinstance(item, dict) for item in value)
    ):
        raise OfficeApiError(400, "invalid_request", f"字段无效：{key}")
    return value


def _timeout(payload: dict[str, Any]) -> int:
    value = payload.get("timeout", 120)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 600:
        raise OfficeApiError(400, "invalid_request", "等待时间无效。")
    return value


__all__ = [
    "API_HEADER",
    "DEFAULT_PORT",
    "OfficeAddinServer",
    "OfficeAddinServices",
    "OfficeApiError",
]

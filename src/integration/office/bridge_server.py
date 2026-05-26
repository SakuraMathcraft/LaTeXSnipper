"""Localhost HTTP bridge for Office add-ins."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any

from .bridge_auth import OfficeBridgeAuth
from .bridge_contracts import MAX_JSON_BODY_BYTES, OfficeBridgeError, error_response, parse_json_body, success_response
from .conversion_service import OfficeConversionService


class OfficeBridgeServer:
    protocol_version = 1

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        auth: OfficeBridgeAuth | None = None,
        conversion_service: OfficeConversionService | None = None,
        recognition_service: Any | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("Office bridge must bind to localhost only")
        self.host = "127.0.0.1" if host == "localhost" else host
        self.requested_port = int(port)
        self.auth = auth or OfficeBridgeAuth()
        self.conversion_service = conversion_service or OfficeConversionService()
        self.recognition_service = recognition_service
        self._httpd: _OfficeHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._httpd is None:
            return self.requested_port
        return int(self._httpd.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def token(self) -> str:
        return self.auth.token

    def start(self) -> None:
        if self._httpd is not None:
            return
        self._httpd = _OfficeHTTPServer((self.host, self.requested_port), _OfficeRequestHandler, self)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="OfficeBridgeServer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=2.0)

    def health(self) -> dict[str, Any]:
        return {
            "name": "LaTeXSnipper Office Bridge",
            "protocol": self.protocol_version,
            "auth": "bearer",
            "features": {
                "convert_latex": True,
                "capture_recognize": self.recognition_service is not None,
            },
        }

    def config(self) -> dict[str, Any]:
        return {
            "bridge_url": self.base_url,
            "token": self.token,
            "features": self.health()["features"],
        }

    def handle_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path == "/convert/latex":
            return self.conversion_service.convert(payload)
        if path == "/recognize/screenshot":
            if self.recognition_service is None:
                raise OfficeBridgeError(501, "feature_unavailable", "screenshot OCR is not available")
            return self.recognition_service.recognize_screenshot(payload)
        raise OfficeBridgeError(404, "not_found", f"unknown endpoint: {path}")


class _OfficeHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler, bridge: OfficeBridgeServer) -> None:
        super().__init__(server_address, request_handler)
        self.bridge = bridge


class _OfficeRequestHandler(BaseHTTPRequestHandler):
    server: _OfficeHTTPServer

    def log_message(self, _format: str, *args) -> None:
        return

    def do_OPTIONS(self) -> None:
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, success_response(self.server.bridge.health()))
            return
        if self.path == "/config":
            self._send_json(HTTPStatus.OK, success_response(self.server.bridge.config()))
            return
        else:
            self._send_error(OfficeBridgeError(404, "not_found", f"unknown endpoint: {self.path}"))
            return

    def do_POST(self) -> None:
        try:
            self._require_auth()
            payload = self._read_json()
            result = self.server.bridge.handle_post(self.path, payload)
        except OfficeBridgeError as exc:
            self._send_error(exc)
            return
        except Exception as exc:
            self._send_error(OfficeBridgeError(500, "internal_error", str(exc)))
            return
        self._send_json(HTTPStatus.OK, success_response(result))

    def _require_auth(self) -> None:
        if not self.server.bridge.auth.verify_authorization(self.headers.get("Authorization")):
            raise OfficeBridgeError(401, "unauthorized", "valid bearer token is required")

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError as exc:
            raise OfficeBridgeError(400, "invalid_content_length", "invalid content length") from exc
        if length < 0:
            raise OfficeBridgeError(400, "invalid_content_length", "invalid content length")
        if length > MAX_JSON_BODY_BYTES:
            raise OfficeBridgeError(413, "payload_too_large", "request body is too large")
        return parse_json_body(self.rfile.read(length))

    def _send_error(self, error: OfficeBridgeError) -> None:
        self._send_json(HTTPStatus(error.status), error_response(error))

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        origin = self.headers.get("Origin")
        if origin in {"https://localhost:3000", "https://127.0.0.1:3000"}:
            self.send_header("Access-Control-Allow-Origin", origin)
        elif origin is None:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if status != HTTPStatus.NO_CONTENT:
            self.wfile.write(raw)

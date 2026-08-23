"""Bounded, versioned HTTP server for recognition automation."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
import threading
from collections import OrderedDict
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any
from urllib.parse import urlsplit

from integration.automation.auth import (
    EXTERNAL_PERMISSION,
    MATHCRAFT_PERMISSION,
    AuthenticatedPrincipal,
    AutomationApiAuth,
)
from integration.automation.connection_info import remove_connection_file, write_connection_file
from integration.automation.contracts import (
    API_PREFIX,
    API_VERSION,
    DEFAULT_LIMITS,
    SUPPORTED_IMAGE_FORMATS,
    SUPPORTED_RECOGNITION_MODES,
    AutomationApiError,
    AutomationLimits,
    error_response,
    parse_json_object,
    request_id,
    validate_mode,
    validate_timeout,
)
from integration.automation.rate_limit import RateLimiter
from integration.automation.multipart import parse_multipart_stream
from integration.automation.network_security import tunnel_interface_for_address
from recognition.image_input import ImageInputError, image_from_stream
from recognition.jobs import JobSource, JobState, RecognitionItemInput, RecognitionJobCoordinator


_JOB_PATH = re.compile(r"^/api/v1/recognition/jobs/([^/]+)$")
_TERMINAL_STATES = {JobState.COMPLETED.value, JobState.FAILED.value, JobState.CANCELED.value}


class AutomationApiSettingsError(ValueError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True, slots=True)
class AutomationApiSettings:
    host: str = "127.0.0.1"
    port: int = 28765
    access_scope: str = "local"
    remote_security: str = "tunnel"
    remote_key: str = ""
    tls_cert_path: str = ""
    tls_key_path: str = ""
    allowed_origins: tuple[str, ...] = ()
    remote_external_enabled: bool = False

    def validate(self) -> None:
        if not (0 <= int(self.port) <= 65535):
            raise AutomationApiSettingsError("Automation API 端口必须在 0 到 65535 之间。")
        if self.access_scope not in {"local", "remote"}:
            raise AutomationApiSettingsError("Automation API 访问范围必须为仅本机或远程。")
        if self.access_scope == "local":
            try:
                if not ipaddress.ip_address(self.host).is_loopback:
                    raise AutomationApiSettingsError("仅本机模式必须监听本机回环地址。")
            except ValueError as exc:
                if self.host != "localhost":
                    raise AutomationApiSettingsError("仅本机模式必须监听本机回环地址。") from exc
        else:
            if self.remote_security not in {"tunnel", "https"}:
                raise AutomationApiSettingsError("远程模式必须使用安全隧道或 HTTPS。")
            if not self.remote_key:
                raise AutomationApiSettingsError("远程模式必须配置访问密钥。")
            try:
                bind_ip = ipaddress.ip_address(self.host)
            except ValueError as exc:
                raise AutomationApiSettingsError("远程模式必须填写明确的网卡 IP 地址。") from exc
            if bind_ip.is_unspecified or bind_ip.is_multicast or bind_ip.is_loopback:
                raise AutomationApiSettingsError("远程模式必须监听明确的非回环网卡地址。")
            if self.remote_security == "tunnel" and tunnel_interface_for_address(self.host) is None:
                raise AutomationApiSettingsError(
                    "安全隧道模式必须选择 Tailscale、WireGuard 或其它 VPN 隧道接口地址；"
                    "普通局域网或公网地址请使用 HTTPS。"
                )
            if self.remote_security == "https":
                if not Path(self.tls_cert_path).is_file() or not Path(self.tls_key_path).is_file():
                    raise AutomationApiSettingsError("HTTPS 模式必须提供有效的证书和私钥文件。")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
                raise AutomationApiSettingsError(f"CORS Origin 格式无效：{origin}")


class AutomationApiServer:
    def __init__(
        self,
        coordinator: RecognitionJobCoordinator,
        *,
        settings: AutomationApiSettings = AutomationApiSettings(),
        auth: AutomationApiAuth | None = None,
        limits: AutomationLimits = DEFAULT_LIMITS,
        connection_file: Path | None = None,
    ) -> None:
        settings.validate()
        self.coordinator = coordinator
        self.settings = settings
        self.auth = auth or AutomationApiAuth(
            remote_key=settings.remote_key,
            remote_external_enabled=settings.remote_external_enabled,
        )
        self.limits = limits
        self.connection_file = connection_file
        self._httpd: _BoundedHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._rate_limiter = RateLimiter()
        self._idempotency_lock = threading.Lock()
        self._idempotency: OrderedDict[tuple[str, str], str] = OrderedDict()

    @property
    def host(self) -> str:
        return self.settings.host

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1]) if self._httpd else int(self.settings.port)

    @property
    def base_url(self) -> str:
        scheme = "https" if self.settings.access_scope == "remote" and self.settings.remote_security == "https" else "http"
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{scheme}://{host}:{self.port}"

    def start(self) -> None:
        if self._httpd is not None:
            return
        httpd = _BoundedHTTPServer(
            (self.settings.host, self.settings.port),
            _AutomationRequestHandler,
            api=self,
            concurrency=self.limits.request_concurrency,
        )
        if self.settings.access_scope == "remote" and self.settings.remote_security == "https":
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(self.settings.tls_cert_path, self.settings.tls_key_path)
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="AutomationApiServer", daemon=True)
        self._thread.start()
        try:
            write_connection_file(
                base_url=self.base_url,
                token=self.auth.local_token,
                path=self.connection_file,
            )
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        remove_connection_file(self.connection_file)

    def minimal_health(self) -> dict[str, Any]:
        available = self.coordinator.model_available or self.coordinator.external_available
        return {"status": "ok" if available else "degraded"}

    def authenticated_config(self, principal: AuthenticatedPrincipal) -> dict[str, Any]:
        limits = self.limits
        return {
            "api_version": API_VERSION,
            "image_formats": list(SUPPORTED_IMAGE_FORMATS),
            "backends": {
                "mathcraft": {
                    "available": self.coordinator.model_available,
                    "input_types": ["image_upload"],
                    "modes": list(SUPPORTED_RECOGNITION_MODES),
                },
                "external": {
                    "available": self.coordinator.external_available,
                    "input_types": ["image_upload"],
                    "modes": list(SUPPORTED_RECOGNITION_MODES),
                },
            },
            "permissions": sorted(principal.permissions),
            "next_result_available": principal.kind == "local",
            "limits": {
                "max_image_bytes": limits.max_encoded_image_bytes,
                "max_request_bytes": limits.max_request_body_bytes,
                "max_batch_items": limits.max_batch_items,
                "max_image_pixels": limits.max_decoded_image_pixels,
                "max_batch_pixels": limits.max_request_decoded_pixels,
                "max_wait_seconds": limits.max_prefer_wait_seconds,
            },
            "mathcraft_available": self.coordinator.model_available,
            "external_available": self.coordinator.external_available,
        }

    def allowed_host(self, value: str | None) -> bool:
        if not value:
            return False
        raw = value.strip().lower()
        hostname = raw
        if raw.startswith("["):
            hostname = raw[1 : raw.find("]")] if "]" in raw else ""
        elif raw.count(":") == 1:
            hostname = raw.rsplit(":", 1)[0]
        accepted = {self.settings.host.lower(), "localhost"}
        if self.settings.access_scope == "local":
            accepted.update(("127.0.0.1", "::1"))
        return hostname in accepted

    def authenticate(self, handler: BaseHTTPRequestHandler) -> AuthenticatedPrincipal:
        principal = self.auth.authenticate(handler.headers.get("Authorization"))
        if principal is None:
            raise AutomationApiError(401, "unauthorized", "需要有效的 Bearer 访问凭据。")
        peer = handler.client_address[0]
        try:
            peer_is_loopback = ipaddress.ip_address(peer).is_loopback
        except ValueError:
            peer_is_loopback = False
        if self.settings.access_scope == "local" and not peer_is_loopback:
            raise AutomationApiError(403, "forbidden", "仅允许本机设备访问。")
        local_addresses = {self.settings.host}
        try:
            local_addresses.update(
                info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None)
            )
        except OSError:
            pass
        if principal.kind == "local" and not peer_is_loopback and peer not in local_addresses:
            raise AutomationApiError(403, "forbidden", "本机会话凭据不能用于远程访问。")
        return principal

    def check_rate_limit(self, principal: AuthenticatedPrincipal, peer: str, *, query: bool) -> None:
        if principal.kind != "remote":
            return
        limit = (
            self.limits.remote_status_queries_per_minute
            if query
            else self.limits.remote_submissions_per_minute
        )
        if not self._rate_limiter.allow((principal.id, peer, "query" if query else "submit"), limit):
            raise AutomationApiError(429, "rate_limited", "请求频率超过限制，请稍后重试。")

    def submit_idempotent(self, principal_id: str, key: str, submitter) -> dict[str, Any]:
        lookup = (principal_id, key)
        with self._idempotency_lock:
            existing = self._idempotency.get(lookup)
            if existing:
                try:
                    job = self.coordinator.get(existing, principal_id=principal_id)
                except AutomationApiError:
                    self._idempotency.pop(lookup, None)
                else:
                    self._idempotency.move_to_end(lookup)
                    return job
            job = submitter()
            self._idempotency[lookup] = job["id"]
            self._idempotency.move_to_end(lookup)
            while len(self._idempotency) > self.limits.max_retained_jobs:
                self._idempotency.popitem(last=False)
            return job


class _BoundedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, request_handler, *, api: AutomationApiServer, concurrency: int) -> None:
        self.api = api
        self._request_slots = threading.BoundedSemaphore(concurrency)
        self._decode_slot = threading.BoundedSemaphore(1)
        super().__init__(server_address, request_handler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(self.api.limits.request_read_timeout_seconds)
        return request, address

    def process_request(self, request, client_address) -> None:
        self._request_slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class _AutomationRequestHandler(BaseHTTPRequestHandler):
    server: _BoundedHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")

    def _dispatch(self, method: str) -> None:
        current_request_id = request_id()
        self.connection.settimeout(self.server.api.limits.request_read_timeout_seconds)
        try:
            path = urlsplit(self.path).path
            if not self.server.api.allowed_host(self.headers.get("Host")):
                raise AutomationApiError(400, "invalid_request", "Host 请求头无效。")
            if method == "OPTIONS":
                self._handle_options()
                return
            if method == "GET" and path == f"{API_PREFIX}/health":
                self._send_json(HTTPStatus.OK, self.server.api.minimal_health())
                return
            principal = self.server.api.authenticate(self)
            if method == "GET" and path == f"{API_PREFIX}/config":
                self._send_json(HTTPStatus.OK, self.server.api.authenticated_config(principal))
                return
            if method == "POST" and path == f"{API_PREFIX}/recognition/jobs":
                self.server.api.check_rate_limit(principal, self.client_address[0], query=False)
                self._create_job(principal)
                return
            match = _JOB_PATH.fullmatch(path)
            if match and method in {"GET", "DELETE"}:
                self.server.api.check_rate_limit(principal, self.client_address[0], query=True)
                job_id = match.group(1)
                if method == "DELETE":
                    job = self.server.api.coordinator.cancel(job_id, principal_id=principal.id)
                else:
                    job = self.server.api.coordinator.get(job_id, principal_id=principal.id)
                self._send_json(HTTPStatus.OK, {"job": job})
                return
            raise AutomationApiError(404, "job_not_found", "接口不存在。")
        except AutomationApiError as exc:
            self._send_json(HTTPStatus(exc.status), error_response(exc, request_id_value=current_request_id))
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return
        except Exception:
            error = AutomationApiError(500, "internal_error", "请求处理失败。")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, error_response(error, request_id_value=current_request_id))
        finally:
            try:
                self.connection.settimeout(self.server.api.limits.keep_alive_timeout_seconds)
            except OSError:
                self.close_connection = True

    def _create_job(self, principal: AuthenticatedPrincipal) -> None:
        content_type = self.headers.get("Content-Type", "")
        source = JobSource.LOCAL_API if principal.kind == "local" else JobSource.REMOTE_API
        if content_type.lower().startswith("application/json"):
            payload = parse_json_object(self._read_body())
            input_data = payload.get("input")
            if not isinstance(input_data, dict) or input_data.get("type") != "next_result":
                raise AutomationApiError(400, "invalid_request", "不支持该识别输入类型。")
            if principal.kind != "local":
                raise AutomationApiError(403, "forbidden", "远程凭据不能订阅桌面识别结果。")
            timeout = validate_timeout(payload.get("timeout"))

            def create_waiter():
                return self.server.api.coordinator.create_next_result_job(
                    principal_id=principal.id,
                    source=source,
                    timeout_seconds=timeout,
                )

            idempotency_key = self._idempotency_key()
            job = (
                self.server.api.submit_idempotent(principal.id, idempotency_key, create_waiter)
                if idempotency_key
                else create_waiter()
            )
        elif content_type.lower().startswith("multipart/form-data"):
            job = self._create_upload_job(principal, source, content_type)
        else:
            raise AutomationApiError(400, "invalid_request", "请使用 multipart/form-data 或 application/json。")

        wait_seconds = self._prefer_wait_seconds()
        if wait_seconds > 0:
            job = self.server.api.coordinator.wait(
                job["id"], principal_id=principal.id, timeout=wait_seconds
            )
        status = HTTPStatus.OK if job["state"] in _TERMINAL_STATES else HTTPStatus.ACCEPTED
        headers = {"Location": f"{API_PREFIX}/recognition/jobs/{job['id']}"} if status == HTTPStatus.ACCEPTED else None
        self._send_json(status, {"job": job}, extra_headers=headers)

    def _create_upload_job(
        self,
        principal: AuthenticatedPrincipal,
        source: JobSource,
        content_type: str,
    ) -> dict[str, Any]:
        length = self._content_length()
        header = Message()
        header["Content-Type"] = content_type
        boundary = header.get_param("boundary", header="content-type")
        if not boundary:
            raise AutomationApiError(400, "invalid_request", "Multipart 请求缺少分隔符。")
        parts = parse_multipart_stream(
            self.rfile,
            content_length=length,
            boundary=str(boundary),
            image_limit=self.server.api.limits.max_encoded_image_bytes,
            max_items=self.server.api.limits.max_batch_items,
        )
        fields: dict[str, str] = {}
        inputs: list[RecognitionItemInput] = []
        total_pixels = 0
        decode_acquired = False
        try:
            decode_acquired = self.server._decode_slot.acquire(
                timeout=self.server.api.limits.request_read_timeout_seconds
            )
            if not decode_acquired:
                raise AutomationApiError(503, "queue_full", "图片解码服务繁忙，请稍后重试。")
            for part in parts:
                if part.name == "images":
                    image = image_from_stream(
                        part.stream,
                        max_encoded_bytes=self.server.api.limits.max_encoded_image_bytes,
                        max_pixels=self.server.api.limits.max_decoded_image_pixels,
                    )
                    total_pixels += image.width * image.height
                    if total_pixels > self.server.api.limits.max_request_decoded_pixels:
                        raise AutomationApiError(413, "image_too_large", "批量图片解码后的总像素超过限制。")
                    filename = Path(part.filename).name if part.filename else None
                    inputs.append(RecognitionItemInput(image=image, filename=filename))
                elif part.name in {"backend", "mode", "timeout"}:
                    fields[part.name] = part.stream.read().decode("utf-8", errors="strict").strip()
        except ImageInputError as exc:
            status = 415 if exc.code == "unsupported_image_format" else 413 if exc.code == "image_too_large" else 400
            raise AutomationApiError(status, exc.code, exc.user_message) from exc
        except UnicodeDecodeError as exc:
            raise AutomationApiError(400, "invalid_request", "Multipart 文本字段必须使用 UTF-8。") from exc
        finally:
            if decode_acquired:
                self.server._decode_slot.release()
            for part in parts:
                part.close()
        if not inputs:
            raise AutomationApiError(400, "invalid_request", "至少需要一个 images 图片字段。")
        mode = validate_mode(fields.get("mode"))
        backend = self._validate_backend(fields.get("backend"))
        self._require_backend_permission(principal, backend)
        timeout = validate_timeout(fields.get("timeout"))

        idempotency_key = self._idempotency_key()
        def submit():
            return self.server.api.coordinator.submit(
                inputs,
                principal_id=principal.id,
                source=source,
                mode=mode,
                timeout_seconds=timeout,
                backend=backend,
            )

        return (
            self.server.api.submit_idempotent(principal.id, idempotency_key, submit)
            if idempotency_key
            else submit()
        )

    @staticmethod
    def _validate_backend(value: Any) -> str:
        backend = str(value or "mathcraft").strip().lower()
        if backend not in {"mathcraft", "external"}:
            raise AutomationApiError(400, "invalid_backend", "不支持该识别后端。")
        return backend

    @staticmethod
    def _require_backend_permission(principal: AuthenticatedPrincipal, backend: str) -> None:
        permission = EXTERNAL_PERMISSION if backend == "external" else MATHCRAFT_PERMISSION
        if not principal.allows(permission):
            raise AutomationApiError(403, "forbidden", "没有使用该识别后端的权限。")

    def _idempotency_key(self) -> str:
        key = str(self.headers.get("Idempotency-Key") or "").strip()
        if len(key) > 200:
            raise AutomationApiError(400, "invalid_request", "Idempotency-Key 过长。")
        return key

    def _read_body(self) -> bytes:
        length = self._content_length()
        body = self.rfile.read(length)
        if len(body) != length:
            raise AutomationApiError(400, "invalid_request", "请求体不完整。")
        return body

    def _content_length(self) -> int:
        transfer_encoding = str(self.headers.get("Transfer-Encoding") or "").strip().lower()
        if transfer_encoding:
            raise AutomationApiError(411, "invalid_request", "请求必须提供 Content-Length。")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise AutomationApiError(411, "invalid_request", "请求必须提供 Content-Length。")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise AutomationApiError(400, "invalid_request", "Content-Length 无效。") from exc
        if length <= 0:
            raise AutomationApiError(400, "invalid_request", "请求体为空。")
        if length > self.server.api.limits.max_request_body_bytes:
            raise AutomationApiError(413, "payload_too_large", "请求体超过大小限制。")
        return length

    def _prefer_wait_seconds(self) -> float:
        value = str(self.headers.get("Prefer") or "")
        match = re.search(r"(?:^|[,;\s])wait\s*=\s*([0-9]+(?:\.[0-9]+)?)", value, re.IGNORECASE)
        if not match:
            return 0.0
        return min(float(match.group(1)), self.server.api.limits.max_prefer_wait_seconds)

    def _handle_options(self) -> None:
        origin = self.headers.get("Origin")
        if origin not in self.server.api.settings.allowed_origins:
            raise AutomationApiError(403, "forbidden", "该 Origin 不在允许列表中。")
        self._send_json(
            HTTPStatus.NO_CONTENT,
            None,
            extra_headers={
                "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Prefer, Idempotency-Key",
                "Access-Control-Max-Age": "600",
            },
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any] | None,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(int(status))
            if payload is not None:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin and origin in self.server.api.settings.allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if raw:
                self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            return

from __future__ import annotations

import http.client
import io
import json
import os
import stat
import sys
import threading
import time
import types
import uuid
from pathlib import Path

import pytest
from PIL import Image

from backend.external_model.schemas import ExternalModelConfig
from integration.automation import AutomationApiAuth, AutomationApiServer, AutomationApiSettings
from integration.automation.multipart import parse_multipart_stream
from integration.automation.contracts import AutomationLimits
from runtime.private_files import restrict_file_to_current_user
from recognition.jobs import JobSource, RecognitionItemInput
from recognition.jobs import RecognitionJobCoordinator
from ui.automation_api_controller import automation_api_operation_error_message


def _request(server, method: str, path: str, *, body: bytes | None = None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
    final_headers = {"Host": f"127.0.0.1:{server.port}", **(headers or {})}
    connection.request(method, path, body=body, headers=final_headers)
    response = connection.getresponse()
    raw = response.read()
    result = response.status, dict(response.getheaders()), json.loads(raw) if raw else None
    connection.close()
    return result


def _multipart(fields: dict[str, str], images: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = f"test-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            )
        )
    for filename, data in images:
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="images"; filename="{filename}"\r\n'.encode(),
                b"Content-Type: application/octet-stream\r\n\r\n",
                data,
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _png() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (10, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_desktop_automation_messages_do_not_expose_runtime_exceptions() -> None:
    for action in ("start", "stop", "unexpected"):
        message = automation_api_operation_error_message(action)
        assert any("\u4e00" <= char <= "\u9fff" for char in message)
        assert "exception" not in message.lower()

    with pytest.raises(ValueError) as raised:
        AutomationApiSettings(access_scope="remote", remote_key="").validate()
    assert any("\u4e00" <= char <= "\u9fff" for char in str(raised.value))


def test_health_config_upload_query_and_connection_file(tmp_path: Path) -> None:
    coordinator = RecognitionJobCoordinator(
        lambda image, mode: f"{mode}:{image.size}",
        external_config_provider=lambda: ExternalModelConfig(
            base_url="http://127.0.0.1:11434",
            model_name="vision",
        ),
        external_predictor=lambda image, config: f"{config.model_name}:{image.size}",
    )
    connection_file = tmp_path / "automation-api.json"
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0),
        auth=AutomationApiAuth(local_token="local-secret"),
        connection_file=connection_file,
    )
    server.start()
    try:
        status, headers, health = _request(server, "GET", "/api/v1/health")
        assert status == 200 and health == {"status": "ok"}
        assert "Access-Control-Allow-Origin" not in headers

        status, _, error = _request(server, "GET", "/api/v1/config")
        assert status == 401 and error["error"]["code"] == "unauthorized"
        status, _, config = _request(
            server,
            "GET",
            "/api/v1/config",
            headers={"Authorization": "Bearer local-secret"},
        )
        assert status == 200 and config["api_version"] == "1"
        assert "token" not in json.dumps(config).lower()

        body, content_type = _multipart({"mode": "mixed", "timeout": "10"}, [("wrong.txt", _png())])
        status, _, created = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=body,
            headers={
                "Authorization": "Bearer local-secret",
                "Content-Type": content_type,
                "Prefer": "wait=2",
            },
        )
        assert status == 200
        assert created["job"]["items"][0]["text"] == "mixed:(10, 8)"

        body, content_type = _multipart(
            {"backend": "external", "mode": "formula", "timeout": "10"},
            [("input.png", _png())],
        )
        status, _, created = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=body,
            headers={
                "Authorization": "Bearer local-secret",
                "Content-Type": content_type,
                "Prefer": "wait=2",
            },
        )
        assert status == 200
        assert created["job"]["backend"] == "external"
        assert created["job"]["items"][0]["text"] == "vision:(10, 8)"

        saved = json.loads(connection_file.read_text(encoding="utf-8"))
        assert saved["base_url"] == server.base_url
        assert saved["token"] == "local-secret"
        if os.name != "nt":
            assert stat.S_IMODE(connection_file.stat().st_mode) == 0o600
    finally:
        server.stop()
        coordinator.stop()
    assert not connection_file.exists()


def test_job_ownership_remote_next_result_and_cors_are_restricted(tmp_path: Path) -> None:
    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: "ok",
        external_config_provider=lambda: ExternalModelConfig(
            base_url="http://127.0.0.1:11434",
            model_name="vision",
        ),
        external_predictor=lambda _image, _config: "external",
    )
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(
            port=0,
            allowed_origins=("https://allowed.example",),
            remote_key="remote-secret",
        ),
        auth=AutomationApiAuth(local_token="local", remote_key="remote-secret"),
        connection_file=tmp_path / "connection.json",
    )
    server.start()
    try:
        next_result = json.dumps({"input": {"type": "next_result"}}).encode()
        status, _, error = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=next_result,
            headers={"Authorization": "Bearer remote-secret", "Content-Type": "application/json"},
        )
        assert status == 403 and error["error"]["code"] == "forbidden"

        body, content_type = _multipart(
            {"backend": "external", "mode": "formula"}, [("input.png", _png())]
        )
        status, _, error = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=body,
            headers={
                "Authorization": "Bearer remote-secret",
                "Content-Type": content_type,
            },
        )
        assert status == 403 and error["error"]["code"] == "forbidden"

        status, headers, _ = _request(
            server,
            "GET",
            "/api/v1/config",
            headers={"Authorization": "Bearer local", "Origin": "https://allowed.example"},
        )
        assert status == 200 and headers["Access-Control-Allow-Origin"] == "https://allowed.example"
        status, headers, _ = _request(
            server,
            "GET",
            "/api/v1/config",
            headers={"Authorization": "Bearer local", "Origin": "https://evil.example"},
        )
        assert status == 200 and "Access-Control-Allow-Origin" not in headers
    finally:
        server.stop()
        coordinator.stop()


def test_http_connection_can_be_reused_with_bounded_keep_alive(tmp_path: Path) -> None:
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok")
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0),
        auth=AutomationApiAuth(local_token="local"),
        connection_file=tmp_path / "connection.json",
    )
    server.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
    try:
        for _ in range(2):
            connection.request("GET", "/api/v1/health", headers={"Host": f"127.0.0.1:{server.port}"})
            response = connection.getresponse()
            assert response.status == 200
            response.read()
    finally:
        connection.close()
        server.stop()
        coordinator.stop()


def test_multipart_parser_reads_large_parts_in_bounded_chunks() -> None:
    boundary = "stream-test"
    payload = b"x" * (2 * 1024 * 1024)
    body = (
        f"--{boundary}\r\n".encode()
        + b'Content-Disposition: form-data; name="images"; filename="input.bin"\r\n\r\n'
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )

    class ObservedStream(io.BytesIO):
        largest_read = 0

        def read(self, size=-1):
            self.largest_read = max(self.largest_read, size)
            return super().read(size)

    source = ObservedStream(body)
    parts = parse_multipart_stream(
        source,
        content_length=len(body),
        boundary=boundary,
        image_limit=3 * 1024 * 1024,
        max_items=1,
    )
    try:
        assert len(parts) == 1 and parts[0].size == len(payload)
        assert source.largest_read <= 64 * 1024
        assert getattr(parts[0].stream, "_rolled") is True
    finally:
        for part in parts:
            part.close()


def test_idempotent_submission_is_atomic_and_bounded(tmp_path: Path) -> None:
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok")
    limits = AutomationLimits(max_retained_jobs=2)
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0),
        limits=limits,
        connection_file=tmp_path / "connection.json",
    )
    submitted = 0
    submitted_lock = threading.Lock()

    def submit():
        nonlocal submitted
        with submitted_lock:
            submitted += 1
        return coordinator.submit(
            [RecognitionItemInput(Image.new("RGB", (2, 2)))],
            principal_id="p",
            source=JobSource.LOCAL_API,
            mode="formula",
            timeout_seconds=5,
        )

    results: list[dict] = []
    threads = [
        threading.Thread(target=lambda: results.append(server.submit_idempotent("p", "same", submit)))
        for _ in range(8)
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        assert submitted == 1
        assert len({result["id"] for result in results}) == 1
        server.submit_idempotent("p", "second", submit)
        server.submit_idempotent("p", "third", submit)
        assert len(server._idempotency) == 2
    finally:
        coordinator.stop()


def test_tunnel_mode_requires_the_address_to_belong_to_a_tunnel_interface(monkeypatch) -> None:
    address = types.SimpleNamespace(family=2, address="100.100.100.100")
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        types.SimpleNamespace(net_if_addrs=lambda: {"Tailscale": [address]}),
    )
    AutomationApiSettings(
        host="100.100.100.100",
        access_scope="remote",
        remote_security="tunnel",
        remote_key="secret",
    ).validate()
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        types.SimpleNamespace(net_if_addrs=lambda: {"Ethernet": [address]}),
    )
    with pytest.raises(ValueError, match="HTTPS"):
        AutomationApiSettings(
            host="100.100.100.100",
            access_scope="remote",
            remote_security="tunnel",
            remote_key="secret",
        ).validate()
    with pytest.raises(ValueError, match="HTTPS"):
        AutomationApiSettings(
            host="192.168.1.20",
            access_scope="remote",
            remote_security="tunnel",
            remote_key="secret",
        ).validate()


def test_concurrent_uploads_decode_one_request_at_a_time(tmp_path: Path, monkeypatch) -> None:
    import integration.automation.server as server_module

    active = 0
    maximum = 0
    lock = threading.Lock()

    def observed_decode(_stream, **_kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return Image.new("RGB", (10, 8), "white")

    monkeypatch.setattr(server_module, "image_from_stream", observed_decode)
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok")
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0),
        auth=AutomationApiAuth(local_token="local"),
        connection_file=tmp_path / "connection.json",
    )
    server.start()
    results: list[int] = []

    def submit() -> None:
        body, content_type = _multipart({"mode": "formula"}, [("input.png", _png())])
        status, _, _ = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=body,
            headers={
                "Authorization": "Bearer local",
                "Content-Type": content_type,
                "Prefer": "wait=2",
            },
        )
        results.append(status)

    threads = [threading.Thread(target=submit) for _ in range(3)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        assert results == [200, 200, 200]
        assert maximum == 1
    finally:
        server.stop()
        coordinator.stop()


def test_remote_submission_rate_limit_returns_stable_error(tmp_path: Path) -> None:
    limits = AutomationLimits(remote_submissions_per_minute=1)
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok", limits=limits)
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0, remote_key="remote"),
        auth=AutomationApiAuth(local_token="local", remote_key="remote"),
        limits=limits,
        connection_file=tmp_path / "connection.json",
    )
    server.start()
    try:
        statuses = []
        errors = []
        for _ in range(2):
            body, content_type = _multipart({"mode": "formula"}, [("input.png", _png())])
            status, _, result = _request(
                server,
                "POST",
                "/api/v1/recognition/jobs",
                body=body,
                headers={
                    "Authorization": "Bearer remote",
                    "Content-Type": content_type,
                    "Prefer": "wait=2",
                },
            )
            statuses.append(status)
            errors.append((result.get("error") or {}).get("code"))
        assert statuses == [200, 429]
        assert errors == [None, "rate_limited"]
    finally:
        server.stop()
        coordinator.stop()


def test_windows_private_file_acl_targets_only_current_sid(tmp_path: Path, monkeypatch) -> None:
    import runtime.private_files as private_files

    calls: list[list[str]] = []

    def run(command, **_kwargs):
        calls.append(command)
        stdout = '"DESKTOP\\User","S-1-5-21-123"\n' if command[0] == "whoami" else ""
        return types.SimpleNamespace(stdout=stdout)

    target = tmp_path / "secret.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(private_files, "_is_windows", lambda: True)
    monkeypatch.setattr(private_files.subprocess, "run", run)
    restrict_file_to_current_user(target)
    assert calls[0][:2] == ["whoami", "/user"]
    assert calls[1] == [
        "icacls",
        str(target),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-21-123:(F)",
    ]


def test_next_result_idempotency_and_publication(tmp_path: Path) -> None:
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok")
    server = AutomationApiServer(
        coordinator,
        settings=AutomationApiSettings(port=0),
        auth=AutomationApiAuth(local_token="local"),
        connection_file=tmp_path / "connection.json",
    )
    server.start()
    body = json.dumps({"input": {"type": "next_result"}}).encode()
    headers = {
        "Authorization": "Bearer local",
        "Content-Type": "application/json",
        "Idempotency-Key": "next-result-retry",
    }
    try:
        first = _request(server, "POST", "/api/v1/recognition/jobs", body=body, headers=headers)
        second = _request(server, "POST", "/api/v1/recognition/jobs", body=body, headers=headers)
        assert first[0] == second[0] == 202
        assert first[2]["job"]["id"] == second[2]["job"]["id"]
        assert first[2]["job"]["state"] == "awaiting_result"
        assert coordinator.publish_next_result("x^2", backend="mathcraft", mode="formula")
        status, _, completed = _request(
            server,
            "GET",
            f"/api/v1/recognition/jobs/{first[2]['job']['id']}",
            headers={"Authorization": "Bearer local"},
        )
        assert status == 200
        assert completed["job"]["items"][0]["text"] == "x^2"

        legacy_body = json.dumps({"input": {"type": "desktop_capture"}}).encode()
        status, _, error = _request(
            server,
            "POST",
            "/api/v1/recognition/jobs",
            body=legacy_body,
            headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
        )
        assert status == 400 and error["error"]["code"] == "invalid_request"
    finally:
        server.stop()
        coordinator.stop()

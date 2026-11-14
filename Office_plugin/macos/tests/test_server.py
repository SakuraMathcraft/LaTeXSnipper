from __future__ import annotations

import http.client
import json
import shutil
import ssl
import sys
from pathlib import Path

import pytest
from latexsnipper_office.assets import OfficeAddinAssets, source_assets
from latexsnipper_office.certificate import OPENSSL, ensure_certificate
from latexsnipper_office.server import (
    API_HEADER,
    TYPOGRAPHY_ADAPTER_PATH,
    OfficeAddinServer,
    OfficeApiError,
)

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(
    not Path(OPENSSL).is_file() or sys.platform == "win32",
    reason="the loopback certificate is created with the system OpenSSL",
)


class FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def catalog(self):
        return {"symbolFonts": ["mathjax-tex"]}

    def font_outlines(self, runs):
        self.calls.append(("font_outlines", runs))
        return {"outlines": {run["key"]: {"Path": ""} for run in runs}}

    def mathml_to_omml(self, mathml, typography):
        self.calls.append(("omml", (mathml, typography)))
        return "<m:oMath/>"

    def load_settings(self, host):
        return {"host": host}

    def save_settings(self, host, payload):
        self.calls.append(("save", (host, payload)))
        if payload.get("invalid"):
            raise OfficeApiError(422, "invalid_settings", "bad")
        return {"host": host, **payload}

    def import_settings(self, host):
        return {"kind": "import"}

    def export_settings(self, host):
        return {"kind": "export"}

    def recognition_config(self):
        return {"ok": True}

    def create_next_result_job(self, timeout):
        self.calls.append(("next", timeout))
        return {"job": {"id": "job-1"}}

    def recognition_job(self, job_id):
        return {"job": {"id": job_id, "state": "running"}}

    def cancel_recognition_job(self, job_id):
        self.calls.append(("cancel", job_id))
        return {"job": {"id": job_id, "state": "canceled"}}

    def write_word_variables(self, marker, values):
        self.calls.append(("variables", (marker, values)))
        return {"written": len(values)}


@pytest.fixture(scope="module")
def identity(tmp_path_factory):
    return ensure_certificate(tmp_path_factory.mktemp("cert"))[0]


@pytest.fixture
def running(identity, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "taskpane.html").write_text("<p>pane</p>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    repository = source_assets(ROOT, ROOT / "src/assets/MathJax")
    assets = OfficeAddinAssets(
        web=web,
        shared_editor=repository.shared_editor,
        typography_adapter=repository.typography_adapter,
        manifest_template=repository.manifest_template,
        mathjax=repository.mathjax,
        support=repository.support,
    )
    services = FakeServices()
    server = OfficeAddinServer(
        assets=assets, certificate=identity, services=services, port=0
    )
    # Port 0 lets the OS choose; record the real port for Host checks.
    server.start()
    server.port = server._server.server_address[1]
    context = ssl.create_default_context(cafile=str(identity.certificate))
    yield server, services, context
    server.stop()


def connect(server, context):
    return http.client.HTTPSConnection(
        "localhost", server.port, context=context, timeout=10
    )


def request(server, context, method, path, body=None, headers=None, connection=None):
    connection = connection or connect(server, context)
    sent = {API_HEADER: "1", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body)
        sent["Content-Type"] = "application/json"
    connection.request(method, path, data, sent)
    response = connection.getresponse()
    raw = response.read()
    return response, raw


def test_serves_add_in_pages_and_shared_assets(running):
    server, _, context = running
    response, body = request(server, context, "GET", "/addin/taskpane.html")
    assert response.status == 200
    assert body == b"<p>pane</p>"
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    for path in (
        "/shared/editor.js",
        "/mathjax/startup.js",
        TYPOGRAPHY_ADAPTER_PATH,
        "/support/alipay.jpg",
    ):
        response, _ = request(server, context, "GET", path)
        assert response.status == 200, path


@pytest.mark.parametrize(
    "path",
    [
        "/addin/../secret.txt",
        "/addin/%2e%2e/secret.txt",
        "/addin/..%2fsecret.txt",
        "/",
        "/elsewhere/x",
        "/addin/",
    ],
)
def test_static_paths_cannot_leave_their_roots(running, path):
    server, _, context = running
    connection = connect(server, context)
    connection.putrequest("GET", path, skip_accept_encoding=True)
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 404
    assert b"outside" not in response.read()


def test_api_requires_marker_header(running):
    server, _, context = running
    connection = connect(server, context)
    connection.request("GET", "/api/catalog")
    response = connection.getresponse()
    assert response.status == 403
    assert json.loads(response.read())["error"]["code"] == "forbidden"


def test_api_rejects_foreign_origin_and_preflight(running):
    server, _, context = running
    response, _ = request(
        server,
        context,
        "GET",
        "/api/catalog",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status == 403
    response, _ = request(
        server,
        context,
        "OPTIONS",
        "/api/catalog",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status == 403
    assert response.getheader("Access-Control-Allow-Origin") is None
    response, _ = request(
        server,
        context,
        "GET",
        "/api/catalog",
        headers={"Origin": f"https://localhost:{server.port}"},
    )
    assert response.status == 200


def test_rejects_unexpected_host_header(running):
    server, _, context = running
    response, _ = request(
        server, context, "GET", "/api/health", headers={"Host": "attacker.example"}
    )
    assert response.status == 421


def test_keep_alive_requests_each_read_their_own_body(running):
    server, services, context = running
    connection = connect(server, context)
    response, _ = request(
        server,
        context,
        "POST",
        "/api/recognition/next",
        {"timeout": 30},
        connection=connection,
    )
    assert response.status == 200
    response, raw = request(
        server,
        context,
        "POST",
        "/api/omml",
        {"mathml": "<math/>", "typography": {"a": 1}},
        connection=connection,
    )
    assert response.status == 200, raw
    assert ("omml", ("<math/>", {"a": 1})) in services.calls
    response, _ = request(
        server, context, "POST", "/api/omml", {}, connection=connection
    )
    assert response.status == 400


def test_routes_reach_services(running):
    server, services, context = running
    assert request(server, context, "GET", "/api/settings/powerpoint")[0].status == 200
    response, raw = request(
        server, context, "PUT", "/api/settings/word", {"invalid": True}
    )
    assert response.status == 422
    assert json.loads(raw)["error"]["code"] == "invalid_settings"
    assert request(server, context, "GET", "/api/settings/excel")[0].status == 404
    assert (
        request(server, context, "DELETE", "/api/recognition/jobs/job-1")[0].status
        == 200
    )
    assert ("cancel", "job-1") in services.calls
    body = {
        "marker": "_LSLink0123456789abcdef",
        "values": {"LaTeXSnipper.DocumentId": "a" * 32},
    }
    assert (
        request(server, context, "POST", "/api/word/variables", body)[0].status == 200
    )
    assert ("variables", (body["marker"], body["values"])) in services.calls
    assert (
        request(server, context, "GET", "/api/recognition/jobs/..%2f")[0].status == 404
    )
    assert (
        request(server, context, "POST", "/api/recognition/next", {"timeout": 0})[
            0
        ].status
        == 400
    )
    runs = [{"key": "k", "text": "x", "family": "Times New Roman", "style": 0}]
    response, raw = request(
        server, context, "POST", "/api/font-outlines", {"runs": runs}
    )
    assert json.loads(raw) == {"outlines": {"k": {"Path": ""}}}


def test_rejects_oversized_and_malformed_bodies(running):
    server, _, context = running
    connection = connect(server, context)
    connection.request(
        "POST", "/api/omml", b"{", {API_HEADER: "1", "Content-Type": "application/json"}
    )
    response = connection.getresponse()
    assert response.status == 400
    response.read()
    connection = connect(server, context)
    connection.putrequest("POST", "/api/omml")
    connection.putheader(API_HEADER, "1")
    connection.putheader("Content-Length", str(64 * 1024 * 1024))
    connection.endheaders()
    response = connection.getresponse()
    assert response.status == 413


def test_internal_errors_do_not_leak_details(running):
    server, services, context = running

    def broken():
        raise RuntimeError("/private/detail/path")

    services.catalog = broken
    response, raw = request(server, context, "GET", "/api/catalog")
    assert response.status == 500
    assert b"/private/detail" not in raw


def test_validate_reports_missing_assets(tmp_path):
    assets = OfficeAddinAssets(
        *(tmp_path / name for name in ("w", "s", "a.js", "m.xml", "mj", "sup"))
    )
    with pytest.raises(FileNotFoundError):
        assets.validate()


def test_packaged_layout_is_self_contained(tmp_path):
    sys.path.insert(0, str(ROOT / "Office_plugin/macos"))
    try:
        import build
    finally:
        sys.path.remove(str(ROOT / "Office_plugin/macos"))
    from latexsnipper_office.assets import packaged_assets

    addin = build.assemble_resources(tmp_path)
    assets = packaged_assets(addin, addin / "MathJax")
    assets.validate()
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == build.version()
    assert (addin / "support/alipay.jpg").is_file()
    # Only the Office MathJax profile: SVG output, no CHTML fonts.
    assert not list((addin / "MathJax").rglob("chtml*"))
    assert not list(addin.rglob(".DS_Store"))
    shutil.rmtree(tmp_path / "office_addin")

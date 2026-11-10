"""Check that model downloads fall back to certifi without a system trust store."""

from __future__ import annotations

import ssl
import sys
from types import SimpleNamespace

import pytest

import mathcraft_ocr.downloader as downloader_mod


def _fake_paths(cafile: str = "", capath: str = "") -> SimpleNamespace:
    return SimpleNamespace(cafile=cafile, capath=capath)


def test_system_trust_store_keeps_default_context(monkeypatch, tmp_path):
    bundle = tmp_path / "cert.pem"
    bundle.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(
        downloader_mod.ssl, "get_default_verify_paths", lambda: _fake_paths(str(bundle))
    )
    # A real trust store means urllib already works; do not override it.
    assert downloader_mod._fallback_ssl_context() is None


def test_configured_but_missing_store_falls_back_to_certifi(monkeypatch, tmp_path):
    bundle = tmp_path / "cacert.pem"
    bundle.write_text("dummy", encoding="utf-8")
    # python.org framework builds report a cafile path that was never created.
    monkeypatch.setattr(
        downloader_mod.ssl,
        "get_default_verify_paths",
        lambda: _fake_paths(str(tmp_path / "missing.pem")),
    )
    monkeypatch.setitem(
        sys.modules, "certifi", SimpleNamespace(where=lambda: str(bundle))
    )
    built: list[dict] = []
    real_context = ssl.create_default_context()

    def _create_context(**kwargs):
        built.append(kwargs)
        return real_context

    monkeypatch.setattr(downloader_mod.ssl, "create_default_context", _create_context)
    context = downloader_mod._fallback_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert built == [{"cafile": str(bundle)}]
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_missing_certifi_bundle_leaves_urllib_default(monkeypatch, tmp_path):
    monkeypatch.setattr(
        downloader_mod.ssl, "get_default_verify_paths", lambda: _fake_paths()
    )
    monkeypatch.setitem(
        sys.modules,
        "certifi",
        SimpleNamespace(where=lambda: str(tmp_path / "absent.pem")),
    )
    assert downloader_mod._fallback_ssl_context() is None


def test_import_failure_leaves_urllib_default(monkeypatch):
    monkeypatch.setattr(
        downloader_mod.ssl, "get_default_verify_paths", lambda: _fake_paths()
    )
    monkeypatch.setitem(sys.modules, "certifi", None)
    assert downloader_mod._fallback_ssl_context() is None


@pytest.mark.parametrize("exc", [RuntimeError("boom")])
def test_unexpected_error_is_suppressed(monkeypatch, exc):
    def _raise():
        raise exc

    monkeypatch.setattr(downloader_mod.ssl, "get_default_verify_paths", _raise)
    assert downloader_mod._fallback_ssl_context() is None

"""Check how model downloads select a TLS trust store."""

from __future__ import annotations

import ssl
import sys
from types import SimpleNamespace

import pytest

import mathcraft_ocr.downloader as downloader_mod


@pytest.fixture
def missing_ca_paths(monkeypatch, tmp_path):
    paths = ssl.get_default_verify_paths()
    monkeypatch.setenv(paths.openssl_cafile_env, str(tmp_path / "missing.pem"))
    monkeypatch.setenv(paths.openssl_capath_env, str(tmp_path / "missing-certs"))


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_other_platforms_keep_default_context(monkeypatch, missing_ca_paths, platform):
    monkeypatch.setattr(downloader_mod, "sys", SimpleNamespace(platform=platform))
    assert downloader_mod._fallback_ssl_context() is None


@pytest.fixture
def macos_without_ca_paths(monkeypatch, missing_ca_paths):
    monkeypatch.setattr(downloader_mod, "sys", SimpleNamespace(platform="darwin"))


def test_macos_with_ca_file_keeps_default_context(
    monkeypatch, macos_without_ca_paths, tmp_path
):
    bundle = tmp_path / "cacert.pem"
    bundle.touch()
    monkeypatch.setenv(ssl.get_default_verify_paths().openssl_cafile_env, str(bundle))
    assert downloader_mod._fallback_ssl_context() is None


def test_macos_without_ca_paths_uses_verified_context(macos_without_ca_paths):
    context = downloader_mod._fallback_ssl_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.cert_store_stats()["x509_ca"] > 0
    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_missing_certifi_bundle_leaves_urllib_default(
    monkeypatch, macos_without_ca_paths, tmp_path
):
    monkeypatch.setitem(
        sys.modules,
        "certifi",
        SimpleNamespace(where=lambda: str(tmp_path / "absent.pem")),
    )
    assert downloader_mod._fallback_ssl_context() is None


def test_import_failure_leaves_urllib_default(monkeypatch, macos_without_ca_paths):
    monkeypatch.setitem(sys.modules, "certifi", None)
    assert downloader_mod._fallback_ssl_context() is None

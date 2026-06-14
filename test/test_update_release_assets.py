from __future__ import annotations

import importlib
import sys
import types
from urllib.parse import urlparse


class _FakeQUrl:
    def __init__(self, url: str):
        self._url = url

    def path(self) -> str:
        return urlparse(self._url).path


def _load_release_assets(monkeypatch):
    pyqt6 = types.ModuleType("PyQt6")
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.QUrl = _FakeQUrl
    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)
    sys.modules.pop("update.release_assets", None)
    return importlib.import_module("update.release_assets")


def _asset(name: str) -> dict:
    return {
        "name": name,
        "browser_download_url": f"https://example.test/{name}",
        "size": 42,
    }


def test_macos_release_asset_prefers_dmg_over_windows_installer(monkeypatch) -> None:
    release_assets = _load_release_assets(monkeypatch)
    monkeypatch.setattr(release_assets.sys, "platform", "darwin")

    picked = release_assets._pick_release_asset(
        {
            "assets": [
                _asset("LaTeXSnipperSetup-2.4.0.exe"),
                _asset("LaTeXSnipper_2.4.0_arm64.app.zip"),
                _asset("LaTeXSnipper_2.4.0_arm64.dmg"),
                _asset("SHA256SUMS-macos.txt"),
            ]
        }
    )

    assert picked[1] == "LaTeXSnipper_2.4.0_arm64.dmg"


def test_linux_release_asset_prefers_deb(monkeypatch) -> None:
    release_assets = _load_release_assets(monkeypatch)
    monkeypatch.setattr(release_assets.sys, "platform", "linux")

    picked = release_assets._pick_release_asset(
        {
            "assets": [
                _asset("LaTeXSnipperSetup-2.4.0.exe"),
                _asset("LaTeXSnipper_2.4.0_arm64.dmg"),
                _asset("latexsnipper_2.4.0_amd64.deb"),
            ]
        }
    )

    assert picked[1] == "latexsnipper_2.4.0_amd64.deb"


def test_windows_release_asset_keeps_setup_exe_preferred(monkeypatch) -> None:
    release_assets = _load_release_assets(monkeypatch)
    monkeypatch.setattr(release_assets.sys, "platform", "win32")

    picked = release_assets._pick_release_asset(
        {
            "assets": [
                _asset("LaTeXSnipper_2.4.0_arm64.dmg"),
                _asset("OfficePluginSetup-2.4.0.exe"),
                _asset("LaTeXSnipperSetup-2.4.0.exe"),
                _asset("LaTeXSnipper_2.4.0_amd64.deb"),
            ]
        }
    )

    assert picked[1] == "LaTeXSnipperSetup-2.4.0.exe"

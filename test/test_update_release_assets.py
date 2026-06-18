from __future__ import annotations

import sys

from update.release_assets import _release_info_from_payload
from update.release_types import _compare_versions, _stable_tag_key


def _release_payload() -> dict:
    names = [
        "OfficePluginSetup-2.4.0.exe",
        "LaTeXSnipperSetup-2.4.0.exe",
        "LaTeXSnipper_2.4.0_amd64.deb",
        "LaTeXSnipper_2.4.0_arm64.dmg",
        "LaTeXSnipper_2.4.0_arm64.app.zip",
        "LaTeXSnipper_User_Manual.pdf",
    ]
    return {
        "tag_name": "v2.4.0 LTS",
        "html_url": "https://github.com/SakuraMathcraft/LaTeXSnipper/releases/tag/v2.4.0-LTS",
        "body": "Stable release",
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://example.invalid/{name}",
                "id": str(index),
                "size": 100 + index,
                "updated_at": "2026-06-18T00:00:00Z",
                "digest": "sha256:" + str(index % 10) * 64,
            }
            for index, name in enumerate(names, start=1)
        ],
    }


def test_lts_release_tag_compares_as_stable_semver() -> None:
    assert _stable_tag_key("v2.4.0 LTS") == (2, 4, 0)
    assert _stable_tag_key("v2.4.0-LTS") == (2, 4, 0)
    assert _stable_tag_key("v2.4.0-rc1") == ()
    assert _compare_versions("v2.4.0 LTS", "v2.4.0") == 0


def test_windows_update_chooses_main_installer_not_office_plugin(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    info = _release_info_from_payload(_release_payload())

    assert info.asset_name == "LaTeXSnipperSetup-2.4.0.exe"
    assert "OfficePluginSetup" not in info.asset_name


def test_macos_update_chooses_dmg_for_current_arch(monkeypatch) -> None:
    import update.release_assets as release_assets

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(release_assets.platform, "machine", lambda: "arm64")
    info = _release_info_from_payload(_release_payload())

    assert info.asset_name == "LaTeXSnipper_2.4.0_arm64.dmg"


def test_linux_update_chooses_debian_package(monkeypatch) -> None:
    import update.release_assets as release_assets

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(release_assets.platform, "machine", lambda: "x86_64")
    info = _release_info_from_payload(_release_payload())

    assert info.asset_name == "LaTeXSnipper_2.4.0_amd64.deb"


def test_update_has_no_generic_asset_fallback(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    payload = _release_payload()
    payload["assets"] = [
        {
            "name": "LaTeXSnipper_User_Manual.pdf",
            "browser_download_url": "https://example.invalid/manual.pdf",
        },
        {
            "name": "OfficePluginSetup-2.4.0.exe",
            "browser_download_url": "https://example.invalid/OfficePluginSetup-2.4.0.exe",
        },
    ]
    info = _release_info_from_payload(payload)

    assert info.asset_name == ""
    assert info.asset_url == ""

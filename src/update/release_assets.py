import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from update.release_types import ReleaseInfo, _normalize_sha256

_WINDOWS_ASSET_SUFFIXES = (".exe", ".msi", ".zip")
_MACOS_ASSET_SUFFIXES = (".dmg", ".app.zip", ".zip")
_LINUX_ASSET_SUFFIXES = (".deb", ".appimage", ".rpm", ".tar.gz", ".zip")
_FALLBACK_ASSET_SUFFIXES = (
    ".exe",
    ".msi",
    ".dmg",
    ".app.zip",
    ".deb",
    ".appimage",
    ".rpm",
    ".tar.gz",
    ".zip",
)
_ASSET_SIDECAR_SUFFIXES = (
    ".sigstore.json",
    ".sha256",
    ".sha256sum",
    ".sha256.txt",
)


def _asset_sha256_from_payload(payload: dict) -> str:
    return _normalize_sha256(
        payload.get("asset_sha256")
        or payload.get("sha256")
        or payload.get("sha256_digest")
        or payload.get("digest")
        or payload.get("hash")
    )


def _platform_asset_suffixes(platform: str | None = None) -> tuple[str, ...]:
    value = (platform or sys.platform or "").lower()
    if value == "darwin":
        return _MACOS_ASSET_SUFFIXES
    if value == "win32":
        return _WINDOWS_ASSET_SUFFIXES
    if value.startswith("linux"):
        return _LINUX_ASSET_SUFFIXES
    return _FALLBACK_ASSET_SUFFIXES


def _asset_supported_suffix_rank(name: str, *, platform: str | None = None) -> int:
    lower = str(name or "").lower()
    suffixes = _platform_asset_suffixes(platform)
    for rank, suffix in enumerate(suffixes):
        if lower.endswith(suffix):
            return rank
    return len(suffixes)


def _is_asset_sidecar(name: str) -> bool:
    lower = str(name or "").lower()
    return any(lower.endswith(suffix) for suffix in _ASSET_SIDECAR_SUFFIXES)


def _installer_channel_rank(name: str) -> int:
    compact = re.sub(r"[^a-z0-9]+", "", str(name or "").lower())
    is_latexsnipper = "latexsnipper" in compact
    is_setup = "setup" in compact
    is_offline = "offline" in compact
    if is_latexsnipper and is_setup and not is_offline:
        return 0
    if is_setup and not is_offline:
        return 1
    if is_latexsnipper and is_setup and is_offline:
        return 2
    if is_offline:
        return 3
    return 4


def _asset_channel_rank(name: str, *, platform: str | None = None) -> int:
    value = (platform or sys.platform or "").lower()
    if value == "win32":
        return _installer_channel_rank(name)
    compact = re.sub(r"[^a-z0-9]+", "", str(name or "").lower())
    if "latexsnipper" in compact and "office" not in compact:
        return 0
    return 1


def _release_asset_sort_key(asset: dict) -> tuple[int, int, int, str]:
    name = str(asset.get("name", "") or "")
    return (
        _asset_supported_suffix_rank(name),
        1 if _is_asset_sidecar(name) else 0,
        _asset_channel_rank(name),
        name.lower(),
    )


def _release_asset_tuple(asset: dict) -> tuple[str, str, str, int, str, str]:
    name = str(asset.get("name", "") or "")
    return (
        str(asset.get("browser_download_url", "") or ""),
        name,
        str(asset.get("id", "") or ""),
        int(asset.get("size", 0) or 0),
        str(asset.get("updated_at", "") or ""),
        _asset_sha256_from_payload(asset),
    )


def _pick_release_asset(rel: dict) -> tuple[str, str, str, int, str, str]:
    assets = rel.get("assets") or []
    if not isinstance(assets, list):
        return "", "", "", 0, "", ""
    candidates = [
        asset
        for asset in assets
        if isinstance(asset, dict) and str(asset.get("browser_download_url", "") or "")
    ]
    if not candidates:
        return "", "", "", 0, "", ""
    installers = [
        asset
        for asset in candidates
        if _asset_supported_suffix_rank(str(asset.get("name", "") or ""))
        < len(_platform_asset_suffixes())
        and not _is_asset_sidecar(str(asset.get("name", "") or ""))
    ]
    if installers:
        return _release_asset_tuple(min(installers, key=_release_asset_sort_key))
    if candidates:
        return _release_asset_tuple(candidates[0])
    return "", "", "", 0, "", ""


def _release_info_from_payload(rel: dict) -> ReleaseInfo:
    return ReleaseInfo(
        rel.get("tag_name", ""),
        rel.get("html_url", ""),
        rel.get("body", ""),
        *_pick_release_asset(rel),
    )


def _release_page_url(url: str) -> bool:
    path = str(urlparse(str(url or "")).path or "").lower()
    return "/releases/tag/" in path or path.endswith("/releases/latest")


def _normalize_download_asset(url: str, name: str) -> tuple[str, str]:
    clean_url = str(url or "").strip()
    clean_name = str(name or "").strip()
    if not clean_url or _release_page_url(clean_url):
        return "", ""
    if not clean_name:
        try:
            clean_name = Path(unquote(urlparse(clean_url).path or "")).name
        except Exception:
            clean_name = ""
    if not clean_name or "." not in Path(clean_name).name:
        return "", ""
    return clean_url, clean_name

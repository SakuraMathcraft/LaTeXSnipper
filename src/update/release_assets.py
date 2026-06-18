import platform
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl

from update.release_types import ReleaseInfo, _normalize_sha256

_INSTALLER_ASSET_SUFFIXES = (".exe", ".dmg", ".deb", ".app.zip")
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


def _asset_supported_suffix_rank(name: str) -> int:
    lower = str(name or "").lower()
    for rank, suffix in enumerate(sorted(_INSTALLER_ASSET_SUFFIXES, key=len, reverse=True)):
        if lower.endswith(suffix):
            return rank
    return len(_INSTALLER_ASSET_SUFFIXES)


def _is_asset_sidecar(name: str) -> bool:
    lower = str(name or "").lower()
    return any(lower.endswith(suffix) for suffix in _ASSET_SIDECAR_SUFFIXES)


def _platform_asset_rank(name: str) -> int | None:
    lower = str(name or "").lower()
    compact = re.sub(r"[^a-z0-9]+", "", lower)
    machine = platform.machine().lower()

    if sys.platform.startswith("win"):
        if lower.endswith(".exe") and compact.startswith("latexsnippersetup"):
            return 0
        return None

    if sys.platform == "darwin":
        if not compact.startswith("latexsnipper") or not lower.endswith((".dmg", ".app.zip")):
            return None
        if "universal" in lower:
            arch_rank = 0
        elif machine in {"arm64", "aarch64"}:
            arch_rank = 0 if "arm64" in lower or "aarch64" in lower else 2
        elif machine in {"x86_64", "amd64"}:
            arch_rank = 0 if "x86_64" in lower or "x64" in lower or "amd64" in lower else 2
        else:
            arch_rank = 1
        suffix_rank = 0 if lower.endswith(".dmg") else 1
        return arch_rank * 10 + suffix_rank

    if sys.platform.startswith("linux"):
        if not compact.startswith("latexsnipper") or not lower.endswith(".deb"):
            return None
        if machine in {"x86_64", "amd64"}:
            return 0 if "amd64" in lower or "x86_64" in lower else 2
        if machine in {"arm64", "aarch64"}:
            return 0 if "arm64" in lower or "aarch64" in lower else 2
        return 1

    return None


def _release_asset_sort_key(asset: dict) -> tuple[int, int, int, str]:
    name = str(asset.get("name", "") or "")
    platform_rank = _platform_asset_rank(name)
    if platform_rank is None:
        platform_rank = 999
    return (
        platform_rank,
        _asset_supported_suffix_rank(name),
        1 if _is_asset_sidecar(name) else 0,
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
        < len(_INSTALLER_ASSET_SUFFIXES)
        and not _is_asset_sidecar(str(asset.get("name", "") or ""))
        and _platform_asset_rank(str(asset.get("name", "") or "")) is not None
    ]
    if installers:
        return _release_asset_tuple(min(installers, key=_release_asset_sort_key))
    return "", "", "", 0, "", ""


def _release_info_from_payload(rel: dict) -> ReleaseInfo:
    return ReleaseInfo(
        rel.get("tag_name", ""),
        rel.get("html_url", ""),
        rel.get("body", ""),
        *_pick_release_asset(rel),
    )


def _release_page_url(url: str) -> bool:
    path = str(QUrl(url).path() or "").lower()
    return "/releases/tag/" in path or path.endswith("/releases/latest")


def _normalize_download_asset(url: str, name: str) -> tuple[str, str]:
    clean_url = str(url or "").strip()
    clean_name = str(name or "").strip()
    if not clean_url or _release_page_url(clean_url):
        return "", ""
    if not clean_name:
        try:
            clean_name = Path(QUrl(clean_url).path()).name
        except Exception:
            clean_name = ""
    if not clean_name or "." not in Path(clean_name).name:
        return "", ""
    return clean_url, clean_name

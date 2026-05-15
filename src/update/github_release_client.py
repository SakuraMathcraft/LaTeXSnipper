import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from update.release_assets import _release_info_from_payload
from update.release_cache import _load_cached_info, _save_cached_info
from update.release_types import (
    CONNECT_TIMEOUT,
    DEBUG_LOG,
    READ_TIMEOUT,
    ReleaseInfo,
    __version__,
    _API_RELEASES,
    _brief_error_message,
    _compare_versions,
    _stable_tag_key,
)

_session = requests.Session()
_session.headers.update({
    "User-Agent": "LaTeXSnipper-Updater/1.0 (+https://github.com/SakuraMathcraft/LaTeXSnipper)"
})


def _resolve_ca_bundle_path() -> str | None:
    """
    Resolve a usable TLS CA bundle path for frozen builds.
    Prefer certifi; fallback to pip vendored certifi bundle if needed.
    """
    candidates: list[str] = []

    # 1) certifi default path
    try:
        import certifi  # type: ignore
        p = certifi.where()
        if p:
            candidates.append(str(p))
    except Exception:
        pass

    # 2) pip vendored certifi fallback
    try:
        from pip._vendor import certifi as pip_certifi  # type: ignore
        p = pip_certifi.where()
        if p:
            candidates.append(str(p))
    except Exception:
        pass

    # 3) common frozen/runtime locations
    roots = []
    try:
        roots.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
    except Exception:
        pass

    rels = [
        Path("certifi") / "cacert.pem",
        Path("_internal") / "certifi" / "cacert.pem",
        Path("pip") / "_vendor" / "certifi" / "cacert.pem",
        Path("_internal") / "pip" / "_vendor" / "certifi" / "cacert.pem",
    ]
    for root in roots:
        for rel in rels:
            candidates.append(str(root / rel))

    seen = set()
    for raw in candidates:
        if not raw:
            continue
        p = str(Path(raw))
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if Path(p).is_file():
                return p
        except Exception:
            continue
    return None


def _configure_tls_verify():
    """
    Bind requests session to a valid CA bundle path when available.
    This avoids frozen-path CA issues caused by missing certifi data.
    """
    ca_path = _resolve_ca_bundle_path()
    if ca_path:
        _session.verify = ca_path
        # Set envs for child requests/urllib callers in this process.
        os.environ["REQUESTS_CA_BUNDLE"] = ca_path
        os.environ["SSL_CERT_FILE"] = ca_path
        if DEBUG_LOG:
            print(f"[Updater] TLS CA bundle: {ca_path}")
    else:
        if DEBUG_LOG:
            print("[Updater] WARN: no CA bundle file found; update check may fail on HTTPS.")


def _attach_auth_headers(h: dict):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token.strip()}"
    h["Accept"] = "application/vnd.github+json"
    h["X-GitHub-Api-Version"] = "2022-11-28"


def _fmt_reset(ts_utc: Optional[str]):
    if not ts_utc:
        return "未知"
    try:
        dt = datetime.fromtimestamp(int(ts_utc), tz=timezone.utc)
        return dt.astimezone().strftime("%H:%M:%S")
    except Exception:
        return ts_utc


def _fetch_latest_release_fallback(
    diagnostics: List[Tuple[str, str]]
) -> tuple[Optional[ReleaseInfo], str]:
    latest_api = f"{_API_RELEASES}/latest"
    headers: Dict[str, str] = {}
    _attach_auth_headers(headers)
    try:
        resp = _session.get(latest_api, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        if resp.status_code == 404:
            diagnostics.append((latest_api, "latest release not found"))
            return None, ""
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or not payload.get("tag_name"):
            diagnostics.append((latest_api, "invalid latest release response"))
            return None, ""
        return _release_info_from_payload(payload), str(resp.headers.get("ETag") or "")
    except Exception as e:
        diagnostics.append((latest_api, _brief_error_message(e)))
        return None, ""


def _fetch_release() -> Tuple[Optional[ReleaseInfo], Optional[str], List[Tuple[str, str]]]:
    diagnostics: List[Tuple[str, str]] = []
    headers: Dict[str, str] = {}
    _attach_auth_headers(headers)
    etag, _, cached_info = _load_cached_info()
    # If the cached latest version is older than the current app version, the cache is clearly stale; bypass ETag and force a refetch.
    if cached_info and _compare_versions(cached_info.latest, __version__) < 0:
        etag = None
        cached_info = None
    if etag and cached_info:
        headers["If-None-Match"] = etag
    try:
        resp = _session.get(_API_RELEASES, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

        # Rate-limit reset hint; Remaining=0 is treated as exhausted.
        remain_header = resp.headers.get("X-RateLimit-Remaining")
        if resp.status_code == 200 and remain_header == "0":
            reset = resp.headers.get("X-RateLimit-Reset")
            msg = f"GitHub 限频: 剩余=0 重置≈{_fmt_reset(reset)}"
            diagnostics.append(("RATE_LIMIT", msg))  # Sentinel.

        if resp.status_code == 304:
            if cached_info:
                return cached_info, None, diagnostics
            diagnostics.append(("GitHub Releases API", "缓存已过期，请重新检查"))
            return None, "更新缓存失效，请重新检查。", diagnostics

        if resp.status_code == 403:
            remain = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            msg = f"GitHub 限频: 剩余={remain} 重置≈{_fmt_reset(reset)}"
            diagnostics.append((_API_RELEASES, msg))
            diagnostics.append(("RATE_LIMIT", msg))  # Sentinel.
            return None, "GitHub API 请求受限，请稍后重试或设置 GITHUB_TOKEN。", diagnostics

        resp.raise_for_status()

        new_etag = resp.headers.get("ETag")
        releases = resp.json()
        if not isinstance(releases, list):
            diagnostics.append((_API_RELEASES, "响应格式不是 release 列表"))
            return None, "GitHub Releases 响应格式异常。", diagnostics

        ordered = sorted(
            releases,
            key=lambda rel: rel.get("published_at") or rel.get("created_at") or "",
            reverse=True
        )

        stable_releases = [
            rel for rel in ordered
            if _stable_tag_key(rel.get("tag_name", ""))
        ]
        rel = stable_releases[0] if stable_releases else (ordered[0] if ordered else None)
        if not rel:
            diagnostics.append(("EMPTY_RELEASES", "GitHub Releases API returned an empty list"))
            fallback_info, fallback_etag = _fetch_latest_release_fallback(diagnostics)
            if fallback_info:
                if fallback_etag:
                    _save_cached_info(fallback_etag, fallback_info)
                return fallback_info, None, diagnostics
            if cached_info:
                diagnostics.append(("CACHE", "using cached release after empty GitHub response"))
                return cached_info, None, diagnostics
            return None, "GitHub 暂时没有返回发布列表，请稍后重试或打开发布页查看。", diagnostics

        info = _release_info_from_payload(rel)
        if new_etag:
            _save_cached_info(new_etag, info)
        return info, None, diagnostics

    except Exception as e:
        diagnostics.append((_API_RELEASES, _brief_error_message(e)))
        return None, _brief_error_message(e), diagnostics


_configure_tls_verify()

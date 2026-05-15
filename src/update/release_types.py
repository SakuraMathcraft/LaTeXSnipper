import os
import re
from dataclasses import dataclass

import requests

from runtime.distribution import APP_VERSION

_API_RELEASES = "https://api.github.com/repos/SakuraMathcraft/LaTeXSnipper/releases"
_RELEASES_PAGE = "https://github.com/SakuraMathcraft/LaTeXSnipper/releases"
__version__ = APP_VERSION

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 8
DEBUG_LOG = os.environ.get("LATEXSNIPPER_UPDATE_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@dataclass
class ReleaseInfo:
    latest: str
    url: str
    changelog: str = ""
    asset_url: str = ""
    asset_name: str = ""
    asset_id: str = ""
    asset_size: int = 0
    asset_updated_at: str = ""
    asset_sha256: str = ""


def _stable_tag_key(tag: str) -> tuple[int, ...]:
    raw = str(tag or "").strip().lower()
    if not raw:
        return tuple()
    if any(mark in raw for mark in ("beta", "alpha", "rc", "nightly", "preview")):
        return tuple()
    cleaned = raw.lstrip("v")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return tuple()
    return tuple(int(p) for p in parts)


def _compare_versions(left: str, right: str) -> int:
    left_key = _stable_tag_key(left)
    right_key = _stable_tag_key(right)
    if left_key and right_key:
        max_len = max(len(left_key), len(right_key))
        left_key += (0,) * (max_len - len(left_key))
        right_key += (0,) * (max_len - len(right_key))
        if left_key > right_key:
            return 1
        if left_key < right_key:
            return -1
        return 0
    left_raw = str(left or "").strip()
    right_raw = str(right or "").strip()
    if left_raw == right_raw:
        return 0
    return 1 if left_raw > right_raw else -1


def _normalize_sha256(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw.split(":", 1)[1].strip()
    raw = re.sub(r"\s+", "", raw)
    return raw if re.fullmatch(r"[0-9a-f]{64}", raw) else ""


def _brief_error_message(err: object, *, context: str = "update") -> str:
    if isinstance(err, requests.exceptions.Timeout):
        return "连接 GitHub 超时，请检查网络或代理后重试。"
    if isinstance(err, requests.exceptions.SSLError):
        return "TLS 证书校验失败，请检查系统证书、代理或安全软件设置。"
    if isinstance(err, requests.exceptions.ConnectionError):
        return "无法连接 GitHub，请检查网络、代理或 DNS 设置。"
    if isinstance(err, requests.exceptions.HTTPError):
        resp = getattr(err, "response", None)
        code = getattr(resp, "status_code", None)
        if code == 403:
            return "GitHub API 请求受限，请稍后重试或设置 GITHUB_TOKEN。"
        if code == 404:
            return "未找到可用的 GitHub Release，请确认发布页已创建。"
        if code:
            return f"GitHub API 返回 HTTP {code}，请稍后重试。"
    raw = " ".join(str(err or "").replace("\r", " ").replace("\n", " ").split())
    if not raw:
        return "更新请求失败，请检查网络后重试。"
    limit = 120 if context == "download" else 96
    return raw if len(raw) <= limit else raw[: limit - 3] + "..."

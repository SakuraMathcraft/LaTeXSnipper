import base64
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple, Dict

import requests
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QUrl
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextBrowser,
    QHBoxLayout, QProgressBar, QApplication, QMessageBox
)
from PyQt6.QtGui import QTextDocument, QFont
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from qfluentwidgets import PushButton, FluentIcon, InfoBar, InfoBarPosition

from runtime.distribution import APP_VERSION, is_store_distribution, store_update_uri

# ---------------- Constants ----------------
_ETAG_PATH = os.path.join(os.path.dirname(__file__), ".release_etag_cache.json")
_API_RELEASES = "https://api.github.com/repos/SakuraMathcraft/LaTeXSnipper/releases"
_RELEASES_PAGE = "https://github.com/SakuraMathcraft/LaTeXSnipper/releases"
_UPDATE_DIALOG: Optional[QDialog] = None
_RELEASE_CACHE_SCHEMA_VERSION = 2
__version__ = APP_VERSION

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 8
DEBUG_LOG = os.environ.get("LATEXSNIPPER_UPDATE_DEBUG", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_INSTALLER_ASSET_SUFFIXES = (".exe", ".msi", ".zip")
_ASSET_SIDECAR_SUFFIXES = (
    ".sigstore.json",
    ".sha256",
    ".sha256sum",
    ".sha256.txt",
)


def _resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = _resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

def _is_dark_ui() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    c = app.palette().window().color()
    return ((c.red() + c.green() + c.blue()) / 3.0) < 128


def _update_dialog_theme() -> dict:
    if _is_dark_ui():
        return {
            "dialog_bg": "#1b1f27",
            "text": "#e7ebf0",
            "muted": "#a9b3bf",
            "panel_bg": "#232934",
            "border": "#465162",
            "code_bg": "#161a20",
            "accent": "#4c9aff",
            "warn_bg": "#3e2e18",
            "warn_border": "#b8843b",
            "warn_text": "#ffd08a",
        }
    return {
        "dialog_bg": "#f5f7fa",
        "text": "#2e3135",
        "muted": "#555555",
        "panel_bg": "#ffffff",
        "border": "#cfd6dd",
        "code_bg": "#f6f8fa",
        "accent": "#1976d2",
        "warn_bg": "#fff4e0",
        "warn_border": "#f5c182",
        "warn_text": "#d35400",
    }

_session = requests.Session()
_session.headers.update({
    "User-Agent": "LaTeXSnipper-Updater/1.0 (+https://github.com/SakuraMathcraft/LaTeXSnipper)"
})


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    }
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs

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

_configure_tls_verify()

# ---------------- Data Structures ----------------
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

# ---------------- Helpers ----------------
def _load_cached_info():
    try:
        with open(_ETAG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if int(data.get("asset_policy_version", 0) or 0) != _RELEASE_CACHE_SCHEMA_VERSION:
            return None, 0, None
        etag = data.get("etag")
        ts = data.get("ts", 0)
        info_dict = data.get("info")
        if info_dict:
            info = ReleaseInfo(**info_dict)
        else:
            info = None
        return etag, ts, info
    except Exception:
        return None, 0, None

def _save_cached_info(etag: str, info: ReleaseInfo):
    try:
        with open(_ETAG_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "asset_policy_version": _RELEASE_CACHE_SCHEMA_VERSION,
                "etag": etag,
                "ts": int(time.time()),
                "info": {
                    "latest": info.latest,
                    "url": info.url,
                    "changelog": info.changelog,
                    "asset_url": info.asset_url,
                    "asset_name": info.asset_name,
                    "asset_id": info.asset_id,
                    "asset_size": info.asset_size,
                    "asset_updated_at": info.asset_updated_at,
                    "asset_sha256": info.asset_sha256,
                }
            }, f)
    except Exception:
        pass


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


def _asset_sha256_from_payload(payload: dict) -> str:
    return _normalize_sha256(
        payload.get("asset_sha256")
        or payload.get("sha256")
        or payload.get("sha256_digest")
        or payload.get("digest")
        or payload.get("hash")
    )


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


def _asset_supported_suffix_rank(name: str) -> int:
    lower = str(name or "").lower()
    for rank, suffix in enumerate(_INSTALLER_ASSET_SUFFIXES):
        if lower.endswith(suffix):
            return rank
    return len(_INSTALLER_ASSET_SUFFIXES)


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


def _release_asset_sort_key(asset: dict) -> tuple[int, int, int, str]:
    name = str(asset.get("name", "") or "")
    return (
        _asset_supported_suffix_rank(name),
        1 if _is_asset_sidecar(name) else 0,
        _installer_channel_rank(name),
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


def _compute_file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if chunk:
                h.update(chunk)
    return h.hexdigest()


def _schedule_windows_installer(path: str) -> None:
    installer = str(Path(path).resolve())
    script = Path(tempfile.gettempdir()) / f"latexsnipper-install-{os.getpid()}.vbs"
    script.write_text(
        "\n".join([
            'Set shell = CreateObject("WScript.Shell")',
            'Set fso = CreateObject("Scripting.FileSystemObject")',
            f'installer = "{installer.replace(chr(34), chr(34) * 2)}"',
            f'waitPid = "{os.getpid()}"',
            "Do",
            '  Set execObj = shell.Exec("cmd /c tasklist /FI ""PID eq " & waitPid & """ /NH")',
            "  output = LCase(execObj.StdOut.ReadAll())",
            '  If InStr(output, "no tasks are running") > 0 Or InStr(output, LCase(waitPid)) = 0 Then Exit Do',
            "  WScript.Sleep 1000",
            "Loop",
            'shell.Run Chr(34) & installer & Chr(34), 1, False',
            'On Error Resume Next',
            'fso.DeleteFile WScript.ScriptFullName, True',
        ]),
        encoding="utf-8",
    )
    subprocess.Popen(
        ["wscript.exe", "//B", "//NoLogo", str(script)],
        close_fds=True,
        **_hidden_subprocess_kwargs(),
    )


def _prepare_app_for_update_exit() -> None:
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            prepare_restart = getattr(widget, "prepare_restart", None)
            if callable(prepare_restart):
                prepare_restart()
                break
        except Exception:
            continue


def _update_dir() -> Path:
    update_dir = Path.home() / ".latexsnipper" / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    return update_dir


def _installer_meta_path() -> Path:
    return _update_dir() / "installer_meta.json"


def _asset_fingerprint(info: ReleaseInfo) -> dict:
    return {
        "latest": str(info.latest or ""),
        "asset_url": str(info.asset_url or ""),
        "asset_name": str(info.asset_name or ""),
        "asset_id": str(info.asset_id or ""),
        "asset_size": int(info.asset_size or 0),
        "asset_updated_at": str(info.asset_updated_at or ""),
        "asset_sha256": _normalize_sha256(info.asset_sha256),
    }


def _load_installer_meta() -> dict:
    try:
        with _installer_meta_path().open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_installer_meta(info: ReleaseInfo, path: str, sha256_hex: str) -> None:
    payload = _asset_fingerprint(info)
    payload["path"] = str(path or "")
    payload["sha256"] = str(sha256_hex or "")
    try:
        with _installer_meta_path().open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_installer_meta() -> None:
    try:
        _installer_meta_path().unlink(missing_ok=True)
    except Exception:
        pass

# ---------------- Main Fetch ----------------
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

# ---------------- Rich Text Browser ----------------
_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/"
_REL_IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\((?!https?://|data:)([^)]+)\)')
_MARK_TAG_PATTERN = re.compile(r"</?mark\b[^>]*>", re.IGNORECASE)

def _fix_relative_images(md: str) -> str:
    return _REL_IMG_PATTERN.sub(
        lambda m: f"![{m.group(1)}]({_GITHUB_RAW_PREFIX}{m.group(2).lstrip('./')})",
        md
    )


def _prepare_release_markdown(md: str) -> str:
    fixed = _fix_relative_images(md)
    return _MARK_TAG_PATTERN.sub("", fixed)


class RemoteImageBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._manager.finished.connect(self._on_reply)
        self._cache: Dict[str, bytes] = {}
        self._pending: Dict[str, QNetworkReply] = {}
        self._generation = 0

    def start_new_html(self, html: str):
        self._generation += 1
        self._abort_pending()
        super().setHtml(html)

    def start_new_markdown(self, markdown: str, stylesheet: str = ""):
        self._generation += 1
        self._abort_pending()
        if stylesheet:
            self.document().setDefaultStyleSheet(stylesheet)
        self.document().setMarkdown(
            markdown,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub,
        )

    def _abort_pending(self):
        for r in list(self._pending.values()):
            try:
                r.finished.disconnect(self._on_reply)
            except Exception:
                pass
            r.abort()
            r.deleteLater()
        self._pending.clear()

    def loadResource(self, rtype, url: QUrl):
        if rtype == QTextDocument.ResourceType.ImageResource and url.scheme() in ("http", "https"):
            key = url.toString()
            if key in self._cache:
                return self._cache[key]
            if key not in self._pending:
                reply = self._manager.get(QNetworkRequest(url))
                reply._gen = self._generation  # type: ignore
                self._pending[key] = reply
            # Transparent 1x1 placeholder.
            return base64.b64decode("R0lGODlhAQABAPAAAAAAAAAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")
        return super().loadResource(rtype, url)

    def _on_reply(self, reply: QNetworkReply):
        url = reply.url().toString()
        gen = getattr(reply, "_gen", -1)
        self._pending.pop(url, None)
        if gen == self._generation and reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            self._cache[url] = data
            self.document().addResource(QTextDocument.ResourceType.ImageResource, reply.url(), data)
            self.viewport().update()
        reply.deleteLater()

# ---------------- Main Dialog ----------------
def _show_existing_update_dialog():
    if _UPDATE_DIALOG is None:
        return None
    try:
        if _UPDATE_DIALOG.isVisible():
            _UPDATE_DIALOG.show()
            _UPDATE_DIALOG.raise_()
            _UPDATE_DIALOG.activateWindow()
            return _UPDATE_DIALOG
    except RuntimeError:
        pass
    _clear_global()
    return None


def _open_store_update_page(parent) -> None:
    try:
        import webbrowser

        webbrowser.open(store_update_uri())
    except Exception as e:
        InfoBar.error(
            title="无法打开 Microsoft Store",
            content=_brief_error_message(e),
            parent=parent,
            duration=3500,
            position=InfoBarPosition.TOP,
        )


def _store_update_dialog(parent=None):
    global _UPDATE_DIALOG
    existing = _show_existing_update_dialog()
    if existing is not None:
        return existing

    dlg = QDialog(parent)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowTitle("检查更新")
    dlg.setWindowFlags(
        (
            dlg.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
    )
    dlg.resize(520, 220)
    dlg.setModal(False)
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    _apply_app_window_icon(dlg)
    _UPDATE_DIALOG = dlg
    dlg.destroyed.connect(_clear_global)

    lay = QVBoxLayout(dlg)
    title = QLabel("版本更新")
    title_font = QFont(title.font())
    title_font.setPointSize(max(title_font.pointSize(), 14))
    title_font.setBold(True)
    title.setFont(title_font)
    lay.addWidget(title)

    lay.addWidget(QLabel(f"当前版本: {__version__}"))
    lay.addWidget(QLabel("当前渠道: Microsoft Store"))
    status = QLabel("此版本由 Microsoft Store 管理更新，不会下载 GitHub Release 安装包。")
    status.setWordWrap(True)
    lay.addWidget(status)

    desc = QLabel("如需更新，请打开 Microsoft Store 的库/下载页面，或等待 Store 自动更新。")
    desc.setWordWrap(True)
    lay.addWidget(desc)
    lay.addStretch()

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_store = PushButton(FluentIcon.LINK, "打开 Microsoft Store")
    btn_close = PushButton(FluentIcon.CLOSE, "关闭")
    for button in (btn_store, btn_close):
        button.setFixedHeight(32)
        btn_row.addWidget(button)
    lay.addLayout(btn_row)

    btn_store.clicked.connect(lambda: _open_store_update_page(dlg))
    btn_close.clicked.connect(dlg.close)

    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


def check_update_dialog(parent=None):
    global _UPDATE_DIALOG
    if is_store_distribution():
        return _store_update_dialog(parent)

    existing = _show_existing_update_dialog()
    if existing is not None:
        return existing

    dlg = QDialog(parent)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowTitle("检查更新")
    dlg.setWindowFlags(
        (
            dlg.windowFlags()
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
    )
    dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
    dlg.resize(650, 520)
    theme = _update_dialog_theme()
    dlg.setModal(False)
    dlg.setWindowModality(Qt.WindowModality.NonModal)
    _UPDATE_DIALOG = dlg
    dlg.destroyed.connect(_clear_global)

    lay = QVBoxLayout(dlg)
    title = QLabel("版本更新")
    title_font = QFont(title.font())
    title_font.setPointSize(max(title_font.pointSize(), 14))
    title_font.setBold(True)
    title.setFont(title_font)
    lay.addWidget(title)
    lbl_current = QLabel(f"当前版本: {__version__}")
    lay.addWidget(lbl_current)
    lbl_status = QLabel("正在联网获取最新版本信息，请保持与GitHub的连接畅通...")
    lay.addWidget(lbl_status)
    bar = QProgressBar()
    bar.setRange(0, 0)
    lay.addWidget(bar)

    txt = RemoteImageBrowser()
    txt.setOpenExternalLinks(True)
    txt.setPlaceholderText("变更日志 / 诊断输出...")
    lay.addWidget(txt, 1)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_download = PushButton(FluentIcon.DOWNLOAD, "下载并安装")
    btn_open = PushButton(FluentIcon.LINK, "打开链接")
    btn_copy = PushButton(FluentIcon.COPY, "复制链接")
    btn_retry = PushButton(FluentIcon.SYNC, "重新检查")
    btn_close = PushButton(FluentIcon.CLOSE, "关闭")
    for b in (btn_download, btn_open, btn_copy, btn_retry, btn_close):
        b.setFixedHeight(32)
        btn_row.addWidget(b)
    btn_download.setEnabled(False)
    btn_open.setEnabled(False)
    btn_copy.setEnabled(False)
    btn_retry.setEnabled(False)
    lay.addLayout(btn_row)

    state = {
        "done": False,
        "info": None,
        "aborted": False,
        "downloading": False,
        "pause_requested": False,
        "closing": False,
        "fallback_url": _RELEASES_PAGE,
    }
    watchdog = QTimer(dlg)
    watchdog.setSingleShot(True)

    class _ResultEmitter(QObject):
        done = pyqtSignal(object, object, object)
        download_progress = pyqtSignal(int, int, object)
        download_done = pyqtSignal(object, object)
    emitter = _ResultEmitter(dlg)  # Bind to the parent object so it disconnects automatically on destruction.

    def _question_close_only(
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
    ) -> QMessageBox.StandardButton:
        msg = QMessageBox(dlg)
        _apply_app_window_icon(msg)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(buttons)
        msg.setDefaultButton(default)
        msg.setWindowFlags(
            (
                msg.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowSystemMenuHint
                | Qt.WindowType.WindowCloseButtonHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
        )
        msg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        msg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        msg.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)
        return QMessageBox.StandardButton(msg.exec())

    def safe_ui(fn):
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        try:
            fn()
        except RuntimeError:
            pass

    def safe_emit(signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:
            pass

    def safe_emit_signal(obj, signal_name: str, *args):
        try:
            signal = getattr(obj, signal_name)
        except RuntimeError:
            return
        safe_emit(signal, *args)

    def watchdog_timeout():
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        state["done"] = True
        bar.setRange(0, 1)
        lbl_status.setText("获取超时（可能网络握手慢），可重新检查。")
        txt.start_new_html(
            f"<pre>超出设定: connect={CONNECT_TIMEOUT}s read={READ_TIMEOUT}s\n可点 重新检查 再发起。</pre>"
        )
        btn_open.setEnabled(True)
        btn_copy.setEnabled(True)
        btn_retry.setEnabled(True)

    watchdog.timeout.connect(watchdog_timeout)

    def render_changelog(changelog: str):
        if not changelog:
            txt.start_new_html("<p>(无变更日志)</p>")
            return
        md = _prepare_release_markdown(changelog)
        css = f"""
body{{font-family:'Microsoft YaHei UI','Segoe UI',sans-serif;font-size:12px;line-height:1.55;color:{theme['text']};}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;}}
code,pre{{font-family:Consolas,'Microsoft YaHei',monospace;}}
img{{max-width:100%;}}
table{{border-collapse:collapse;}}
table,th,td{{border:1px solid {theme['border']};padding:4px;}}
a{{color:{theme['accent']};}}
"""
        txt.start_new_markdown(md, css)

    def on_result(info, err, diag):
        if DEBUG_LOG and diag:
            print(f"[Updater] release diagnostics: {diag}")
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        state["done"] = True
        watchdog.stop()
        bar.setRange(0, 1)
        dlg.unsetCursor()
        if err:
            message = _brief_error_message(err)
            lbl_status.setText(f"暂时无法确认更新：{message}")
            lines = [
                "<p>暂时无法获取更新信息。可稍后重试，或直接打开 GitHub Releases 页面查看。</p>",
                "<ul>",
            ]
            shown_diag = False
            for u, e in diag:
                if u == "RATE_LIMIT":
                    continue
                if u == "EMPTY_RELEASES":
                    lines.append("<li>GitHub API 本次返回了空发布列表，但这不代表项目没有发布版本。</li>")
                    shown_diag = True
                    continue
                if u == "CACHE":
                    lines.append("<li>已改用本地缓存的发布信息。</li>")
                    shown_diag = True
                    continue
                lines.append(f"<li>{html.escape(str(u))}: {html.escape(_brief_error_message(e))}</li>")
                shown_diag = True
            if not shown_diag:
                lines.append(f"<li>来源: {html.escape(_API_RELEASES)}</li>")
            if not any(k in ("RATE_LIMIT",) or "限频" in str(e) for k, e in diag):
                lines.append("<li>建议：检查网络、代理或 DNS；也可以直接打开发布页。</li>")
            lines.append("</ul>")
            txt.start_new_html("".join(lines))
            btn_open.setEnabled(True)
            btn_copy.setEnabled(True)
            btn_retry.setEnabled(True)
            return

        state["info"] = info
        cmp = _compare_versions(info.latest, __version__)
        if cmp > 0:
            lbl_status.setText(f"发现新版本: {info.latest} (当前 {__version__})")
        elif cmp == 0:
            lbl_status.setText(f"已经是最新版本: {info.latest}")
        else:
            lbl_status.setText(f"当前版本高于线上稳定版本: {info.latest} (当前 {__version__})")
        render_changelog(info.changelog)

        # Rate-limit hint.
        rate_msg = next(
            (m for k, m in diag if k == "RATE_LIMIT" or "GitHub 限频" in m),
            None
        )
        if rate_msg:
            lbl_status.setText(lbl_status.text() + "（GitHub 限频）")
            warn_html = (
                f"<div style='color:{theme['warn_text']};font-size:12px;"
                f"border:1px solid {theme['warn_border']};background:{theme['warn_bg']};"
                "padding:6px;border-radius:4px;margin-bottom:8px;'>"
                f"⚠ {rate_msg}；建议稍后重试或设置 GITHUB_TOKEN。</div>"
            )
            current = txt.toHtml()
            txt.start_new_html(warn_html + current)

        _refresh_download_button()
        btn_open.setEnabled(True)
        btn_copy.setEnabled(True)
        btn_retry.setEnabled(True)

    emitter.done.connect(lambda i, e, d: safe_ui(lambda: on_result(i, e, d)))

    def _download_target(info: ReleaseInfo) -> tuple[str, str]:
        url, name = _normalize_download_asset(info.asset_url, info.asset_name)
        if not url or not name:
            return "", ""
        return url, str(_update_dir() / name)

    def _download_paths(info: ReleaseInfo) -> tuple[str, str, str]:
        url, dest = _download_target(info)
        return url, dest, dest + ".part"

    def _remove_path(path: str) -> None:
        try:
            p = Path(path)
            if p.exists() and p.is_file():
                p.unlink()
        except Exception:
            pass

    def _prune_update_dir(info: ReleaseInfo) -> None:
        _, dest, tmp_path = _download_paths(info)
        keep = {
            str(Path(dest)),
            str(Path(tmp_path)),
            str(_installer_meta_path()),
        }
        for child in _update_dir().iterdir():
            child_str = str(child)
            if child_str in keep:
                continue
            try:
                if child.is_file():
                    child.unlink()
            except Exception:
                pass

    def _local_installer_valid(info: ReleaseInfo) -> bool:
        _, dest, _ = _download_paths(info)
        dest_path = Path(dest)
        if not dest_path.is_file():
            return False
        meta = _load_installer_meta()
        if not meta:
            return False
        if str(meta.get("path", "")) != str(dest_path):
            return False
        if any(str(meta.get(k, "")) != str(v) for k, v in _asset_fingerprint(info).items() if k != "asset_size"):
            return False
        if int(meta.get("asset_size", 0) or 0) != int(info.asset_size or 0):
            return False
        if info.asset_size and dest_path.stat().st_size != int(info.asset_size):
            return False
        saved_sha256 = str(meta.get("sha256", "") or "").strip().lower()
        if not saved_sha256:
            return False
        return _compute_sha256(str(dest_path)).lower() == saved_sha256

    def _ensure_latest_installer_only(info: ReleaseInfo) -> bool:
        _prune_update_dir(info)
        _, dest, tmp_path = _download_paths(info)
        if os.path.exists(tmp_path) and not os.path.exists(dest):
            return False
        if _local_installer_valid(info):
            return True
        _remove_path(dest)
        _remove_path(tmp_path)
        _clear_installer_meta()
        return False

    def _refresh_download_button() -> None:
        info = state.get("info")
        if not info:
            btn_download.setEnabled(False)
            return
        url, dest, tmp_path = _download_paths(info)
        has_valid_local = _ensure_latest_installer_only(info) if url else False
        btn_download.setEnabled(bool(url))
        if not url:
            btn_download.setText("无安装包")
        elif os.path.exists(tmp_path) and not os.path.exists(dest):
            btn_download.setText("继续下载")
        elif has_valid_local:
            btn_download.setText("安装已下载")
        elif _compare_versions(info.latest, __version__) > 0:
            btn_download.setText("下载并安装")
        else:
            btn_download.setText("重新下载")

    def _compute_sha256(path: str) -> str:
        return _compute_file_sha256(path)

    def _read_signature_status(path: str) -> str:
        ext = Path(path).suffix.lower()
        if os.name != "nt" or ext not in (".exe", ".msi"):
            return "未校验（非 Windows 安装器）"
        try:
            escaped_path = path.replace("'", "''")
            cmd = (
                "Get-AuthenticodeSignature -FilePath "
                f"'{escaped_path}' | "
                "Select-Object Status,SignerCertificate | ConvertTo-Json -Compress"
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=20,
                encoding="utf-8",
                errors="replace",
                **_hidden_subprocess_kwargs(),
            )
            raw = (proc.stdout or "").strip()
            if not raw:
                return "未校验（无签名信息）"
            obj = json.loads(raw)
            status = str(obj.get("Status", "") or "Unknown")
            cert = obj.get("SignerCertificate") or {}
            subject = str(cert.get("Subject", "") or "").strip()
            if subject:
                return f"{status} / {subject}"
            return status
        except Exception as e:
            return f"未校验（{e}）"

    def _confirm_install(path: str, sha256_hex: str, signature_status: str) -> bool:
        name = Path(path).name or path
        msg = (
            f"已下载更新包：{name}\n\n"
            f"SHA256:\n{sha256_hex}\n\n"
            f"签名状态：{signature_status}\n\n"
            "是否立即启动安装程序？"
        )
        ret = _question_close_only(
            "确认安装更新",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return ret == QMessageBox.StandardButton.Yes

    def _maybe_launch_installer(path: str):
        if not path or not Path(path).is_file():
            InfoBar.error(
                title="安装包不存在",
                content=f"未找到下载完成的安装包：{path}",
                parent=dlg,
                duration=4000,
                position=InfoBarPosition.TOP,
            )
            return
        ext = Path(path).suffix.lower()
        sha256_hex = _compute_sha256(path)
        info = state.get("info")
        expected_sha256 = _normalize_sha256(info.asset_sha256) if isinstance(info, ReleaseInfo) else ""
        if expected_sha256 and sha256_hex.lower() != expected_sha256:
            _clear_installer_meta()
            _remove_path(path)
            lbl_status.setText("下载校验失败：安装包 SHA256 与线上发布信息不一致")
            InfoBar.error(
                title="下载校验失败",
                content="安装包 SHA256 与线上发布信息不一致，请重新下载。",
                parent=dlg,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
            return
        signature_status = _read_signature_status(path)
        if isinstance(info, ReleaseInfo):
            _save_installer_meta(info, path, sha256_hex)
        if os.name != "nt" or not getattr(sys, "frozen", False) or ext not in (".exe", ".msi"):
            lbl_status.setText(f"下载完成: {path}")
            InfoBar.success(
                title="更新已下载",
                content=f"已下载到 {path}，SHA256 已生成",
                parent=dlg,
                duration=3500,
                position=InfoBarPosition.TOP,
            )
            return
        if not _confirm_install(path, sha256_hex, signature_status):
            lbl_status.setText("安装已取消，更新包保留在本地")
            InfoBar.info(
                title="已取消安装",
                content=f"更新包已保留：{path}",
                parent=dlg,
                duration=3500,
                position=InfoBarPosition.TOP,
            )
            return
        try:
            lbl_status.setText("下载完成，正在退出程序并启动安装器...")
            _prepare_app_for_update_exit()
            _schedule_windows_installer(path)
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, app.quit)
                QTimer.singleShot(2000, lambda: os._exit(0))
        except Exception as e:
            try:
                _prepare_app_for_update_exit()
                subprocess.Popen([path], close_fds=True, **_hidden_subprocess_kwargs())
                app = QApplication.instance()
                if app is not None:
                    QTimer.singleShot(0, app.quit)
                    QTimer.singleShot(2000, lambda: os._exit(0))
            except Exception:
                InfoBar.error(
                    title="启动安装器失败",
                    content=_brief_error_message(e),
                    parent=dlg,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                )

    def _on_download_progress(cur: int, total: int, path: object):
        if state["aborted"] or (not dlg.isVisible()):
            return
        bar.setRange(0, max(total, 1))
        bar.setValue(max(0, min(cur, max(total, 1))))
        name = Path(str(path or "")).name or "更新包"
        if total > 0:
            pct = int((cur * 100) / total) if total > 0 else 0
            lbl_status.setText(f"正在下载 {name} ({pct}% , {cur}/{total} 字节)")
        else:
            lbl_status.setText(f"正在下载 {name}...")

    def _on_download_done(path: object, err: object):
        state["downloading"] = False
        if state["aborted"] or (not dlg.isVisible()):
            return
        if err == "__paused__":
            _refresh_download_button()
            btn_open.setEnabled(bool(state.get("info")))
            btn_copy.setEnabled(bool(state.get("info")))
            btn_retry.setEnabled(True)
            dlg.unsetCursor()
            bar.setRange(0, 1)
            lbl_status.setText("下载已暂停，可稍后继续下载。")
            InfoBar.info(
                title="下载已暂停",
                content="更新包已保留，下次打开可继续下载。",
                parent=dlg,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
            return
        if err:
            message = _brief_error_message(err, context="download")
            _refresh_download_button()
            btn_open.setEnabled(bool(state.get("info")))
            btn_copy.setEnabled(bool(state.get("info")))
            btn_retry.setEnabled(True)
            dlg.unsetCursor()
            bar.setRange(0, 1)
            lbl_status.setText(f"下载失败：{message}")
            InfoBar.error(
                title="下载失败",
                content=message,
                parent=dlg,
                duration=4000,
                position=InfoBarPosition.TOP,
            )
            return
        bar.setRange(0, 1)
        bar.setValue(1)
        _maybe_launch_installer(str(path or ""))
        _refresh_download_button()
        btn_open.setEnabled(bool(state.get("info")))
        btn_copy.setEnabled(bool(state.get("info")))
        btn_retry.setEnabled(True)
        dlg.unsetCursor()

    emitter.download_progress.connect(lambda cur, total, path: _on_download_progress(cur, total, path))
    emitter.download_done.connect(lambda path, err: _on_download_done(path, err))

    def worker():
        info, err, diag = _fetch_release()
        # Emit after the thread finishes; if the dialog was destroyed, the emitter was destroyed too, so skip.
        safe_emit_signal(emitter, "done", info, err, diag)

    def start_fetch():
        state["done"] = False
        state["aborted"] = False
        state["closing"] = False
        state["info"] = None
        lbl_status.setText("正在联网获取最新版本信息，请保持与GitHub的连接畅通...")
        txt.start_new_html("<p style='color:#777;'>正在获取...</p>")
        bar.setRange(0, 0)
        btn_open.setEnabled(False)
        btn_copy.setEnabled(False)
        btn_retry.setEnabled(False)
        dlg.setCursor(Qt.CursorShape.BusyCursor)
        total_wait_ms = max((CONNECT_TIMEOUT + READ_TIMEOUT) * 1000 + 1000, 10000)
        watchdog.start(total_wait_ms)
        threading.Thread(target=worker, daemon=True).start()

    def _current_update_link() -> str:
        if state["info"]:
            return state["info"].asset_url or state["info"].url or state.get("fallback_url", "")
        return str(state.get("fallback_url", "") or "")

    def do_open():
        link = _current_update_link()
        if link:
            import webbrowser
            webbrowser.open(link)

    def do_copy():
        link = _current_update_link()
        if link:
            try:
                QApplication.clipboard().setText(link)
                InfoBar.success(
                    title="已复制",
                    content="下载链接已复制到剪贴板。",
                    parent=dlg,
                    duration=2200,
                    position=InfoBarPosition.TOP,
                )
            except Exception as e:
                InfoBar.error(
                    title="复制失败",
                    content=_brief_error_message(e),
                    parent=dlg,
                    duration=3000,
                    position=InfoBarPosition.TOP,
                )

    def do_download():
        info = state.get("info")
        if not info:
            return
        url, dest, tmp_path = _download_paths(info)
        if not url:
            InfoBar.warning(
                title="无可下载资产",
                content="当前版本仅提供网页链接，请手动下载。",
                parent=dlg,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        valid_local = _ensure_latest_installer_only(info)
        if valid_local and os.path.exists(dest):
            _maybe_launch_installer(dest)
            return
        if os.path.exists(dest):
            ret = _question_close_only(
                "安装包已存在",
                "检测到已存在安装包，是否继续重新下载并覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        _prune_update_dir(info)
        btn_download.setEnabled(False)
        btn_open.setEnabled(False)
        btn_copy.setEnabled(False)
        btn_retry.setEnabled(False)
        dlg.setCursor(Qt.CursorShape.BusyCursor)
        bar.setRange(0, 100)
        bar.setValue(0)
        lbl_status.setText("正在下载更新包...")
        state["downloading"] = True
        state["pause_requested"] = False

        class _PauseDownload(Exception):
            pass

        def worker_download():
            try:
                existing = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
                headers: Dict[str, str] = {}
                file_mode = "ab" if existing > 0 else "wb"
                if existing > 0:
                    headers["Range"] = f"bytes={existing}-"
                with _session.get(url, stream=True, timeout=(CONNECT_TIMEOUT, 60), headers=headers) as r:
                    r.raise_for_status()
                    if existing > 0 and r.status_code == 200:
                        existing = 0
                        file_mode = "wb"
                    reported = int(r.headers.get("Content-Length", "0") or "0")
                    total = existing + reported if existing > 0 and r.status_code == 206 else reported
                    cur = existing
                    with open(tmp_path, file_mode) as f:
                        for chunk in r.iter_content(chunk_size=1024 * 128):
                            if state["pause_requested"]:
                                raise _PauseDownload()
                            if not chunk:
                                continue
                            f.write(chunk)
                            cur += len(chunk)
                            safe_emit_signal(emitter, "download_progress", cur, total, dest)
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                os.replace(tmp_path, dest)
                safe_emit_signal(emitter, "download_done", dest, None)
            except _PauseDownload:
                safe_emit_signal(emitter, "download_done", dest, "__paused__")
            except Exception as e:
                safe_emit_signal(emitter, "download_done", dest, _brief_error_message(e, context="download"))

        threading.Thread(target=worker_download, daemon=True).start()

    def abort_and_close():
        if state["closing"]:
            return
        if state["downloading"]:
            ret = _question_close_only(
                "确认关闭",
                "关闭该窗口会暂停下载，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        state["closing"] = True
        state["pause_requested"] = state["downloading"]
        state["aborted"] = True
        _clear_global()
        dlg.close()

    # Custom ESC handling: abort instead of crashing.
    orig_key = dlg.keyPressEvent
    def _keyPress(ev):
        if ev.key() == Qt.Key.Key_Escape:
            abort_and_close()
            ev.accept()
            return
        orig_key(ev)
    dlg.keyPressEvent = _keyPress

    orig_close_event = dlg.closeEvent
    def _close_event(ev):
        if not state["closing"]:
            abort_and_close()
            ev.ignore()
            return
        orig_close_event(ev)
    dlg.closeEvent = _close_event

    btn_download.clicked.connect(do_download)
    btn_open.clicked.connect(do_open)
    btn_copy.clicked.connect(do_copy)
    btn_retry.clicked.connect(start_fetch)
    btn_close.clicked.connect(abort_and_close)

    start_fetch()
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg

def _clear_global():
    global _UPDATE_DIALOG
    _UPDATE_DIALOG = None

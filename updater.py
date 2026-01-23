
import os, json, time, threading, re, base64, requests
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QUrl
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextBrowser,
    QHBoxLayout, QProgressBar, QMessageBox, QApplication
)
from PyQt6.QtGui import QTextDocument
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from qfluentwidgets import PushButton, FluentIcon

try:
    import markdown2
except ImportError:
    markdown2 = None

# ---------------- 常量 ----------------
_ETAG_PATH = os.path.join(os.path.dirname(__file__), ".release_etag_cache.json")
_API_RELEASES = "https://api.github.com/repos/SakuraMathcraft/LaTeXSnipper/releases"
_UPDATE_DIALOG: Optional[QDialog] = None
__version__ = "v1.0"

PRIMARY_URL = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/version.json"
MIRROR_URLS = [
    "https://cdn.jsdelivr.net/gh/SakuraMathcraft/LaTeXSnipper/version.json",
    "https://raw.fastgit.org/SakuraMathcraft/LaTeXSnipper/main/version.json"
]

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 8
DEBUG_LOG = True

DIALOG_QSS = """
QDialog{background:#f5f7fa;}
QLabel{color:#2e3135;font-size:13px;}
QTextBrowser{
  background:#ffffff;
  border:1px solid #cfd6dd;
  border-radius:6px;
  font-family:Consolas,'Microsoft YaHei',monospace;
  font-size:12px;
  padding:6px;
}
QProgressBar{
  border:1px solid #cfd6dd;
  border-radius:6px;
  background:#ffffff;
  text-align:center;
  height:12px;
}
QProgressBar::chunk{
  background:#1976d2;
  border-radius:6px;
}
"""

_session = requests.Session()
_session.headers.update({
    "User-Agent": "LaTeXSnipper-Updater/1.0 (+https://github.com/SakuraMathcraft/LaTeXSnipper)"
})

# ---------------- 数据结构 ----------------
@dataclass
class ReleaseInfo:
    latest: str
    url: str
    changelog: str = ""

# ---------------- 辅助函数 ----------------
def _load_cached_info():
    try:
        with open(_ETAG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
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
                "etag": etag,
                "ts": int(time.time()),
                "info": {
                    "latest": info.latest,
                    "url": info.url,
                    "changelog": info.changelog
                }
            }, f)
    except Exception:
        pass

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

def _fetch_version_json_fallback() -> Tuple[Optional[ReleaseInfo], Optional[str], List[Tuple[str, str]]]:
    diags: List[Tuple[str, str]] = []
    for u in [PRIMARY_URL] + MIRROR_URLS:
        try:
            r = _session.get(u, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            r.raise_for_status()
            js = r.json()
            return ReleaseInfo(
                js.get("latest", ""),
                js.get("url", "https://github.com/SakuraMathcraft/LaTeXSnipper/releases"),
                js.get("changelog", "")
            ), None, diags
        except Exception as e:
            diags.append((u, repr(e)))
    return None, "回退 version.json 亦失败", diags

# ---------------- 主获取（含限频检测增强） ----------------
# ---------------- 主获取（含限频检测增强） ----------------
def _fetch_release() -> Tuple[Optional[ReleaseInfo], Optional[str], List[Tuple[str, str]]]:
    diagnostics: List[Tuple[str, str]] = []
    headers: Dict[str, str] = {}
    _attach_auth_headers(headers)
    etag, _, cached_info = _load_cached_info()
    if etag:
        headers["If-None-Match"] = etag
    try:
        resp = _session.get(_API_RELEASES, headers=headers, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

        # 速率即将重置提醒（Remaining=0 即视为限额耗尽）
        remain_header = resp.headers.get("X-RateLimit-Remaining")
        if resp.status_code == 200 and remain_header == "0":
            reset = resp.headers.get("X-RateLimit-Reset")
            msg = f"GitHub 限频: 剩余=0 重置≈{_fmt_reset(reset)}"
            diagnostics.append(("RATE_LIMIT", msg))  # 哨兵

        if resp.status_code == 304:
            if cached_info:
                return cached_info, None, diagnostics
            else:
                # 无缓存，回退获取
                info, err, fb = _fetch_version_json_fallback()
                diagnostics.extend(fb)
                return info, err, diagnostics

        if resp.status_code == 403:
            remain = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            msg = f"GitHub 限频: 剩余={remain} 重置≈{_fmt_reset(reset)}"
            diagnostics.append((_API_RELEASES, msg))
            diagnostics.append(("RATE_LIMIT", msg))  # 哨兵
            info, err, fb = _fetch_version_json_fallback()
            diagnostics.extend(fb)
            if info:
                return info, None, diagnostics
            return None, msg + " 且回退失败", diagnostics

        resp.raise_for_status()

        new_etag = resp.headers.get("ETag")
        releases = resp.json()

        def pick(key: str):
            for rel in releases:
                tag = (rel.get("tag_name") or "").lower()
                if key in tag:
                    return rel
            return None

        # 正式版本优先选择稳定版本，不再优先选择 beta/nightly
        rel = pick("v1.") or pick("beta") or pick("nightly") or (releases[0] if releases else None)
        if not rel:
            diagnostics.append((_API_RELEASES, "no releases"))
            return None, "未找到 release", diagnostics

        info = ReleaseInfo(
            rel.get("tag_name", ""),
            rel.get("html_url", ""),
            rel.get("body", "")
        )
        if new_etag:
            _save_cached_info(new_etag, info)
        return info, None, diagnostics

    except Exception as e:
        diagnostics.append((_API_RELEASES, repr(e)))
        info, err, fb = _fetch_version_json_fallback()
        diagnostics.extend(fb)
        if info:
            return info, None, diagnostics
        return None, str(e), diagnostics

# ---------------- 图文浏览器 ----------------
_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/"
_REL_IMG_PATTERN = re.compile(r'!\[([^\]]*)\]\((?!https?://|data:)([^)]+)\)')

def _fix_relative_images(md: str) -> str:
    return _REL_IMG_PATTERN.sub(
        lambda m: f"![{m.group(1)}]({_GITHUB_RAW_PREFIX}{m.group(2).lstrip('./')})",
        md
    )

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
            # 透明 1x1 占位
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

# ---------------- 主对话框 ----------------
def check_update_dialog(parent=None):
    global _UPDATE_DIALOG
    if _UPDATE_DIALOG is not None:
        _UPDATE_DIALOG.raise_()
        _UPDATE_DIALOG.activateWindow()
        return

    dlg = QDialog(parent)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowTitle("检查更新")
    dlg.resize(650, 520)
    dlg.setStyleSheet(DIALOG_QSS)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    _UPDATE_DIALOG = dlg
    dlg.destroyed.connect(_clear_global)

    lay = QVBoxLayout(dlg)
    title = QLabel("版本更新"); title.setStyleSheet("font-size:18px;font-weight:600;margin-bottom:4px;")
    lay.addWidget(title)
    lbl_current = QLabel(f"当前版本: {__version__}"); lay.addWidget(lbl_current)
    lbl_status = QLabel("正在联网获取最新版本信息，请保持与GitHub的连接畅通...")
    lbl_status.setStyleSheet("color:#555;margin-bottom:4px;")
    lay.addWidget(lbl_status)
    bar = QProgressBar(); bar.setRange(0, 0); lay.addWidget(bar)

    txt = RemoteImageBrowser()
    txt.setOpenExternalLinks(True)
    txt.setPlaceholderText("变更日志 / 诊断输出...")
    lay.addWidget(txt, 1)

    btn_row = QHBoxLayout(); btn_row.addStretch()
    btn_open = PushButton(FluentIcon.LINK, "打开链接")
    btn_copy = PushButton(FluentIcon.COPY, "复制链接")
    btn_retry = PushButton(FluentIcon.SYNC, "重新检查")
    btn_close = PushButton(FluentIcon.CLOSE, "关闭")
    for b in (btn_open, btn_copy, btn_retry, btn_close):
        b.setFixedHeight(32); btn_row.addWidget(b)
    btn_open.setEnabled(False); btn_copy.setEnabled(False); btn_retry.setEnabled(False)
    lay.addLayout(btn_row)

    state = {"done": False, "info": None, "aborted": False}
    watchdog = QTimer(dlg); watchdog.setSingleShot(True)

    class _ResultEmitter(QObject):
        done = pyqtSignal(object, object, object)
    emitter = _ResultEmitter(dlg)  # 绑定父对象，销毁后自动断开

    def safe_ui(fn):
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        try:
            fn()
        except RuntimeError:
            pass

    def watchdog_timeout():
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        state["done"] = True
        bar.setRange(0, 1)
        lbl_status.setText("获取超时（可能网络握手慢），可重新检查。")
        txt.start_new_html(
            f"<pre>超出设定: connect={CONNECT_TIMEOUT}s read={READ_TIMEOUT}s\n可点 重新检查 再发起。</pre>"
        )
        btn_retry.setEnabled(True)

    watchdog.timeout.connect(watchdog_timeout)

    def render_changelog(changelog: str):
        if not changelog:
            txt.start_new_html("<p>(无变更日志)</p>")
            return
        md = _fix_relative_images(changelog)
        if markdown2:
            html_body = markdown2.markdown(
                md, extras=["fenced-code-blocks", "tables", "strike", "task_list"]
            )
            style = """
<style>
body{font-family:Consolas,'Microsoft YaHei',monospace;font-size:12px;line-height:1.5;}
pre,code{background:#f6f8fa;}
pre{padding:8px;border-radius:4px;overflow:auto;}
code{padding:2px 4px;border-radius:3px;}
img{max-width:100%;border:1px solid #e0e0e0;border-radius:4px;}
table{border-collapse:collapse;}
table,th,td{border:1px solid #d0d7de;padding:4px;}
</style>
"""
            txt.start_new_html(style + html_body)
        else:
            esc = md.replace("&", "&amp;").replace("<", "&lt;")
            txt.start_new_html(f"<pre>{esc}</pre>")

    def on_result(info, err, diag):
        if DEBUG_LOG:
            print(f"DEBUG: diag = {diag}")
        if state["aborted"] or state["done"] or (not dlg.isVisible()):
            return
        state["done"] = True
        watchdog.stop()
        bar.setRange(0, 1)
        dlg.unsetCursor()
        if err:
            lbl_status.setText(f"获取失败: {err}")
            lines = ["尝试结果:"]
            for u, e in diag:
                lines.append(f"- {u}\n  -> {e}")
            if not any(k in ("RATE_LIMIT",) or "限频" in e for k, e in diag):
                lines.append("请求过于频繁，建议: 检查网络 / 代理 / DNS, 稍后再试。")
            esc = "\n".join(lines).replace("&", "&amp;").replace("<", "&lt;")
            txt.start_new_html(f"<pre>{esc}</pre>")
            btn_retry.setEnabled(True)
            return

        state["info"] = info
        if info.latest != __version__:
            lbl_status.setText(f"发现新版本: {info.latest} (当前 {__version__})")
        else:
            lbl_status.setText(f"已经是最新版本: {info.latest}")
        render_changelog(info.changelog)

        # 限频提示（包含备用源触发）
        rate_msg = next(
            (m for k, m in diag if k == "RATE_LIMIT" or "GitHub 限频" in m),
            None
        )
        if rate_msg:
            lbl_status.setText(lbl_status.text() + "（限频/备用源）")
            warn_html = (
                "<div style='color:#d35400;font-size:12px;"
                "border:1px solid #f5c182;background:#fff4e0;"
                "padding:6px;border-radius:4px;margin-bottom:8px;'>"
                f"⚠ {rate_msg}；建议稍后重试或设置 GITHUB_TOKEN。</div>"
            )
            current = txt.toHtml()
            txt.start_new_html(warn_html + current)

        btn_open.setEnabled(True)
        btn_copy.setEnabled(True)
        btn_retry.setEnabled(True)

    emitter.done.connect(lambda i, e, d: safe_ui(lambda: on_result(i, e, d)))

    def worker():
        info, err, diag = _fetch_release()
        # 线程结束后发信号；若对话框已销毁，emitter 也随父销毁，不会调用槽
        try:
            emitter.done.emit(info, err, diag)
        except RuntimeError:
            pass

    def start_fetch():
        state["done"] = False
        state["aborted"] = False
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

    def do_open():
        if state["info"]:
            import webbrowser
            webbrowser.open(state["info"].url)

    def do_copy():
        if state["info"]:
            QApplication.clipboard().setText(state["info"].url)
            QMessageBox.information(dlg, "复制", "下载链接已复制。")

    def abort_and_close():
        # 标记放弃，阻止后续 UI 更新
        state["aborted"] = True
        dlg.close()

    # 自定义 ESC：中止而非崩
    orig_key = dlg.keyPressEvent
    def _keyPress(ev):
        if ev.key() == Qt.Key.Key_Escape:
            abort_and_close()
            ev.accept()
            return
        orig_key(ev)
    dlg.keyPressEvent = _keyPress

    btn_open.clicked.connect(do_open)
    btn_copy.clicked.connect(do_copy)
    btn_retry.clicked.connect(start_fetch)
    btn_close.clicked.connect(abort_and_close)

    start_fetch()
    dlg.exec()

def _clear_global():
    global _UPDATE_DIALOG
    _UPDATE_DIALOG = None

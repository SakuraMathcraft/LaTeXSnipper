# src/updater.py
import threading
import requests
from dataclasses import dataclass
from typing import Optional, List, Tuple
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit,
    QHBoxLayout, QProgressBar, QMessageBox
)

__version__ = "1.0"

PRIMARY_URL = "https://raw.githubusercontent.com/SakuraMathcraft/LaTeXSnipper/main/version.json"
MIRROR_URLS = [
    "https://cdn.jsdelivr.net/gh/SakuraMathcraft/LaTeXSnipper/version.json",
    "https://raw.fastgit.org/SakuraMathcraft/LaTeXSnipper/main/version.json"
]

CONNECT_TIMEOUT = 6
READ_TIMEOUT = 8
DEBUG_LOG = True

@dataclass
class ReleaseInfo:
    latest: str
    url: str
    changelog: str = ""

PRIMARY_STYLE = (
    "QPushButton{background:#1976d2;color:#fff;border:none;border-radius:6px;padding:8px 16px;font-size:13px;}"
    "QPushButton:hover{background:#1e88e5;}"
    "QPushButton:disabled{background:#90caf9;color:#e3f2fd;}"
)
DIALOG_QSS = """
QDialog{background:#f5f7fa;}
QLabel{color:#2e3135;font-size:13px;}
QTextEdit{
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

class _ResultEmitter(QObject):
    done = pyqtSignal(object, object, object)  # info, err, diag

def _try_fetch(url: str) -> dict:
    resp = _session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    resp.raise_for_status()
    return resp.json()

def _fetch_release() -> tuple[Optional[ReleaseInfo], Optional[str], List[Tuple[str, str]]]:
    urls = [PRIMARY_URL] + MIRROR_URLS
    diagnostics: List[Tuple[str, str]] = []
    for u in urls:
        try:
            data = _try_fetch(u)
            info = ReleaseInfo(
                latest=str(data.get("version", "")).strip(),
                url=str(data.get("url", "")).strip() or "https://github.com/",
                changelog=(data.get("changelog") or "").strip()
            )
            if info.latest:
                if DEBUG_LOG: print(f"[updater] success {u} -> {info.latest}")
                return info, None, diagnostics
            diagnostics.append((u, "empty version field"))
        except Exception as e:
            diagnostics.append((u, repr(e)))
            if DEBUG_LOG: print(f"[updater] fail {u}: {e}")
    return None, (diagnostics[-1][1] if diagnostics else "unknown error"), diagnostics

_UPDATE_DIALOG: Optional[QDialog] = None  # 全局单实例

def check_update_dialog(parent=None):
    global _UPDATE_DIALOG
    if _UPDATE_DIALOG is not None:
        # 已存在则激活
        _UPDATE_DIALOG.raise_()
        _UPDATE_DIALOG.activateWindow()
        return

    dlg = QDialog(parent)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.destroyed.connect(lambda: _clear_global())
    _UPDATE_DIALOG = dlg

    dlg.setWindowTitle("检查更新")
    dlg.resize(600, 470)
    dlg.setStyleSheet(DIALOG_QSS)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)

    lay = QVBoxLayout(dlg)
    title = QLabel("版本更新(如遇错误请重试或者重启程序)")
    title.setStyleSheet("font-size:18px;font-weight:600;margin-bottom:4px;")
    lay.addWidget(title)

    lbl_current = QLabel(f"当前版本: {__version__}")
    lay.addWidget(lbl_current)

    lbl_status = QLabel("正在联网获取最新版本信息，请保持与GitHub的连接畅通...")
    lbl_status.setStyleSheet("color:#555;margin-bottom:4px;")
    lay.addWidget(lbl_status)

    bar = QProgressBar()
    bar.setRange(0, 0)
    lay.addWidget(bar)

    txt = QTextEdit()
    txt.setReadOnly(True)
    txt.setPlaceholderText("变更日志 / 诊断输出...")
    lay.addWidget(txt, 1)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_open = QPushButton("打开链接")
    btn_copy = QPushButton("复制链接")
    btn_retry = QPushButton("重新检查")
    btn_close = QPushButton("关闭")
    for b in (btn_open, btn_copy, btn_retry, btn_close):
        b.setStyleSheet(PRIMARY_STYLE)
    btn_open.setEnabled(False)
    btn_copy.setEnabled(False)
    btn_retry.setEnabled(False)
    for b in (btn_open, btn_copy, btn_retry, btn_close):
        btn_row.addWidget(b)
    lay.addLayout(btn_row)

    state = {"done": False, "info": None}
    watchdog = QTimer(dlg); watchdog.setSingleShot(True)
    emitter = _ResultEmitter()

    def watchdog_timeout():
        if state["done"]:
            return
        bar.setRange(0, 1)
        lbl_status.setText("获取超时（可能网络握手慢），可重新检查。")
        txt.setPlainText(
            f"超出设定：connect={CONNECT_TIMEOUT}s read={READ_TIMEOUT}s\n"
            "仍可能稍后返回结果；你可点 重新检查 再发起。"
        )
        btn_retry.setEnabled(True)

    watchdog.timeout.connect(watchdog_timeout)

    def on_result(info, err, diag):
        if state["done"]:
            return
        state["done"] = True
        watchdog.stop()
        bar.setRange(0, 1)
        if err:
            lbl_status.setText(f"获取失败: {err}")
            lines = ["尝试结果:"]
            for u, e in diag:
                lines.append(f"- {u}\n  -> {e}")
            lines.append("建议：检查网络 / 代理 / DNS，稍后再试。")
            txt.setPlainText("\n".join(lines))
            btn_retry.setEnabled(True)
            return
        state["info"] = info
        if info.latest != __version__:
            lbl_status.setText(f"发现新版本: {info.latest}（当前 {__version__}）")
        else:
            lbl_status.setText(f"已经是最新版本: {info.latest}")
        txt.setPlainText(info.changelog or "(无变更日志)")
        btn_open.setEnabled(True)
        btn_copy.setEnabled(True)
        btn_retry.setEnabled(True)

    emitter.done.connect(on_result)

    def worker():
        info, err, diag = _fetch_release()
        emitter.done.emit(info, err, diag)

    def start_fetch():
        state["done"] = False
        state["info"] = None
        lbl_status.setText("正在联网获取最新版本信息，请保持与GitHub的连接畅通...")
        txt.clear()
        bar.setRange(0, 0)
        btn_open.setEnabled(False)
        btn_copy.setEnabled(False)
        btn_retry.setEnabled(False)
        # 给网络总时长一个下限，避免过快超时
        total_wait_ms = max((CONNECT_TIMEOUT + READ_TIMEOUT) * 1000 + 1000, 10000)
        watchdog.start(total_wait_ms)
        threading.Thread(target=worker, daemon=True).start()

    def do_open():
        import webbrowser
        if state["info"]:
            webbrowser.open(state["info"].url)

    def do_copy():
        if state["info"]:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(state["info"].url)
            QMessageBox.information(dlg, "复制", "下载链接已复制。")

    def do_close():
        dlg.close()

    btn_open.clicked.connect(do_open)
    btn_copy.clicked.connect(do_copy)
    btn_retry.clicked.connect(start_fetch)
    btn_close.clicked.connect(do_close)

    start_fetch()
    dlg.exec()

def _clear_global():
    global _UPDATE_DIALOG
    _UPDATE_DIALOG = None

import html
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QVBoxLayout
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PushButton

from runtime.distribution import is_store_distribution
from update.dialog_helpers import (
    _clear_global,
    _hidden_subprocess_kwargs,
    _set_update_dialog,
    _show_existing_update_dialog,
    _update_dialog_theme,
    question_close_only,
)
from update.github_release_client import _fetch_release, _session
from update.installer_cache import (
    _clear_installer_meta,
    _compute_file_sha256,
    _download_paths,
    _ensure_latest_installer_only,
    _prune_update_dir,
    _remove_path,
    _save_installer_meta,
)
from update.installer_launch import _prepare_app_for_update_exit, _read_signature_status, _schedule_windows_installer
from update.markdown_rendering import _prepare_release_markdown
from update.release_types import (
    CONNECT_TIMEOUT,
    DEBUG_LOG,
    READ_TIMEOUT,
    ReleaseInfo,
    __version__,
    _API_RELEASES,
    _RELEASES_PAGE,
    _brief_error_message,
    _compare_versions,
    _normalize_sha256,
)
from update.remote_image_browser import RemoteImageBrowser
from update.store_dialog import _store_update_dialog


def check_update_dialog(parent=None):
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
    _set_update_dialog(dlg)
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



    def _confirm_install(path: str, sha256_hex: str, signature_status: str) -> bool:
        name = Path(path).name or path
        msg = (
            f"已下载更新包：{name}\n\n"
            f"SHA256:\n{sha256_hex}\n\n"
            f"签名状态：{signature_status}\n\n"
            "是否立即启动安装程序？"
        )
        ret = question_close_only(dlg, 
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
        sha256_hex = _compute_file_sha256(path)
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
            ret = question_close_only(dlg, 
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
            ret = question_close_only(dlg, 
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

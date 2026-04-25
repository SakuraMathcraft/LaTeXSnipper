# --- Crash guard & runtime sanity, put this at the VERY TOP of 'src/main.py' ---
import atexit
import builtins
import ctypes
import datetime
import faulthandler
import importlib
import io
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from io import BytesIO
from logging.handlers import RotatingFileHandler
from pathlib import Path

STABLE_GUI_PIP_SPECS = [
    "PyQt6==6.10.0",
    "PyQt6-Qt6==6.10.0",
    "PyQt6-WebEngine==6.10.0",
    "PyQt6-WebEngine-Qt6==6.10.0",
    "PyQt6-Fluent-Widgets==1.11.2",
]

STABLE_GUI_VERSION_PINS = {
    "PyQt6": "6.10.0",
    "PyQt6-Qt6": "6.10.0",
    "PyQt6-WebEngine": "6.10.0",
    "PyQt6-WebEngine-Qt6": "6.10.0",
    "PyQt6-Fluent-Widgets": "1.11.2",
}


def _gui_dep_version_mismatches():
    try:
        import importlib.metadata as metadata
    except Exception:
        return []

    mismatches = []
    for dist_name, expected in STABLE_GUI_VERSION_PINS.items():
        try:
            actual = metadata.version(dist_name)
        except metadata.PackageNotFoundError:
            actual = None
        except Exception:
            actual = None
        if actual != expected:
            shown = actual if actual is not None else "未安装"
            mismatches.append(f"{dist_name}={shown}，期望 {expected}")
    return mismatches


def _install_stable_gui_deps(pyexe: str, reason: str):
    print(f"[WARN] GUI 依赖需要修复：{reason}")
    subprocess.check_call([pyexe, "-m", "pip", "install", "--force-reinstall", *STABLE_GUI_PIP_SPECS])
    importlib.invalidate_caches()


def _early_ensure_pyqt6_and_pywin32():
    import os, sys, subprocess, importlib
    pyexe = sys.executable
    exe_name = os.path.basename(pyexe).lower()
    # 仅在源码解释器模式启用早期 pip 自修复；打包 exe 不支持 `-m pip` 语义
    can_pip_repair = (not getattr(sys, "frozen", False)) and exe_name.startswith("python")
    if not can_pip_repair:
        print("[INFO] 打包模式或非 python 解释器启动，跳过早期 pip 自修复。")
        return

    mismatches = _gui_dep_version_mismatches()
    if mismatches:
        _install_stable_gui_deps(pyexe, "; ".join(mismatches))

    # 检查 PyQt6
    try:
        import PyQt6 as _PyQt6
        _ = _PyQt6
    except ImportError:
        print("[WARN] 未检测到 PyQt6，尝试自动安装...")
        _install_stable_gui_deps(pyexe, "PyQt6 未安装")
        importlib.invalidate_caches()
        import PyQt6 as _PyQt6
        _ = _PyQt6
        print("[OK] PyQt6 安装成功。")
    else:
        # PyQt6 已存在，但可能缺少 WebEngine
        try:
            from PyQt6 import QtWebEngineWidgets as _QtWebEngineWidgets
            _ = _QtWebEngineWidgets
        except Exception:
            print("[WARN] 未检测到 PyQt6-WebEngine，尝试自动安装...")
            _install_stable_gui_deps(pyexe, "PyQt6-WebEngine 未安装")
            importlib.invalidate_caches()

    # 检查 qfluentwidgets（PyQt6-Fluent-Widgets）
    try:
        import qfluentwidgets as _qfluentwidgets
        _ = _qfluentwidgets
    except ImportError:
        print("[WARN] 未检测到 PyQt6-Fluent-Widgets，尝试自动安装...")
        _install_stable_gui_deps(pyexe, "PyQt6-Fluent-Widgets 未安装")
        importlib.invalidate_caches()
        import qfluentwidgets as _qfluentwidgets
        _ = _qfluentwidgets
        print("[OK] PyQt6-Fluent-Widgets 安装成功。")

    # 检查 win32api
    try:
        import win32api as _win32api
        _ = _win32api
    except ImportError:
        print("[WARN] 未检测到 win32api，尝试自动安装 pywin32...")
        subprocess.check_call([pyexe, "-m", "pip", "install", "pywin32"])
        importlib.invalidate_caches()
        # 关键：安装后直接提示用户重启
        print("[OK] pywin32 安装成功。请关闭并重新启动本程序以完成初始化。")
        import time
        time.sleep(2)
        sys.exit(0)

    # 检查 pyperclip
    try:
        import pyperclip as _pyperclip
        _ = _pyperclip
    except ImportError:
        print("[WARN] 未检测到 pyperclip，尝试自动安装...")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "pyperclip"])
            importlib.invalidate_caches()
            import pyperclip as _pyperclip
            _ = _pyperclip
            print("[OK] pyperclip 安装成功。")
        except Exception as e:
            print(f"[WARN] pyperclip 自动安装失败: {e}")
            # Fallback stub to avoid crash; clipboard copy will be no-op with warning.
            import types
            def _copy_stub(_text):
                print("[WARN] pyperclip 不可用，无法复制到剪贴板。")
            sys.modules.setdefault("pyperclip", types.SimpleNamespace(copy=_copy_stub))

    # 检查 requests（用于更新检查）
    try:
        import requests as _requests
        _ = _requests
    except ImportError:
        print("[WARN] 未检测到 requests，尝试自动安装...")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "requests"])
            importlib.invalidate_caches()
            import requests as _requests
            _ = _requests
            print("[OK] requests 安装成功。")
        except Exception as e:
            print(f"[WARN] requests 自动安装失败: {e}")
            import types
            def _requests_stub(*_args, **_kwargs):
                raise RuntimeError("requests 不可用，更新检查已禁用。")
            sys.modules.setdefault("requests", types.SimpleNamespace(get=_requests_stub, post=_requests_stub))

_early_ensure_pyqt6_and_pywin32()

def resource_path(relative_path):
    """获取打包后资源的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 全局配置文件名（仅定义一次）
CONFIG_FILENAME = "LaTeXSnipper_config.json"
APP_STATE_DIRNAME = ".latexsnipper"
_APP_LOG_DIR_CACHE = None


def _app_state_dir():
    p = pathlib.Path.home() / APP_STATE_DIRNAME
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _app_log_dir() -> pathlib.Path:
    """Return a writable log directory, falling back when the profile log dir is locked."""
    global _APP_LOG_DIR_CACHE
    if _APP_LOG_DIR_CACHE is not None:
        return _APP_LOG_DIR_CACHE

    import tempfile

    candidates = [
        _app_state_dir() / "logs",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(pathlib.Path(local_app_data) / "LaTeXSnipper" / "logs")
    candidates.append(pathlib.Path(tempfile.gettempdir()) / "LaTeXSnipper" / "logs")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / f".write-test-{os.getpid()}.tmp"
            probe.write_text("ok", encoding="utf-8")
            try:
                probe.unlink()
            except Exception:
                pass
            _APP_LOG_DIR_CACHE = candidate
            return candidate
        except Exception:
            continue

    fallback = pathlib.Path(tempfile.gettempdir())
    _APP_LOG_DIR_CACHE = fallback
    return fallback

# 全局持有 crash 日志文件句柄，避免被 GC 或提前关闭
_CRASH_FH = None
_LSN_CONSOLE_CTRL_HANDLER = None
_LSN_DEBUG_CONSOLE_READY = False
_LSN_RUNTIME_LOG_DIALOG = None
_LSN_RUNTIME_LOG_PATH = None
_LSN_RUNTIME_LOG_FH_OUT = None
_LSN_RUNTIME_LOG_FH_ERR = None
_LSN_RUNTIME_LOG_RESET_DONE = False
_LSN_RUNTIME_LOG_CLEANUP_HOOKED = False

def _pre_bootstrap_runtime():
    global _CRASH_FH

    # 1) 避免 OpenMP 重复加载导致的 0xC0000409
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")

    # 2) 自定义标记，供 onnxruntime 使用 CPU EP
    os.environ.setdefault("ORT_NO_AZURE_EP", "1")

    # 3) 仅为 faulthandler 打开一个稳定的 crash 日志文件，不动 sys.stderr
    log_dir = pathlib.Path.home() / ".latexsnipper" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash-native.log"

    try:
        # 打开文件并保持在全局变量中，进程退出前不主动关闭
        _CRASH_FH = open(crash_log, "a", encoding="utf-8", buffering=1)
        _CRASH_FH.write(f"\n=== LaTeXSnipper start {datetime.datetime.now().isoformat()} ===\n")
        faulthandler.enable(all_threads=True, file=_CRASH_FH)
    except Exception:
        # 如果失败，就退回到默认 stderr，但也不要再改写 sys.stderr
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

_pre_bootstrap_runtime()


def _load_qt_symbols():
    from PyQt6.QtCore import (
        QBuffer,
        QCoreApplication,
        QEvent,
        QIODevice,
        QObject,
        QSize,
        Qt,
        QThread,
        QTimer,
        pyqtSignal,
    )
    from PyQt6.QtGui import QIcon, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication,
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTextEdit,
        QVBoxLayout,
        QWidget,
        QWidgetAction,
    )
    return (
        QApplication,
        QBuffer,
        QCoreApplication,
        QDialog,
        QDialogButtonBox,
        QEvent,
        QHBoxLayout,
        QIcon,
        QInputDialog,
        QIODevice,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QObject,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QScrollArea,
        QSize,
        QSizePolicy,
        QTextCursor,
        QTextEdit,
        QThread,
        QTimer,
        QVBoxLayout,
        QWidget,
        QWidgetAction,
        Qt,
        pyqtSignal,
    )


(
    QApplication,
    QBuffer,
    QCoreApplication,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QHBoxLayout,
    QIcon,
    QInputDialog,
    QIODevice,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QObject,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSize,
    QSizePolicy,
    QTextCursor,
    QTextEdit,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    Qt,
    pyqtSignal,
) = _load_qt_symbols()

# 必须在创建 QApplication 之前设置此属性（满足 QtWebEngine 的上下文共享要求）
try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

app = QApplication.instance() or QApplication(sys.argv)

_single_instance_lock = None

def _release_single_instance_lock():
    """Release single-instance file lock explicitly (used by restart path)."""
    global _single_instance_lock
    fh = _single_instance_lock
    _single_instance_lock = None
    if fh is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            try:
                fh.seek(0)
            except Exception:
                pass
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
    except Exception:
        pass
    try:
        fh.close()
    except Exception:
        pass


def _ensure_single_instance() -> bool:
    '''Prevent multiple GUI instances on Windows using a file lock.'''
    lock_dir = Path.home() / ".latexsnipper"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "instance.lock"
    restart_flag = os.environ.get("LATEXSNIPPER_RESTART") == "1"

    if os.name == "nt":
        try:
            import msvcrt
            # Restart path may need to wait for previous process to flush/close workers.
            attempts = 150 if restart_flag else 1
            delay = 0.2
            for _ in range(attempts):
                fh = open(lock_file, "a+", encoding="utf-8")
                try:
                    fh.seek(0)
                except Exception:
                    pass
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    fh.close()
                    if restart_flag:
                        import time
                        time.sleep(delay)
                        continue
                    return False
                global _single_instance_lock
                _single_instance_lock = fh
                return True
            return False
        except Exception:
            return True
    return True


if not _ensure_single_instance():
    try:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(None, "LaTeXSnipper", "Another instance is already running.")
    except Exception:
        print("[WARN] already running; exiting")
    sys.exit(0)

atexit.register(_release_single_instance_lock)


# --------- Startup Splash ---------
_STARTUP_SPLASH = None
_FORCE_ENTER_STARTUP_MESSAGE = "正在跳过依赖安装并进入主程序..."


class _StartupDialog(QWidget):
    def __init__(self, pixmap, flags):
        super().__init__(None, flags)
        self._label = QLabel(self)
        self._label.setScaledContents(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setPixmap(pixmap)

    def setPixmap(self, pixmap):
        self._label.setPixmap(pixmap)
        dpr = float(pixmap.devicePixelRatio() or 1.0)
        logical_w = max(1, int(round(pixmap.width() / dpr)))
        logical_h = max(1, int(round(pixmap.height() / dpr)))
        self._label.setGeometry(0, 0, logical_w, logical_h)
        self.resize(logical_w, logical_h)

    def finish(self, _window=None):
        self.close()


def _build_startup_splash_pixmap(app, status_text: str = ""):
    """Build a crisp high-DPI splash pixmap with a safe status text area."""
    from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon, QFontMetrics
    from PyQt6.QtCore import Qt, QRect

    logical_w, logical_h = 340, 360
    dpr = 1.0
    try:
        screen = app.primaryScreen() if app else None
        if screen is not None:
            dpr = float(screen.devicePixelRatio() or 1.0)
    except Exception:
        dpr = 1.0

    pm = QPixmap(int(logical_w * dpr), int(logical_h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(248, 248, 248, 246))
    painter.drawRoundedRect(10, 10, logical_w - 20, logical_h - 20, 20, 20)

    icon_path = resource_path("assets/icon.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
    icon_size = 112
    if not icon.isNull():
        icon_rect = QRect((logical_w - icon_size) // 2, 72, icon_size, icon_size)
        icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)

    painter.setPen(QColor(38, 38, 38))
    title_font = QFont("Microsoft YaHei UI", 16)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(QRect(0, 196, logical_w, 34), int(Qt.AlignmentFlag.AlignCenter), "LaTeXSnipper")

    painter.setPen(QColor(110, 110, 110))
    sub_font = QFont("Microsoft YaHei UI", 11)
    painter.setFont(sub_font)
    painter.drawText(QRect(0, 232, logical_w, 24), int(Qt.AlignmentFlag.AlignCenter), "正在启动...")

    status_font = QFont("Microsoft YaHei UI", 10)
    painter.setFont(status_font)
    fm = QFontMetrics(status_font)
    safe_text = fm.elidedText((status_text or "").strip(), Qt.TextElideMode.ElideRight, logical_w - 44)
    painter.setPen(QColor(92, 92, 92))
    painter.drawText(QRect(22, 270, logical_w - 44, 32), int(Qt.AlignmentFlag.AlignCenter), safe_text)

    painter.end()
    return pm


def _create_startup_splash(app):
    """Create a centered splash window to indicate app is loading."""
    try:
        pm = _build_startup_splash_pixmap(app, "")

        splash = _StartupDialog(
            pm,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        splash._lsn_status = ""
        try:
            screen = app.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                splash.move(geo.center().x() - splash.width() // 2, geo.center().y() - splash.height() // 2)
        except Exception:
            pass
        splash.show()
        app.processEvents()
        return splash
    except Exception as e:
        print(f"[WARN] startup splash init failed: {e}")
        return None


def _update_startup_splash(splash, message: str):
    if not splash:
        return
    try:
        app = QApplication.instance()
        if app is not None:
            splash._lsn_status = str(message or "")
            splash.setPixmap(_build_startup_splash_pixmap(app, splash._lsn_status))
            app.processEvents()
    except Exception:
        pass


def _ensure_startup_splash(message: str = ""):
    global _STARTUP_SPLASH
    app = QApplication.instance()
    if app is None:
        return None
    if _STARTUP_SPLASH is None:
        _STARTUP_SPLASH = _create_startup_splash(app)
    else:
        try:
            if not _STARTUP_SPLASH.isVisible():
                _STARTUP_SPLASH.show()
                app.processEvents()
        except Exception:
            pass
    _update_startup_splash(_STARTUP_SPLASH, message)
    return _STARTUP_SPLASH


def _take_startup_splash(app, message: str = ""):
    global _STARTUP_SPLASH
    splash = _STARTUP_SPLASH or _create_startup_splash(app)
    _STARTUP_SPLASH = splash
    try:
        if splash is not None and not splash.isVisible():
            splash.show()
            app.processEvents()
    except Exception:
        pass
    _update_startup_splash(splash, message)
    return splash


def _finish_startup_splash(splash, window=None):
    global _STARTUP_SPLASH
    try:
        if window is not None and hasattr(window, "_startup_progress"):
            window._startup_progress = None
    except Exception:
        pass
    try:
        if splash:
            splash.finish(window)
    except Exception:
        pass
    try:
        if splash is not None and _STARTUP_SPLASH is splash:
            _STARTUP_SPLASH = None
    except Exception:
        pass


def _hide_startup_splash_for_modal():
    """Hide the startup splash before showing dependency dialogs."""
    splash = _STARTUP_SPLASH
    if not splash:
        return
    try:
        if splash.isVisible():
            splash.hide()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
    except Exception:
        pass



def _deps_force_entered(db_module=None) -> bool:
    try:
        db = db_module
        if db is None:
            import deps_bootstrap as db
        checker = getattr(db, "was_last_ensure_deps_force_enter", None)
        return bool(checker()) if callable(checker) else False
    except Exception:
        return False


def _mark_startup_force_entered():
    os.environ["LATEXSNIPPER_FORCE_ENTERED"] = "1"
    app = QApplication.instance()
    if app is not None:
        return _take_startup_splash(app, _FORCE_ENTER_STARTUP_MESSAGE)
    return _ensure_startup_splash(_FORCE_ENTER_STARTUP_MESSAGE)


def _startup_force_enter_pending() -> bool:
    return os.environ.get("LATEXSNIPPER_FORCE_ENTERED") == "1"


def _startup_status_message(default: str) -> str:
    return _FORCE_ENTER_STARTUP_MESSAGE if _startup_force_enter_pending() else default


def _startup_deps_resume_message() -> str:
    if os.environ.pop("LATEXSNIPPER_FORCE_ENTERED", "0") == "1":
        return _FORCE_ENTER_STARTUP_MESSAGE
    return "依赖检查完成，继续启动..."


_ensure_startup_splash("配置 MathJax 与 WebEngine...")

# ============ QWebEngine profile 配置 ============
# 只保留 MathJax 本地资源访问所需设置，WebEngineProcess 路径由完整打包负责。
try:
    from PyQt6.QtWebEngineCore import QWebEngineProfile
    
    profile = QWebEngineProfile.defaultProfile()
    
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    
    settings = profile.settings()
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    
    print("[MathJax] QWebEngine 配置已应用（支持本地文件+CDN 备选）")
except Exception as e:
    print(f"[WARN] QWebEngine 配置失败: {e}")

class LogViewerDialog(QDialog):
    def __init__(self, log_file: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("实时日志")
        self.resize(820, 520)
        self._log_file = Path(log_file)
        self._pos = 0
        self._theme_is_dark_cached = None

        lay = QVBoxLayout(self)
        self.lbl = QLabel(str(self._log_file))
        self.lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.txt = QPlainTextEdit(); self.txt.setReadOnly(True)

        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("打开目录")
        self.btn_clear = QPushButton("清空日志")
        self.btn_close = QPushButton("关闭")
        btn_row.addWidget(self.btn_open); btn_row.addWidget(self.btn_clear); btn_row.addStretch(); btn_row.addWidget(self.btn_close)

        lay.addWidget(self.lbl); lay.addWidget(self.txt, 1); lay.addLayout(btn_row)

        self.btn_open.clicked.connect(self._open_dir)
        self.btn_clear.clicked.connect(self._clear_log)
        self.btn_close.clicked.connect(self.close)

        self._ensure_file()
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._poll_file)
        self.timer.start()
        self._poll_file(_initial=True)
        self._apply_theme_styles(force=True)

    def _apply_theme_styles(self, force: bool = False):
        dark = _is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        try:
            self.lbl.setStyleSheet(f"color: {_dialog_theme_tokens()['muted']};")
        except Exception:
            pass

    def _ensure_file(self):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._log_file.exists():
            self._log_file.write_text("", encoding="utf-8")
        self._pos = 0

    def _open_dir(self):
        try:
            if os.name == "nt":
                os.startfile(self._log_file.parent)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(self._log_file.parent)])
        except Exception:
            pass

    def _clear_log(self):
        try:
            self._log_file.write_text("", encoding="utf-8")
            self._pos = 0
            self.txt.clear()
        except Exception:
            pass

    def _poll_file(self, _initial: bool = False):
        try:
            with self._log_file.open("r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
            if chunk:
                self.txt.appendPlainText(chunk.rstrip("\n"))
                self.txt.verticalScrollBar().setValue(self.txt.verticalScrollBar().maximum())
        except Exception:
            pass

    def closeEvent(self, ev):
        try:
            self.timer.stop()
        except Exception:
            pass
        return super().closeEvent(ev)

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._apply_theme_styles(force=True)
        except Exception:
            pass


class RuntimeLogDialog(QDialog):
    """初始化/运行日志窗口（GUI 版，不使用系统控制台）。"""

    def __init__(self, log_file: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LaTeXSnipper 初始化与运行日志")
        self.resize(980, 620)
        self._log_file = Path(log_file)
        self._pos = 0
        self._theme_is_dark_cached = None
        try:
            icon_path = resource_path("assets/icon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        lay = QVBoxLayout(self)
        self.lbl = QLabel(str(self._log_file))
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)

        use_fluent = False
        try:
            from qfluentwidgets import PushButton as FluentPushButton, FluentIcon
            use_fluent = True
        except Exception:
            FluentPushButton = None
            FluentIcon = None

        btn_row = QHBoxLayout()
        if use_fluent and FluentPushButton and FluentIcon:
            self.btn_open = FluentPushButton(FluentIcon.FOLDER, "打开目录")
            self.btn_copy_all = FluentPushButton(FluentIcon.COPY, "复制全部")
            self.btn_clear_view = FluentPushButton(FluentIcon.BROOM, "清空视图")
            self.btn_close = FluentPushButton(FluentIcon.CLOSE, "关闭")
        else:
            self.btn_open = QPushButton("打开目录")
            self.btn_copy_all = QPushButton("复制全部")
            self.btn_clear_view = QPushButton("清空视图")
            self.btn_close = QPushButton("关闭")
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_copy_all)
        btn_row.addWidget(self.btn_clear_view)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)

        lay.addWidget(self.lbl)
        lay.addWidget(self.txt, 1)
        lay.addLayout(btn_row)

        self.btn_open.clicked.connect(self._open_dir)
        self.btn_copy_all.clicked.connect(self._copy_all)
        self.btn_clear_view.clicked.connect(self._clear_view)
        self.btn_close.clicked.connect(self.hide)

        self._ensure_file()
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll_file)
        self.timer.start()
        self._poll_file(_initial=True)
        self._apply_theme_styles(force=True)

    def _apply_theme_styles(self, force: bool = False):
        dark = _is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        try:
            self.lbl.setStyleSheet(f"color: {_dialog_theme_tokens()['muted']};")
        except Exception:
            pass

    def _ensure_file(self):
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self._log_file.exists():
            self._log_file.write_text("", encoding="utf-8")
        self._pos = 0

    def _open_dir(self):
        try:
            if os.name == "nt":
                os.startfile(self._log_file.parent)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(self._log_file.parent)])
        except Exception:
            pass

    def _copy_all(self):
        try:
            QApplication.clipboard().setText(self.txt.toPlainText())
            try:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.success(
                    title="已复制",
                    content="日志内容已复制到剪贴板",
                    parent=self,
                    duration=1500,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
        except Exception:
            pass

    def _clear_view(self):
        try:
            self.txt.clear()
            try:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.success(
                    title="已清空",
                    content="日志视图已清空",
                    parent=self,
                    duration=1500,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
        except Exception:
            pass

    def _poll_file(self, _initial: bool = False):
        try:
            with self._log_file.open("r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._pos)
                chunk = f.read()
                self._pos = f.tell()
            if chunk:
                self.txt.moveCursor(QTextCursor.MoveOperation.End)
                self.txt.insertPlainText(chunk)
                sb = self.txt.verticalScrollBar()
                sb.setValue(sb.maximum())
        except Exception:
            pass

    def closeEvent(self, ev):
        # 不销毁，只隐藏；避免重复创建窗口与信号连接。
        try:
            ev.ignore()
            self.hide()
            return
        except Exception:
            pass
        return super().closeEvent(ev)

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._apply_theme_styles(force=True)
        except Exception:
            pass

APP_LOG_FILE: Path | None = None
_ORIGINAL_PRINT = None
_PRINT_BRIDGE_INSTALLED = False
_RUNTIME_SESSION_HANDLER = None
_APP_LOGGING_INITIALIZED = False

def init_app_logging() -> Path:
    """
    初始化应用日志：控制台 + 轮转文件(~/.latexsnipper/logs/app.log)。
    多次调用会复用已存在的处理器。
    """
    global APP_LOG_FILE, _RUNTIME_SESSION_HANDLER, _APP_LOGGING_INITIALIZED
    _ensure_startup_splash(_startup_status_message("初始化日志..."))
    log_dir = Path(_app_log_dir())
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    if _APP_LOGGING_INITIALIZED and APP_LOG_FILE is not None:
        return APP_LOG_FILE

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 避免重复添加处理器
    has_file = any(
        isinstance(h, RotatingFileHandler)
        and os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(str(log_path))
        for h in root.handlers
    )
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers)

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    file_handler = None
    active_log_path = log_path
    if not has_file:
        try:
            fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        except PermissionError as e:
            active_log_path = log_dir / f"app-{os.getpid()}.log"
            try:
                fh = RotatingFileHandler(active_log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
                try:
                    if sys.__stderr__ and not getattr(sys.__stderr__, "closed", False):
                        sys.__stderr__.write(
                            f"[WARN] app.log 被占用，已切换到 {active_log_path}: {e}\n"
                        )
                except Exception:
                    pass
            except Exception as fallback_error:
                fh = None
                try:
                    if sys.__stderr__ and not getattr(sys.__stderr__, "closed", False):
                        sys.__stderr__.write(
                            f"[WARN] 无法初始化文件日志，继续仅使用控制台日志: {fallback_error}\n"
                        )
                except Exception:
                    pass
        if fh is not None:
            fh.setFormatter(fmt)
            root.addHandler(fh)
            file_handler = fh
    else:
        for h in root.handlers:
            if isinstance(h, RotatingFileHandler) and os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(str(log_path)):
                file_handler = h
                active_log_path = Path(getattr(h, "baseFilename", str(log_path)))
                break
    if not has_stream:
        # 固定写到原始 stdout，避免后续 stdout 重定向导致 logging 链路异常。
        sh = logging.StreamHandler(sys.__stdout__)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    _RUNTIME_SESSION_HANDLER = None

    # 将 print 输出桥接到 app.log，提升日志文件可用性。
    global _ORIGINAL_PRINT, _PRINT_BRIDGE_INSTALLED
    if (not _PRINT_BRIDGE_INSTALLED) and (file_handler is not None):
        _ORIGINAL_PRINT = builtins.print

        bridge_logger = logging.getLogger("runtime.print")
        bridge_logger.setLevel(logging.INFO)
        bridge_logger.propagate = False
        if not any(h is file_handler for h in bridge_logger.handlers):
            bridge_logger.addHandler(file_handler)

        def _print_bridge(*args, **kwargs):
            # 先保持原有 print 行为（终端/GUI 日志窗口）。
            _ORIGINAL_PRINT(*args, **kwargs)
            try:
                target = kwargs.get("file", None)
                # 仅桥接标准输出流，避免写入到其它文件对象时重复记录。
                if target not in (None, sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
                    return
                sep = kwargs.get("sep", " ")
                msg = sep.join(str(a) for a in args).rstrip("\r\n")
                if msg:
                    bridge_logger.info(msg)
            except Exception:
                pass

        builtins.print = _print_bridge
        _PRINT_BRIDGE_INSTALLED = True

    APP_LOG_FILE = active_log_path
    if not getattr(root, "_latexsnipper_session_logged", False):
        logging.info("session start: pid=%s exe=%s log=%s", os.getpid(), sys.executable, active_log_path)
        setattr(root, "_latexsnipper_session_logged", True)
    
    # 初始化 LaTeX 设置
    _ensure_startup_splash(_startup_status_message("初始化 LaTeX 设置..."))
    try:
        config_dir = Path.home() / ".latexsnipper"
        config_dir.mkdir(parents=True, exist_ok=True)
        init_latex_settings(config_dir)
        print("[LaTeX] 设置初始化完成")
    except Exception as e:
        print(f"[WARN] LaTeX 设置初始化失败: {e}")

    _APP_LOGGING_INITIALIZED = True
    
    return active_log_path

def open_realtime_log_window(parent=None):
    """
    打开实时日志窗口，显示开发控制台/文件的合并日志。
    """
    global APP_LOG_FILE
    if APP_LOG_FILE is None:
        APP_LOG_FILE = init_app_logging()
    try:
        dlg = LogViewerDialog(APP_LOG_FILE, parent=parent)
        dlg.exec()
    except Exception as e:
        QMessageBox.critical(parent, "错误", f"无法打开日志窗口: {e}")

def _read_deps_dir_from_config() -> Path | None:
    """
    从配置文件读取依赖目录。
    结构: { "install_base_dir": "D:/LaTeXSnipper/deps" }
    """
    cfg = _config_path()
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        v = data.get("install_base_dir")
        if isinstance(v, str) and v.strip():
            return Path(v)
    except Exception:
        pass
    return None

def open_deps_terminal(parent=None):
    """
    在依赖目录打开 cmd.exe，并预置:
    - PATH: 依赖目录内的可用 Python 优先
    """
    deps_dir = _read_deps_dir_from_config()
    if not deps_dir or not deps_dir.exists():
        QMessageBox.warning(parent, "未找到依赖目录", "请先通过依赖向导选择或安装依赖目录。")
        return

    pyexe = _find_install_base_python(deps_dir)
    py_dir = pyexe.parent if pyexe is not None else None

    # 组装环境
    env = os.environ.copy()
    # 无论打包模式还是开发模式，都允许注入依赖目录内的 Python 路径到 PATH
    if py_dir is not None and py_dir.exists():
        env["PATH"] = f"{py_dir};{env.get('PATH','')}"

    # 进入目录并打开 cmd，显示简短提示
    banner = (
        'echo LaTeXSnipper 依赖终端 && '
        'where python && python --version && pip --version && '
        'echo.'
    )
    try:
        subprocess.Popen(
            ["cmd.exe", "/K", banner],
            cwd=str(deps_dir),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE  # 独立窗口
        )
    except Exception as e:
        QMessageBox.critical(parent, "打开失败", f"无法打开依赖终端: {e}")

# AA_ShareOpenGLContexts 已在文件顶部 QApplication 创建前设置

def apply_theme(mode: str = "AUTO") -> bool:
    """安全设置 QFluentWidgets 主题，避免 QConfig 已被销毁导致的 RuntimeError。"""
    try:
        import importlib
        import qfluentwidgets.common.config as cfg
        import qfluentwidgets.common.style_sheet as ss
        theme = getattr(cfg.Theme, mode)
        try:
            ss.setTheme(theme)
            return True
        except RuntimeError:
            # 可能因先前实例销毁导致的 wrapper 失效，尝试重载模块后重试
            cfg = importlib.reload(cfg)
            ss = importlib.reload(ss)
            theme = getattr(cfg.Theme, mode)
            ss.setTheme(theme)
            return True
    except Exception as e:
        print(f"[WARN] 应用主题失败: {e}")
        return False


def normalize_theme_mode(value: str | None) -> str:
    mode = str(value or "auto").strip().lower()
    return mode if mode in ("light", "dark", "auto") else "auto"


def apply_theme_mode(mode: str | None) -> bool:
    normalized = normalize_theme_mode(mode)
    map_mode = {
        "light": "LIGHT",
        "dark": "DARK",
        "auto": "AUTO",
    }
    return apply_theme(map_mode.get(normalized, "AUTO"))


def read_theme_mode_from_config() -> str:
    try:
        cfg_path = _config_path()
        if not cfg_path.exists():
            return "auto"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return "auto"
        return normalize_theme_mode(data.get("theme_mode", "auto"))
    except Exception:
        return "auto"

def _get_app_root() -> Path:
    """获取应用程序根目录
    
    在打包模式下（PyInstaller），返回 _internal 目录
    在开发模式下，返回 src 目录所在的目录
    """
    # 兼容 PyInstaller 打包与源码运行
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller 打包模式：sys._MEIPASS 指向 _internal 目录
        return Path(sys._MEIPASS)
    # 开发模式：返回 main.py 所在目录（即 src 目录）
    return Path(__file__).resolve().parent

def _is_packaged_mode() -> bool:
    """
    检测是否在打包模式下运行。
    打包模式特征：
    1. sys._MEIPASS 存在
    2. APP_DIR 包含 _internal 路径
    """
    # 首先检查 sys._MEIPASS（PyInstaller 标志）
    if hasattr(sys, '_MEIPASS'):
        return True
    
    # 检查 APP_DIR 路径中是否包含 _internal（打包后的标志）
    app_dir_str = str(_get_app_root()).lower()
    return '_internal' in app_dir_str

APP_DIR = _get_app_root()
# 可通过环境变量 `LATEXSNIPPER_MODEL_DIR` 覆盖模型目录
_model_env = os.environ.get("LATEXSNIPPER_MODEL_DIR")
MODEL_DIR = Path(_model_env) if _model_env else (APP_DIR / "models")

# 确保目录存在
MODEL_DIR.mkdir(parents=True, exist_ok=True)

print(f"[DEBUG] 主程序目录: {APP_DIR}")
print(f"[DEBUG] 打包模式: {_is_packaged_mode()}")
# 获取依赖目录，优先环境变量，其次配置文件，最后默认
_deps_env = os.environ.get("LATEXSNIPPER_DEPS_DIR")
DEPS_DIR = Path(_deps_env) if _deps_env else (APP_DIR / "deps")
DEPS_DIR.mkdir(parents=True, exist_ok=True)

print(f"[DEBUG] 依赖目录: {DEPS_DIR}")

class TeeWriter(io.TextIOBase):
    """把写入同时输出到两个流（保留 IDE 输出+新控制台），对 I/O 错误宽容处理。"""

    def __init__(self, a, b):
        self._a = a
        self._b = b
        self._closed = False
        self._b_line_buffer = ""
        # 保存原始流的引用，用于恢复
        self._original_a = a
        self._original_b = b

    @property
    def closed(self) -> bool:
        return self._closed

    def writable(self) -> bool:
        return True

    def _stream_ok(self, stream) -> bool:
        """检查流是否可用"""
        if stream is None:
            return False
        if getattr(stream, "closed", False):
            return False
        if not hasattr(stream, "write"):
            return False
        return True

    def write(self, s):
        if self._closed:
            return 0
        if not isinstance(s, str):
            s = str(s)

        written = 0
        if self._stream_ok(self._a):
            try:
                self._a.write(s)
                written = len(s)
            except (OSError, ValueError, AttributeError):
                pass
            except Exception:
                pass

        if self._stream_ok(self._b):
            try:
                self._b_line_buffer += s
                while True:
                    idx = self._b_line_buffer.find("\n")
                    if idx == -1:
                        break
                    line = self._b_line_buffer[:idx + 1]
                    self._b.write(line)
                    self._b_line_buffer = self._b_line_buffer[idx + 1:]
                written = len(s)
            except (OSError, ValueError, AttributeError):
                pass
            except Exception:
                pass

        # 只在写入成功后 flush
        for stream in (self._a,):
            if not self._stream_ok(stream):
                continue
            try:
                stream.flush()
            except Exception:
                pass

        if self._stream_ok(self._b):
            try:
                self._b.flush()
            except Exception:
                pass

        return written if written else len(s)

    def flush(self):
        if self._closed:
            return
        if self._stream_ok(self._b) and self._b_line_buffer:
            try:
                self._b.write(self._b_line_buffer)
                self._b_line_buffer = ""
            except Exception:
                pass
        for stream in (self._a, self._b):
            if not self._stream_ok(stream):
                continue
            try:
                stream.flush()
            except Exception:
                pass

    def close(self):
        # 不主动关闭底层流，只标记自身已关闭
        self._closed = True

    def fileno(self):
        """返回主流的文件描述符（如果可用）"""
        for stream in (self._a, self._b):
            if self._stream_ok(stream) and hasattr(stream, "fileno"):
                try:
                    return stream.fileno()
                except Exception:
                    pass
        raise OSError("No valid file descriptor")

def _runtime_log_path() -> Path:
    global _LSN_RUNTIME_LOG_PATH
    if _LSN_RUNTIME_LOG_PATH is not None:
        return _LSN_RUNTIME_LOG_PATH
    p = _app_log_dir() / "runtime-console.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    _LSN_RUNTIME_LOG_PATH = p
    return p


def _cleanup_runtime_log_session():
    global _LSN_RUNTIME_LOG_FH_OUT, _LSN_RUNTIME_LOG_FH_ERR, _LSN_RUNTIME_LOG_DIALOG, _LSN_DEBUG_CONSOLE_READY, _RUNTIME_SESSION_HANDLER
    try:
        if isinstance(sys.stdout, TeeWriter):
            sys.stdout = sys.__stdout__
        if isinstance(sys.stderr, TeeWriter):
            sys.stderr = sys.__stderr__
    except Exception:
        pass
    try:
        if _LSN_RUNTIME_LOG_DIALOG is not None:
            try:
                _LSN_RUNTIME_LOG_DIALOG.hide()
            except Exception:
                pass
    except Exception:
        pass
    for fh_name in ("_LSN_RUNTIME_LOG_FH_OUT", "_LSN_RUNTIME_LOG_FH_ERR"):
        fh = globals().get(fh_name)
        if fh is not None:
            try:
                fh.flush()
            except Exception:
                pass
            try:
                fh.close()
            except Exception:
                pass
        globals()[fh_name] = None
    try:
        if _RUNTIME_SESSION_HANDLER is not None:
            root = logging.getLogger()
            try:
                root.removeHandler(_RUNTIME_SESSION_HANDLER)
            except Exception:
                pass
            try:
                _RUNTIME_SESSION_HANDLER.flush()
            except Exception:
                pass
            try:
                _RUNTIME_SESSION_HANDLER.close()
            except Exception:
                pass
    except Exception:
        pass
    _RUNTIME_SESSION_HANDLER = None
    try:
        p = _runtime_log_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass
    _LSN_DEBUG_CONSOLE_READY = False


def _ensure_runtime_log_cleanup_hook():
    global _LSN_RUNTIME_LOG_CLEANUP_HOOKED
    if _LSN_RUNTIME_LOG_CLEANUP_HOOKED:
        return
    try:
        app = QApplication.instance()
        if app is None:
            return
        app.aboutToQuit.connect(_cleanup_runtime_log_session)
        _LSN_RUNTIME_LOG_CLEANUP_HOOKED = True
    except Exception:
        pass


def _hook_runtime_log_streams(tee: bool = True):
    global _LSN_RUNTIME_LOG_FH_OUT, _LSN_RUNTIME_LOG_FH_ERR, _LSN_RUNTIME_LOG_RESET_DONE
    if _LSN_RUNTIME_LOG_FH_OUT is not None and _LSN_RUNTIME_LOG_FH_ERR is not None:
        return

    log_path = _runtime_log_path()
    if not _LSN_RUNTIME_LOG_RESET_DONE:
        try:
            log_path.write_text("", encoding="utf-8")
        except Exception:
            pass
        _LSN_RUNTIME_LOG_RESET_DONE = True

    _LSN_RUNTIME_LOG_FH_OUT = open(log_path, "a", encoding="utf-8", buffering=1)
    _LSN_RUNTIME_LOG_FH_ERR = open(log_path, "a", encoding="utf-8", buffering=1)
    _ensure_runtime_log_cleanup_hook()

    base_out = sys.stdout if sys.stdout and not getattr(sys.stdout, "closed", False) else sys.__stdout__
    base_err = sys.stderr if sys.stderr and not getattr(sys.stderr, "closed", False) else sys.__stderr__
    if isinstance(base_out, TeeWriter):
        base_out = base_out._original_a or sys.__stdout__
    if isinstance(base_err, TeeWriter):
        base_err = base_err._original_a or sys.__stderr__

    if tee and base_out:
        sys.stdout = TeeWriter(base_out, _LSN_RUNTIME_LOG_FH_OUT)
    else:
        sys.stdout = _LSN_RUNTIME_LOG_FH_OUT

    if tee and base_err:
        sys.stderr = TeeWriter(base_err, _LSN_RUNTIME_LOG_FH_ERR)
    else:
        sys.stderr = _LSN_RUNTIME_LOG_FH_ERR


def _show_runtime_log_window(parent=None):
    global _LSN_RUNTIME_LOG_DIALOG
    app = QApplication.instance() or QApplication(sys.argv)
    log_path = _runtime_log_path()
    if _LSN_RUNTIME_LOG_DIALOG is None:
        _LSN_RUNTIME_LOG_DIALOG = RuntimeLogDialog(log_path, parent=parent)
    try:
        _LSN_RUNTIME_LOG_DIALOG.show()
        _LSN_RUNTIME_LOG_DIALOG.raise_()
        _LSN_RUNTIME_LOG_DIALOG.activateWindow()
    except Exception:
        pass
    try:
        app.processEvents()
    except Exception:
        pass


def open_debug_console(force: bool = False, tee: bool = True):
    """GUI 日志窗口模式：可滚动/可复制"""
    global _LSN_DEBUG_CONSOLE_READY

    if getattr(sys, "frozen", False):
        tee = False

    def _read_startup_console_pref(default: bool = False) -> bool:
        try:
            cfg = _config_path()
            if not cfg.exists():
                return default
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return default
            raw = data.get("show_startup_console", default)
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            if isinstance(raw, str):
                return raw.strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            pass
        return default

    env_pref = os.environ.get("LATEXSNIPPER_SHOW_CONSOLE")
    if env_pref is not None:
        want = env_pref.strip().lower() in ("1", "true", "yes", "on")
    else:
        want = _read_startup_console_pref(default=False)
    want = bool(force or want)
    os.environ["LATEXSNIPPER_SHOW_CONSOLE"] = "1" if want else "0"

    if not want:
        try:
            if _LSN_RUNTIME_LOG_DIALOG is not None:
                _LSN_RUNTIME_LOG_DIALOG.hide()
        except Exception:
            pass
        return

    try:
        if _LSN_DEBUG_CONSOLE_READY:
            _show_runtime_log_window()
            return
        _hook_runtime_log_streams(tee=tee)
        _show_runtime_log_window()
        _LSN_DEBUG_CONSOLE_READY = True
        print("[INFO] GUI 日志窗口已打开")
    except Exception:
        try:
            if sys.__stdout__ and not getattr(sys.__stdout__, "closed", False):
                sys.stdout = sys.__stdout__
            if sys.__stderr__ and not getattr(sys.__stderr__, "closed", False):
                sys.stderr = sys.__stderr__
        except Exception:
            pass

def _same_exe(a: str, b: str) -> bool:
    try:
        return os.path.abspath(a).lower() == os.path.abspath(b).lower()
    except Exception:
        return False

def _config_path() -> Path:
    # 统一配置路径：~/.latexsnipper/LaTeXSnipper_config.json
    return _app_state_dir() / CONFIG_FILENAME

def _looks_like_packaged_deps_dir(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        text = str(path.resolve()).lower()
    except Exception:
        text = str(path).lower()
    return ("_internal" in text) and text.endswith("\\deps")


def _iter_install_base_python_candidates(base_dir: Path) -> list[Path]:
    """Return likely python.exe candidates inside a selected dependency base directory."""
    base_dir = Path(base_dir)
    candidates = [
        base_dir / "python.exe",
        base_dir / "Scripts" / "python.exe",
        base_dir / "python311" / "python.exe",
        base_dir / "python311" / "Scripts" / "python.exe",
        base_dir / "Python311" / "python.exe",
        base_dir / "Python311" / "Scripts" / "python.exe",
        base_dir / "python_full" / "python.exe",
        base_dir / "venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "Scripts" / "python.exe",
    ]
    try:
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if name in {"venv", ".venv", "python_full"} or name.startswith("python"):
                candidates.extend([
                    child / "python.exe",
                    child / "Scripts" / "python.exe",
                ])
    except Exception:
        pass

    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def _find_install_base_python(base_dir: Path) -> Path | None:
    """Reuse any existing python.exe inside the dependency directory."""
    for candidate in _iter_install_base_python_candidates(base_dir):
        try:
            if candidate.exists():
                return candidate
        except Exception:
            continue
    return None


def _normalize_install_base_dir(selected_dir: Path) -> Path:
    """
    Normalize the dependency base directory.

    The chosen path should be the base directory that contains a nested
    `python311`, not the leaf `python311` directory itself. If the user or a
    previous partial initialization points at an empty leaf like `.../python311`,
    fold it back to the parent to avoid `python311/python311`.
    """
    path = Path(selected_dir)
    try:
        name = path.name.lower()
    except Exception:
        return path

    looks_like_python_leaf = (
        name in {"venv", ".venv", "python_full"}
        or name.startswith("python")
    )
    if not looks_like_python_leaf:
        return path

    existing_py = _find_install_base_python(path)
    if existing_py is not None:
        return path

    parent = path.parent
    try:
        if parent and str(parent) != str(path):
            return parent
    except Exception:
        pass
    return path

def _current_dev_install_base_dir() -> Path | None:
    if _is_packaged_mode():
        return None
    try:
        exe_path = Path(sys.executable).resolve()
        exe_name = exe_path.name.lower()
        parent_name = exe_path.parent.name.lower()
        if exe_name == "python.exe":
            if parent_name == "deps":
                base = exe_path.parent
                if base.exists():
                    return base
            if exe_path.parent.parent.name.lower() == "deps" and (
                parent_name.startswith("python") or parent_name in {"venv", ".venv", "python_full", "scripts"}
            ):
                base = exe_path.parent.parent
                if base.exists():
                    return base
    except Exception:
        pass
    try:
        base = (APP_DIR / "deps").resolve()
        pyexe = _find_install_base_python(base)
        if pyexe is not None and _same_exe(str(pyexe), sys.executable):
            return base
    except Exception:
        pass
    return None

def _read_install_base_dir() -> Path | None:
    cfg = _config_path()
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text("utf-8"))
            p = _normalize_install_base_dir(Path(data.get("install_base_dir", "")).expanduser())
            if p and p.exists():
                if (not _is_packaged_mode()) and _looks_like_packaged_deps_dir(p):
                    return None
                return p
        except Exception:
            pass
    return None

def _get_bundled_deps_dir_for_packaged() -> Path | None:
    """
    打包模式首启时自动探测内置依赖目录:
    期望目录结构: <_internal>/deps/<python*>/python.exe
    """
    if not _is_packaged_mode():
        return None
    candidates: list[Path] = []
    try:
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            candidates.append(meipass / "deps")
    except Exception:
        pass
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "_internal" / "deps",
            exe_dir / "deps",
        ])
    except Exception:
        pass
    seen: set[str] = set()
    for base in candidates:
        try:
            key = str(base.resolve()).lower()
        except Exception:
            key = str(base).lower()
        if key in seen:
            continue
        seen.add(key)
        pyexe = _find_install_base_python(base)
        if pyexe is not None and pyexe.exists():
            return base
    return None

def _select_install_base_dir() -> Path:
    """
    弹出目录选择对话框。返回用户选择的目录。
    - 如果用户取消，抛出 RuntimeError("user canceled")
    - 不会自动写入配置文件（由调用者决定）
    """
    from pathlib import Path
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFont
        app = QApplication.instance() or QApplication([])
        apply_theme_mode(read_theme_mode_from_config())
        font = QFont("Microsoft YaHei UI", 9)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
        d = _select_existing_directory_with_icon(None, "请选择依赖安装目录", os.path.expanduser("~"))
        if d:
            p = _normalize_install_base_dir(Path(d))
            p.mkdir(parents=True, exist_ok=True)
            return p
        else:
            # 用户取消
            raise RuntimeError("user canceled")
    except RuntimeError:
        raise
    except Exception as e:
        print(f"[ERROR] 目录选择失败: {e}")
        raise RuntimeError("user canceled")


def _apply_app_window_icon(win) -> None:
    try:
        from PyQt6.QtGui import QIcon
        icon_path = resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            win.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass


def _select_existing_directory_with_icon(parent, title: str, initial_dir: str) -> str:
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_dir)
    dlg.setFileMode(QFileDialog.FileMode.Directory)
    dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return ""
    selected = dlg.selectedFiles()
    return selected[0] if selected else ""


def _select_save_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_path, filter_)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dlg.setFileMode(QFileDialog.FileMode.AnyFile)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return "", ""
    selected = dlg.selectedFiles()
    chosen_filter = dlg.selectedNameFilter()
    return (selected[0] if selected else ""), chosen_filter


def _select_open_file_with_icon(parent, title: str, initial_path: str, filter_: str):
    from PyQt6.QtWidgets import QFileDialog
    dlg = QFileDialog(parent, title, initial_path, filter_)
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    _apply_app_window_icon(dlg)
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return "", ""
    selected = dlg.selectedFiles()
    chosen_filter = dlg.selectedNameFilter()
    return (selected[0] if selected else ""), chosen_filter

def _save_install_base_dir(p: Path) -> None:
    """保存依赖目录到配置文件。"""
    try:
        p = _normalize_install_base_dir(p)
        cfg = {}
        c = _config_path()
        if c.exists():
            cfg = json.loads(c.read_text("utf-8") or "{}")
        cfg["install_base_dir"] = str(p)
        c.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] 配置已保存: {p}")
    except Exception as e:
        print(f"[WARN] 保存配置失败: {e}")

def resolve_install_base_dir() -> Path:
    """
    解析依赖安装目录。统一处理开发模式和打包模式。
    
    流程：
    1. 检查配置文件中的 install_base_dir
    2. 打包模式首启时，若存在内置 `_internal/deps` 且其中已带可用 Python，自动采用并写入配置
    3. 若仍为空，弹出目录选择对话框
    4. 检查选定目录是否已有可复用 Python
       - 有：使用该目录，保存配置，返回
       - 无：仅保存目录并返回；是否初始化 python311 交给依赖向导内部处理
    """
    import time

    if not _is_packaged_mode():
        current_dev_base = _current_dev_install_base_dir()
        if current_dev_base is not None:
            return current_dev_base
    
    # 第1步：读取配置中的依赖目录
    p = _read_install_base_dir()

    # 打包模式首启：若无配置，自动使用内置 deps（免手动选择/安装）
    if not p:
        bundled = _get_bundled_deps_dir_for_packaged()
        if bundled:
            try:
                bundled.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            print(f"[INFO] 首次启动：自动使用内置依赖目录: {bundled}")
            _save_install_base_dir(bundled)
            p = bundled

    # 第2步：仍无目录则弹出选择框
    if not p:
        print("[INFO] 首次启动，请选择依赖安装目录...")
        try:
            p = _select_install_base_dir()
        except RuntimeError:
            print("[ERROR] 用户取消了目录选择，退出。")
            time.sleep(2)
            sys.exit(7)
    p = _normalize_install_base_dir(p)
    
    py_exe = _find_install_base_python(p)
    
    # 第3步：检查 Python 是否已存在
    if py_exe is not None and py_exe.exists():
        print(f"[OK] ✓ 已复用目录内 Python: {py_exe}")
        _save_install_base_dir(p)
        return p

    print(f"[INFO] 选定目录未检测到可复用 Python，将由依赖向导按需初始化: {p / 'python311'}")
    _save_install_base_dir(p)
    return p

def _current_runtime_roots() -> list[str]:
    """收集当前进程解释器的根目录及标准库路径，净化时必须保留。"""
    bases: set[Path] = set()
    for b in (getattr(sys, "base_prefix", None),
              getattr(sys, "exec_prefix", None),
              getattr(sys, "prefix", None)):
        if b:
            try:
                bases.add(Path(b).resolve())
            except Exception:
                pass

    roots: set[str] = set()
    for base in bases:
        roots.update({
            str(base),
            str(base / "DLLs"),
            str(base / "Lib"),
            str(base / "Lib" / "site-packages"),
        })
    # 保留当前进程已在用的 pythonXY.zip（支持 3.11/3.12 等三位版本号）
    try:
        for p in list(sys.path):
            try:
                q = Path(p)
                if q.name.lower().startswith("python") and q.suffix.lower() == ".zip":
                    roots.add(str(q.resolve()))
            except Exception:
                continue
    except Exception:
        pass
    return list(roots)

def _sanitize_sys_path(pyexe: str | None, base_dir: Path):
    """净化 sys.path：保留项目根、私有解释器、当前运行时标准库；仅清理 WindowsApps 等污染。"""
    try:
        allowed = [Path(r).resolve() for r in _allowed_roots_for(pyexe, base_dir)]
        runtime_roots = [Path(r).resolve() for r in _current_runtime_roots()]

        def under_any(q: Path, bases: list[Path]) -> bool:
            ql = str(q).lower()
            for b in bases:
                bl = str(b).lower()
                if ql.startswith(bl):
                    return True
            return False

        def ok(item: str) -> bool:
            try:
                q = Path(item).resolve()
            except Exception:
                return False
            sl = str(q).lower()
            # 只过滤系统商店污染
            if "windowsapps\\python" in sl or "microsoft\\windowsapps" in sl:
                return False

            # 允许：项目/私有路径、当前运行时标准库路径、以及标准库 zip
            if under_any(q, allowed) or under_any(q, runtime_roots):
                return True

            # 兼容：匹配 pythonXY(或XYY).zip —— 使用 \d+ 支持 3.11/3.12
            try:
                import re
                if re.fullmatch(r"python\d+\.zip", q.name.lower()):
                    return True
            except Exception:
                pass
            return False
        newp = [p for p in list(sys.path) if ok(p)]

        # 确保源码目录在最前
        try:
            src_dir = str(Path(__file__).resolve().parent)
            if src_dir not in newp:
                newp.insert(0, src_dir)
        except Exception:
            pass

        sys.path[:] = newp
    except Exception:
        pass

def _in_ide() -> bool:
    """检测是否在 IDE 中运行（PyCharm/调试主控台等）。"""
    e = os.environ
    return any(k in e for k in ("PYCHARM_HOSTED", "PYCHARM_DISPLAY_PORT", "PYDEV_CONSOLE_ENCODING"))

def _python_base_from_exe(pyexe: str) -> Path:
    p = Path(pyexe)
    return p.parent.parent if p.parent.name.lower() == "scripts" else p.parent

def _stdlib_zip_versions(base: Path) -> list[tuple[int, int, str]]:
    """返回该基目录下 pythonXY.zip 的 (X,Y,路径) 列表，兼容 3.11/3.12 等多位次版本。"""
    out: list[tuple[int, int, str]] = []
    try:
        for p in base.glob("python*.zip"):
            bn = p.name
            m = re.fullmatch(r"python(\d)(\d+)\.zip", bn, re.I)
            if m:
                out.append((int(m.group(1)), int(m.group(2)), str(p)))
    except Exception:
        pass
    return out

def _same_runtime_version_as_current(pyexe: str | None) -> bool:
    """判断私有解释器的 stdlib zip 是否包含与当前进程相同的主次版本。"""
    if not pyexe or not os.path.exists(pyexe):
        return False
    base = _python_base_from_exe(pyexe)
    cur = (sys.version_info.major, sys.version_info.minor)
    return any((maj, minr) == cur for maj, minr, _ in _stdlib_zip_versions(base))

def _qt_bin_dirs(base: Path) -> list[Path]:
    return [
        base / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin",
        base / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "plugins",
    ]

def _scrub_path_inplace(env: dict | None = None):
    """仅移除 WindowsApps 污染；保留 .venv 与各 Python 安装路径，避免误删当前运行时。"""
    e = env if env is not None else os.environ
    paths = (e.get("PATH") or "").split(";")
    bad_tokens = ("\\WindowsApps\\Python", "Microsoft\\WindowsApps")
    keep = []
    for p in paths:
        q = (p or "").strip()
        if not q:
            continue
        low = q.lower()
        if any(tok.lower() in low for tok in bad_tokens):
            continue
        keep.append(q)
    e["PATH"] = ";".join(keep)

_GUI_DEPS_CHECKED = False
def _try_import_gui() -> bool:
    """尝试导入 GUI 依赖；成功返回 True，不弹窗。"""
    try:
        import importlib
        importlib.invalidate_caches()
        importlib.import_module("PyQt6")
        importlib.import_module("qfluentwidgets")
        # 检查 win32api（pywin32）
        try:
            import win32api as _win32api
            _ = _win32api
        except ImportError:
            return False
        # 触发一次 Qt 核心模块加载，尽早暴露 DLL 问题
        from PyQt6.QtCore import QT_VERSION_STR as _QT_VERSION_STR
        _ = _QT_VERSION_STR
        return True
    except Exception as e:
        print(f"[DEBUG] GUI import failed: {e}")
        return False

def _inject_private_paths(pyexe: str | None):
    """
    注入私有解释器路径：
    - 不同版本：仅注入 Lib、Lib/site-packages 与 Qt bin/plugins
    - 相同版本：额外注入 base、DLLs 与 python*.zip
    """
    if not pyexe or not os.path.exists(pyexe):
        return

    base = _python_base_from_exe(pyexe)
    _scrub_path_inplace()
    same = _same_runtime_version_as_current(pyexe)
    zips = []
    if same:
        zips = [z for (maj, minr, z) in _stdlib_zip_versions(base)
                if (maj, minr) == (sys.version_info.major, sys.version_info.minor)]

    # 只允许注入当前依赖目录，不允许注入其它盘符或历史路径
    cand = [
        str(base / "Lib"),
        str(base / "Lib" / "site-packages"),
        *zips,
    ]
    if same:
        cand = [
            str(base),
            str(base / "DLLs"),
            *cand,
        ]

    # 只保留 src 目录、当前依赖目录及其 site-packages
    src_dir = str(Path(__file__).resolve().parent)
    allowed_prefixes = [src_dir, str(base), str(base / "Lib"), str(base / "Lib" / "site-packages")]
    seen = set()
    newp = []
    for p in cand + list(sys.path):
        if not p:
            continue
        try:
            absp = os.path.abspath(p)
            key = os.path.normcase(absp)
        except Exception:
            continue
        # 只允许 src 目录和当前依赖目录相关路径
        if not any(absp.startswith(prefix) for prefix in allowed_prefixes):
            continue
        if key in seen:
            continue
        seen.add(key)
        newp.append(p)
    sys.path[:] = newp
    try:
        if hasattr(os, "add_dll_directory"):
            if same:
                os.add_dll_directory(str(base))
                dlls = base / "DLLs"
                if dlls.exists():
                    os.add_dll_directory(str(dlls))
            for d in _qt_bin_dirs(base):
                if d.exists():
                    os.add_dll_directory(str(d))
    except Exception:
        pass
    print(f"[DEBUG] 已注入私有解释器路径: {base}  same_ver={same}  zips={zips}")


def _append_private_site_packages(pyexe: str | None):
    '''
    Append private Lib/site-packages to sys.path without overriding bundled Qt runtime.
    Packaged mode only.
    '''
    if not pyexe or not os.path.exists(pyexe):
        return
    try:
        base = _python_base_from_exe(pyexe)
    except Exception:
        return

    for p in (base / "Lib", base / "Lib" / "site-packages"):
        try:
            if p.exists():
                pstr = str(p)
                if pstr not in sys.path:
                    sys.path.append(pstr)
        except Exception:
            pass
    print(f"[INFO] packaged: appended deps path (no Qt override): {base}")

def _block_pyqt6_from_private(pyexe: str | None):
    '''
    Prevent resolving PyQt6 from private site-packages in packaged mode.
    This avoids Qt runtime mixing when private deps also include PyQt6.
    '''
    if not pyexe or not os.path.exists(pyexe):
        return
    try:
        base = _python_base_from_exe(pyexe)
        private_sp = str(base / "Lib" / "site-packages").lower()
    except Exception:
        return

    if not private_sp:
        return

    try:
        import importlib.abc
        import importlib.machinery

        class _BlockPrivatePyQt6(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if not fullname.startswith("PyQt6"):
                    return None
                if fullname in sys.modules or "PyQt6" in sys.modules:
                    return None
                filtered = []
                for p in sys.path:
                    try:
                        if not str(p).lower().startswith(private_sp):
                            filtered.append(p)
                    except Exception:
                        continue
                return importlib.machinery.PathFinder.find_spec(fullname, filtered, target)

        sys.meta_path.insert(0, _BlockPrivatePyQt6())
        print("[INFO] packaged: blocked PyQt6 from private site-packages")
    except Exception as e:
        print(f"[WARN] failed to block PyQt6 from private deps: {e}")


def _setup_qt_dll_dirs(pyexe: str | None = None):
    """
    准确将 PyQt6 的 Qt 运行库加入 DLL 搜索路径与插件搜索路径，并预加载核心 DLL。
    必须在任何 PyQt6/qfluentwidgets 导入之前调用。
    """
    qt6_roots: list[Path] = []

    # 1) 优先按目标解释器推导 site-packages/PyQt6/Qt6
    try:
        if pyexe and os.path.exists(pyexe):
            p = Path(pyexe)
            base = p.parent.parent if p.parent.name.lower() == "scripts" else p.parent
            sp = base / "Lib" / "site-packages"
            q = sp / "PyQt6" / "Qt6"
            if q.exists():
                qt6_roots.append(q)
    except Exception:
        pass

    # 2) 兜底：从当前 sys.path 扫描所有 site-packages
    try:
        for entry in list(sys.path):
            try:
                sp = Path(entry)
                if sp.name.lower() == "site-packages":
                    q = sp / "PyQt6" / "Qt6"
                    if q.exists():
                        qt6_roots.append(q)
            except Exception:
                continue
    except Exception:
        pass
    # 去重
    uniq = []
    seen = set()
    for q in qt6_roots:
        key = str(q.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(q)
    # 注入 DLL/插件目录，并预加载必要 DLL
    for q in uniq:
        bin_dir = q / "bin"
        plug_dir = q / "plugins"

        # 先放入 PATH，避免某些第三方加载路径只认 PATH
        try:
            if bin_dir.exists():
                old = os.environ.get("PATH", "")
                if str(bin_dir) not in old:
                    os.environ["PATH"] = str(bin_dir) + ";" + old
        except Exception:
            pass
        # 使用 Win10+ 的安全方式加入 DLL 搜索路径
        try:
            if hasattr(os, "add_dll_directory") and bin_dir.exists():
                os.add_dll_directory(str(bin_dir))
        except Exception:
            pass

        # 设置 Qt 插件目录（平台插件、图像插件等）
        try:
            if plug_dir.exists():
                os.environ.setdefault("QT_PLUGIN_PATH", str(plug_dir))
                os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plug_dir / "platforms"))
        except Exception:
            pass
        # 预加载关键 Qt DLL（减少“找不到指定的程序”概率）
        try:
            if bin_dir.exists():
                for dll in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Xml.dll"):
                    f = bin_dir / dll
                    if f.exists():
                        ctypes.WinDLL(str(f))
        except Exception:
            pass
def _allowed_roots_for(pyexe: str | None, base_dir: Path) -> list[str]:
    """
    允许保留的路径前缀。
    - 总是保留：项目根、当前运行时标准库根（含 pythonXY.zip）
    - 私有解释器：总是保留 Lib、Lib/site-packages；仅在版本一致时保留 base、DLLs、python*.zip
    """
    roots: set[str] = set()

    # 项目源代码目录
    try:
        src_dir = Path(__file__).resolve().parent
        roots.add(str(src_dir))
        roots.add(str(src_dir.parent))
    except Exception:
        pass
    def add_private_base(b: Path, allow_core: bool):
        if not b.exists():
            return
        # 始终允许纯 Python 包
        roots.update({
            str(b / "Lib"),
            str(b / "Lib" / "site-packages"),
        })
        # 版本一致时再允许核心与 DLLs、zip
        if allow_core:
            roots.update({
                str(b),
                str(b / "DLLs"),
            })
            try:
                for maj, minr, z in _stdlib_zip_versions(b):
                    if (maj, minr) == (sys.version_info.major, sys.version_info.minor):
                        roots.add(z)
            except Exception:
                pass
    # base_dir 下的常见结构
    for cand in (base_dir / "venv", base_dir / "python_full"):
        # 无法准确判版本时，保守处理：不加入 base/DLLs，只留 Lib 路径
        add_private_base(cand, allow_core=False)

    # 指定解释器的基目录（可精确判断版本）
    try:
        allow_core = _same_runtime_version_as_current(pyexe) if (pyexe and os.path.exists(pyexe)) else False
        if pyexe and os.path.exists(pyexe):
            base = _python_base_from_exe(pyexe)
            add_private_base(base, allow_core=allow_core)
    except Exception:
        pass

    # 永远保留当前运行时的标准库根与 zip
    for r in _current_runtime_roots():
        roots.add(r)
    return list(roots)
def _relaunch_with(pyexe: str):
    """用私有解释器重启；Windows 下隐藏后台窗口，避免终端闪现。"""
    import subprocess
    if not pyexe or not os.path.exists(pyexe):
        print("[ERROR] 无法重启：未找到目标解释器。")
        sys.exit(5)
    env = os.environ.copy()
    env["LATEXSNIPPER_BOOTSTRAPPED"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    _scrub_path_inplace(env)
    env.setdefault("QT_QPA_PLATFORM", "windows")
    argv = [pyexe, os.path.abspath(__file__), *sys.argv[1:]]
    print(f"[INFO] 使用私有解释器重启(子进程): {pyexe}")
    try:
        proc = subprocess.Popen(argv, env=env, creationflags=_win_subprocess_flags())
    except Exception as e:
        print(f"[ERROR] 启动子进程失败: {e}")
        sys.exit(6)
    print(f"[INFO] 私有解释器子进程已启动: pid={getattr(proc, 'pid', None)}")
    sys.exit(0)

def _native_message_box(title: str, text: str, flags: int = 0x00000040 | 0x00000004 | 0x00040000) -> int:
    """
    使用 Win32 原生 MessageBox（无 PyQt6 也可用）。
    返回值：6=Yes, 7=No。失败时返回 7。
    """
    try:
        import ctypes
        MessageBoxW = ctypes.windll.user32.MessageBoxW
        return int(MessageBoxW(None, text, title, flags))
    except Exception:
        # 回退到控制台提示
        try:
            print(f"[PROMPT] {title}: {text}")
        except Exception:
            pass
        return 7

def _run_pip_install(pyexe: str, pkgs: list[str]) -> bool:
    """
    使用指定解释器安装依赖；自动尝试多个索引源。
    注意：这里传入的是 pip 包名（例如 PyQt6-Fluent-Widgets），不是导入名。
    """
    import subprocess, os
    if not pyexe or not os.path.exists(pyexe):
        print("[ERROR] 未找到私有解释器，无法安装依赖。")
        return False

    indexes = [
        None,  # 环境默认（可能带 PIP_INDEX_URL）
        "https://pypi.org/simple",
        "https://mirrors.aliyun.com/pypi/simple/",
        "https://pypi.tuna.tsinghua.edu.cn/simple",
    ]
    base_cmd = [pyexe, "-m", "pip", "install", "-U", "--timeout", "35", "--retries", "2"]
    base_env = os.environ.copy()
    base_env.setdefault("PIP_NO_INPUT", "1")

    for idx in indexes:
        env = base_env.copy()
        cmd = base_cmd + pkgs
        if idx:
            cmd += ["-i", idx]
            env.pop("PIP_INDEX_URL", None)  # 避免外部变量干扰
        print(f"[INFO] 开始安装依赖: {' '.join(pkgs)}  index={idx or 'ENV/DEFAULT'}")
        try:
            subprocess.check_call(cmd, env=env, creationflags=_win_subprocess_flags())
            print("[OK] 依赖安装完成。")
            return True
        except Exception as e:
            print(f"[WARN] 该索引安装失败: {e}")
    print("[ERROR] 所有索引均安装失败。")
    return False
def _ensure_gui_deps_or_prompt(pyexe: str | None):
    """
    仅在缺失时弹窗提示安装；已具备则静默返回。
    必须在任何 `from PyQt6 ...` / `from qfluentwidgets ...` 之前调用。
    """
    global _GUI_DEPS_CHECKED
    if _GUI_DEPS_CHECKED:
        return
    _GUI_DEPS_CHECKED = True

    # 先注入路径与 Qt DLL 目录，再尝试导入
    _inject_private_paths(pyexe)
    _setup_qt_dll_dirs(pyexe)
    if _try_import_gui():
        return

    # 检查 win32api 缺失，自动补装 pywin32
    try:
        import win32api as _win32api
        _ = _win32api
    except ImportError:
        print("[INFO] 检测到 win32api 缺失，自动安装 pywin32")
        _run_pip_install(pyexe, ["pywin32"])
        # 安装后重试
        if _try_import_gui():
            print("[OK] pywin32 安装完成，GUI 依赖已就绪。")
            return
    gui_specs = list(STABLE_GUI_PIP_SPECS)
    shown_cmd = (f"{pyexe} -m pip install {' '.join(gui_specs)}"
                 if pyexe else f"python -m pip install {' '.join(gui_specs)}")
    msg = (
        "检测到 GUI 依赖缺失，将尝试安装：\n\n"
        f"{shown_cmd}\n\n"
        "是否继续？"
    )
    ans = _native_message_box("LaTeXSnipper 依赖安装", msg)
    if ans != 6:  # 6=Yes
        print("[WARN] 用户取消安装 GUI 依赖，本次启动将不再提示。")
        return

    if not pyexe or not os.path.exists(pyexe):
        print("[ERROR] 无有效解释器用于安装，取消。")
        return

    ok = _run_pip_install(pyexe, gui_specs)
    if not ok:
        print("[ERROR] 依赖安装失败。")
        return
    # 安装后重试导入
    _inject_private_paths(pyexe)
    _setup_qt_dll_dirs(pyexe)
    if _try_import_gui():
        print("[OK] GUI 依赖安装完成。")
    else:
        print("[ERROR] 安装后仍无法导入，请检查 Qt DLL 路径或重启。")

def _norm_path(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().strip('"').strip("'").strip()


def _win_subprocess_flags() -> int:
    """Windows 子进程窗口策略：后台任务始终隐藏窗口。"""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

def _clean_bad_env():
    """移除/修复坏掉的 LATEXSNIPPER_PYEXE，避免污染后续检测。"""
    val = os.environ.get("LATEXSNIPPER_PYEXE")
    p = _norm_path(val)
    if not p or not os.path.exists(p):
        os.environ.pop("LATEXSNIPPER_PYEXE", None)

def _has_ensurepip_venv(pyexe: str) -> bool:
    try:
        import subprocess
        r = subprocess.run([pyexe, "-c", "import ensurepip, venv;print('ok')"],
                           capture_output=True, text=True, timeout=20, creationflags=_win_subprocess_flags())
        return r.returncode == 0
    except Exception:
        return False

def _find_full_python(base_dir: Path) -> str | None:
    """优先复用安装目录内已有 Python；仅在确实缺失时再安装 python311。"""
    candidate = _find_install_base_python(base_dir)
    if candidate is not None:
        try:
            if candidate.exists() and _has_ensurepip_venv(str(candidate)):
                return str(candidate)
        except Exception:
            pass
        try:
            if candidate.exists():
                return str(candidate)
        except Exception:
            pass
    if getattr(sys, "frozen", False):
        installer = base_dir / "python-3.11.0-amd64.exe"
        if installer.exists():
            if _run_python_installer(installer, base_dir / "python311"):
                candidate = _find_install_base_python(base_dir)
                if candidate is not None and candidate.exists():
                    return str(candidate)
        return None
    for name in ("python3.11.exe", "python.exe", "python3.exe"):
        which = _norm_path(shutil.which(name))
        if which and os.path.exists(which) and _has_ensurepip_venv(which):
            return which
    return None

def _run_python_installer(installer: Path, target_dir: Path) -> bool:
    import subprocess
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        args = [str(installer), "/quiet", "InstallAllUsers=0",
                f"TargetDir={str(target_dir)}",
                "Include_pip=1", "PrependPath=0", "Include_test=0",
                "Include_doc=0", "Include_launcher=0", "SimpleInstall=1"]
        print(f"[INFO] 正在静默安装 Python 到: {target_dir}")
        r = subprocess.run(args, timeout=600, creationflags=_win_subprocess_flags())
        if r.returncode != 0:
            print(f"[WARN] 静默安装返回码: {r.returncode}")
            return False
        return True
    except Exception as e:
        print(f"[WARN] 启动安装器失败: {e}")
        return False

def ensure_full_python_or_prompt(base_dir: Path) -> str | None:
    if getattr(sys, "frozen", False):
        py = _find_full_python(base_dir)
        if py:
            # 打包模式下区分 Python 来源，避免把外部私有环境误标为“内置”。
            py_norm = os.path.normcase(os.path.abspath(py))
            bundled_norm = os.path.normcase(os.path.abspath(str(base_dir)))
            if py_norm.startswith(bundled_norm):
                print(f"[INFO] (打包模式) 使用依赖目录内 Python: {py}")
            else:
                print(f"[INFO] (打包模式) 使用外部私有 Python: {py}")
            return py
        print("[INFO] (打包模式) 依赖目录内未检测到可用 Python，先使用内置运行时启动依赖向导。")
        return sys.executable
    # 开发模式：保留原有多路径查找和安装逻辑
    py = _find_full_python(base_dir)
    if py:
        print(f"[INFO] 使用依赖目录 Python: {py}")
        return py

    # 安装器兜底
    installer: Path | None = None
    for root in (base_dir, Path(__file__).resolve().parent, Path(os.getcwd())):
        try:
            cands = list(Path(root).glob("python-3.11*.exe")) + list(Path(root).glob("python311*.exe"))
            if cands:
                installer = cands[0]
                break
        except Exception:
            pass

    if installer:
        target_dir = base_dir / "python311"
        if _run_python_installer(installer, target_dir):
            py = _find_full_python(base_dir)
            if py:
                print(f"[INFO] Python 3.11 已安装到: {py}")
                return py

    print("[ERROR] 未找到可用的 Python 3.11；请将安装器放入安装目录_internal下或手动安装后重试。")
    return None

_ensure_startup_splash("加载依赖向导模块...")
_ensure_startup_splash("加载设置模块...")


def _load_startup_modules():
    from deps_bootstrap import clear_deps_state, custom_warning_dialog
    from settings_window import SettingsWindow

    return custom_warning_dialog, clear_deps_state, SettingsWindow


custom_warning_dialog, clear_deps_state, SettingsWindow = _load_startup_modules()

# 1) 解析/选择安装目录
_ensure_startup_splash("定位依赖目录...")
INSTALL_BASE_DIR = resolve_install_base_dir()

# 3) 打包模式下：检查是否需要重定向到私有解释器
if _is_packaged_mode():
    py_exe_path = _find_install_base_python(INSTALL_BASE_DIR)
    py_exe = py_exe_path if py_exe_path is not None else (INSTALL_BASE_DIR / "python311" / "python.exe")

    if py_exe.exists():
        if os.environ.get("LATEXSNIPPER_FORCE_PRIVATE_PY") == "1":
            # redirect only when explicitly enabled
            if os.environ.get("LATEXSNIPPER_INNER_PY") != "1":
                print(f"[INFO] packaged: redirect to private python {py_exe}")
                import subprocess
                env = os.environ.copy()
                env["LATEXSNIPPER_INNER_PY"] = "1"
                # 终端显示偏好：优先环境变量，其次配置文件。
                raw_pref = (os.environ.get("LATEXSNIPPER_SHOW_CONSOLE", "") or "").strip().lower()
                if raw_pref in ("1", "true", "yes", "on", "0", "false", "no", "off"):
                    show_console = raw_pref in ("1", "true", "yes", "on")
                else:
                    show_console = False
                    try:
                        cfg_path = _config_path()
                        if cfg_path.exists():
                            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                            raw = cfg_data.get("show_startup_console", False) if isinstance(cfg_data, dict) else False
                            if isinstance(raw, bool):
                                show_console = raw
                            elif isinstance(raw, (int, float)):
                                show_console = bool(raw)
                            elif isinstance(raw, str):
                                show_console = raw.strip().lower() in ("1", "true", "yes", "on")
                    except Exception:
                        pass
                env["LATEXSNIPPER_SHOW_CONSOLE"] = "1" if show_console else "0"
                # 统一优先 pythonw.exe，由 open_debug_console 决定是否分配日志终端。
                # 这样可避免 python.exe 自带控制台在启动瞬间闪窗。
                run_py = py_exe
                pyw = py_exe.parent / "pythonw.exe"
                if pyw.exists():
                    run_py = pyw
                argv = [str(run_py), os.path.abspath(__file__), *sys.argv[1:]]
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if (os.name == "nt") else 0
                subprocess.Popen(argv, env=env, creationflags=creationflags)
                sys.exit(0)
            else:
                print("[INFO] packaged: already in private python")
        else:
            print("[INFO] packaged: keep bundled runtime, mount deps dir")
    else:
        print(f"[WARN] packaged: private python not found: {py_exe}, keep bundled runtime")

BASE_DIR = Path(INSTALL_BASE_DIR)
_clean_bad_env()

_ensure_startup_splash("检查 Python 运行时...")
TARGET_PY = ensure_full_python_or_prompt(BASE_DIR)
if not TARGET_PY:
    print("[ERROR] 未找到可用的完整 Python 3.11。")
    sys.exit(2)

# 固定环境，禁止外部干扰
os.environ["LATEXSNIPPER_PYEXE"] = TARGET_PY
os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = str(BASE_DIR)
os.environ["LATEXSNIPPER_DEPS_DIR"] = str(BASE_DIR)
os.environ.setdefault("PYTHONNOUSERSITE", "1")
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)
os.environ.pop("MATHCRAFT_HOME", None)

# 5) IDE 模式下的路径注入（非打包模式）
if not _in_ide() and not _is_packaged_mode():
    if not _same_exe(sys.executable, TARGET_PY):
        _relaunch_with(TARGET_PY)
elif _in_ide():
    print("[INFO] IDE 中运行，保持当前解释器，但使用私有依赖路径")

# 只有在非 BOOTSTRAPPED 模式下才修改 sys.path
if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1":
    _ensure_startup_splash("挂载私有依赖环境...")
    _sanitize_sys_path(TARGET_PY, BASE_DIR)
    if _is_packaged_mode():
        _append_private_site_packages(TARGET_PY)
        _block_pyqt6_from_private(TARGET_PY)
    else:
        _ensure_startup_splash("检查 GUI 依赖版本...")
        _ensure_gui_deps_or_prompt(TARGET_PY)

    # 5) Startup deps check: show wizard only when required layers are missing.
    # Pass BASE_DIR to avoid repeated path prompts.
    # 若当前进程是“重启后打开依赖向导”场景，则跳过这里的预检查，
    # 由 __main__ 分支统一执行一次交互式校验，避免重复日志与重复验证。
    _open_wizard_env = (os.environ.get("LATEXSNIPPER_OPEN_WIZARD", "") == "1")
    if _open_wizard_env:
        print("[INFO] 依赖向导模式：跳过启动预检查，由向导统一验证。")
    else:
        import importlib as _imp
        _ensure_startup_splash("检查已安装功能层...")
        _db = _imp.import_module("deps_bootstrap")
        try:
            _ok = _db.ensure_deps(
                prompt_ui=True,
                always_show_ui=False,
                require_layers=("BASIC", "CORE"),
                deps_dir=str(BASE_DIR),
                before_show_ui=_hide_startup_splash_for_modal,
                after_force_enter=_mark_startup_force_entered,
            )
            if _ok:
                os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
                if _deps_force_entered(_db):
                    _mark_startup_force_entered()
        except Exception as e:
            print(f"[WARN] deps wizard failed: {e}")

def ensure_deps(*args, **kwargs):
    # 已就绪则直接返回 True，避免再次尝试 venv/构建 UI
    # 但从设置页进入时必须执行校验，不能被短路
    from_settings = bool(kwargs.get("from_settings", False))
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not from_settings:
        return True
    # 真需要时再按需引入并调用（通常用不到）
    import deps_bootstrap as _db
    prompt_ui = bool(kwargs.get("prompt_ui", True))
    if prompt_ui:
        kwargs.setdefault("before_show_ui", _hide_startup_splash_for_modal)
        kwargs.setdefault("after_force_enter", _mark_startup_force_entered)
    ok = _db.ensure_deps(*args, **kwargs)
    if ok:
        os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
        if _deps_force_entered(_db):
            _mark_startup_force_entered()
    return ok


def show_dependency_wizard(always_show_ui=False):
    # 默认不展示；仅在明确需要时才展示（always_show_ui=True）
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not always_show_ui:
        return True
    try:
        import deps_bootstrap as _db
        # 依赖向导统一收口到 ensure_deps，一处负责校验与展示。
        ok = _db.ensure_deps(
            always_show_ui=always_show_ui,
            before_show_ui=_hide_startup_splash_for_modal,
            after_force_enter=_mark_startup_force_entered,
        )
        if ok:
            os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
            if _deps_force_entered(_db):
                _mark_startup_force_entered()
        return ok
    except Exception as e:
        print(f"[WARN] 依赖向导不可用: {e}")
        return False
# 修正路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


def _load_runtime_modules():
    import pyperclip as _pyperclip
    from PIL import Image as _Image
    from backend.external_model import (
        ExternalModelPdfWorker,
        ExternalModelWorker,
        load_config_from_mapping,
    )
    from backend.latex_renderer import get_latex_renderer, init_latex_settings
    from backend.model import ModelWrapper, classify_mathcraft_failure
    from backend.model_factory import create_model_wrapper
    from backend.platform import PlatformCapabilityRegistry, ScreenshotConfig, TrayMenuHandlers
    from editor.workbench_window import WorkbenchWindow
    from handwriting import HandwritingWindow
    from handwriting.bilingual_pdf_window import BilingualPdfWindow
    from qfluentwidgets import (
        Action,
        BodyLabel,
        FluentIcon,
        InfoBar,
        InfoBarPosition,
        MessageBox,
        PrimaryPushButton,
        PrimaryToolButton,
        PushButton,
        RoundMenu,
    )

    return (
        Action,
        BilingualPdfWindow,
        BodyLabel,
        ExternalModelPdfWorker,
        ExternalModelWorker,
        FluentIcon,
        HandwritingWindow,
        _Image,
        InfoBar,
        InfoBarPosition,
        MessageBox,
        ModelWrapper,
        PlatformCapabilityRegistry,
        PrimaryPushButton,
        PrimaryToolButton,
        PushButton,
        RoundMenu,
        ScreenshotConfig,
        TrayMenuHandlers,
        WorkbenchWindow,
        classify_mathcraft_failure,
        create_model_wrapper,
        get_latex_renderer,
        init_latex_settings,
        load_config_from_mapping,
        _pyperclip,
    )


(
    Action,
    BilingualPdfWindow,
    BodyLabel,
    ExternalModelPdfWorker,
    ExternalModelWorker,
    FluentIcon,
    HandwritingWindow,
    Image,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    ModelWrapper,
    PlatformCapabilityRegistry,
    PrimaryPushButton,
    PrimaryToolButton,
    PushButton,
    RoundMenu,
    ScreenshotConfig,
    TrayMenuHandlers,
    WorkbenchWindow,
    classify_mathcraft_failure,
    create_model_wrapper,
    get_latex_renderer,
    init_latex_settings,
    load_config_from_mapping,
    pyperclip,
) = _load_runtime_modules()


def get_app_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).parent

APP_DIR = get_app_dir()

def _apply_close_only_window_flags(win):
    """提示/工具窗口统一为仅保留右上角关闭按钮。"""
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMaximizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    win.setWindowFlags(flags)

def _apply_no_minimize_window_flags(win):
    """工具窗口保留最大化/关闭，去掉最小化按钮。"""
    flags = (
        win.windowFlags()
        | Qt.WindowType.CustomizeWindowHint
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMaximizeButtonHint
    )
    flags = (
        flags
        & ~Qt.WindowType.WindowMinimizeButtonHint
        & ~Qt.WindowType.WindowMinMaxButtonsHint
        & ~Qt.WindowType.WindowContextHelpButtonHint
    )
    flags |= Qt.WindowType.WindowMaximizeButtonHint
    win.setWindowFlags(flags)

def _show_formula_rename_dialog(parent, current_name: str = "", title: str = "重命名公式",
                                prompt: str = "输入公式名称（留空则清除名称）："):
    """统一的公式重命名弹窗：仅保留右上角关闭按钮，固定尺寸。"""
    from PyQt6.QtWidgets import QLineEdit

    dlg = QDialog(parent)
    _apply_close_only_window_flags(dlg)
    dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
    dlg.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel(prompt))

    edit = QLineEdit(dlg)
    edit.setText(current_name or "")
    edit.selectAll()
    edit.setClearButtonEnabled(True)
    lay.addWidget(edit)

    btn_row = QHBoxLayout()
    btn_ok = QPushButton("OK", dlg)
    btn_cancel = QPushButton("Cancel", dlg)
    btn_ok.clicked.connect(dlg.accept)
    btn_cancel.clicked.connect(dlg.reject)
    edit.returnPressed.connect(dlg.accept)
    btn_row.addWidget(btn_ok)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)

    dlg.adjustSize()
    dlg.setFixedSize(max(340, dlg.width()), dlg.height())
    _apply_app_window_icon(dlg)
    QTimer.singleShot(0, edit.setFocus)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return "", False
    return edit.text().strip(), True

def _exec_close_only_message_box(
    parent,
    title: str,
    text: str,
    icon=QMessageBox.Icon.Information,
    buttons=QMessageBox.StandardButton.Ok,
    default_button=None,
    informative_text: str | None = None,
):
    msg = QMessageBox(parent)
    _apply_app_window_icon(msg)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStandardButtons(buttons)
    if default_button is not None:
        msg.setDefaultButton(default_button)
    if informative_text:
        msg.setInformativeText(informative_text)
    _apply_close_only_window_flags(msg)
    return QMessageBox.StandardButton(msg.exec())

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(DEPS_DIR, exist_ok=True)
os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("ORT_DISABLE_AZURE", "1")

def _ensure_std_streams():
    """防御式恢复 stdout/stderr：仅在缺失/不可写/已关闭时兜底，不覆盖正常对象。"""

    def _is_bad(f):
        if f is None:
            return True
        if not hasattr(f, "write"):
            return True
        if getattr(f, "closed", False):
            return True
        # 对于 TeeWriter，只检查其标志
        if isinstance(f, TeeWriter):
            return f._closed
        return False

    def _try_restore():
        """尝试恢复流"""
        # 1) 优先恢复到原始 __stdout__ / __stderr__
        if _is_bad(getattr(sys, "stdout", None)):
            if hasattr(sys, "__stdout__") and sys.__stdout__ is not None and not getattr(sys.__stdout__, "closed", False):
                sys.stdout = sys.__stdout__

        if _is_bad(getattr(sys, "stderr", None)):
            if hasattr(sys, "__stderr__") and sys.__stderr__ is not None and not getattr(sys.__stderr__, "closed", False):
                sys.stderr = sys.__stderr__

        # 2) 若仍为空/不可写/已关闭，兜底到空设备
        if _is_bad(getattr(sys, "stdout", None)):
            try:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                pass

        if _is_bad(getattr(sys, "stderr", None)):
            # 复用 stdout 或创建新的
            if not _is_bad(getattr(sys, "stdout", None)):
                sys.stderr = sys.stdout
            else:
                try:
                    sys.stderr = open(os.devnull, "w", encoding="utf-8")
                except Exception:
                    pass

    _try_restore()

# 在程序启动早期调用一次
_ensure_std_streams()
try:
    from PyQt6 import sip  # PyQt6 bundled sip, preferred for type resolution
except Exception:
    try:
        import sip  # pyright: ignore[reportMissingImports]  # fallback for top-level sip package
    except Exception:
        sip = None
def _action_btn_style() -> str:
    if _is_dark_ui():
        return (
            "PrimaryPushButton{background:#2f6ea8;color:#f5f7fb;border:1px solid #4d8dca;"
            "border-radius:4px;padding:4px 10px;font-size:12px;}"
            "PrimaryPushButton:hover{background:#3e82c3;}"
            "PrimaryPushButton:pressed{background:#245a8d;}"
            "PrimaryPushButton:disabled{background:#2b3440;color:#7f8a98;border:1px solid #465162;}"
        )
    return (
        "PrimaryPushButton{background:#3daee9;color:#ffffff;border:1px solid #2b94cb;"
        "border-radius:4px;padding:4px 10px;font-size:12px;}"
        "PrimaryPushButton:hover{background:#5dbff2;}"
        "PrimaryPushButton:pressed{background:#319fd9;}"
        "PrimaryPushButton:disabled{background:#eef2f6;color:#8a94a3;border:1px solid #d0d7de;}"
    )
# 样式常量
HOVER_STYLE_BASE = "QWidget{background:#fefefe;border:1px solid #cfcfcf;border-radius:5px;padding:6px;}"
HOVER_STYLE_ACTIVE = "QWidget{background:#ffffff;border:1px solid #999;border-radius:5px;padding:6px;}"

MAX_HISTORY = 200
ENABLE_ROW_ANIMATION = False    # 历史记录行动画开关
SAFE_MINIMAL = True          # 第一步：最小化测试开关
PLATFORM_DISABLE_GLOBAL_HOTKEY = False  # 若为 True 不注册全局热键
DEFAULT_FAVORITES_NAME = "favorites.json"
DEFAULT_HISTORY_NAME = "history.json"


def _default_user_data_file(file_name: str) -> Path:
    p = _app_state_dir() / file_name
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _resolve_user_data_file(cfg: "ConfigManager", key: str, default_name: str) -> str:
    configured = str(cfg.get(key, "") or "").strip()
    if configured:
        return str(Path(configured).expanduser())
    target = _default_user_data_file(default_name)
    cfg.set(key, str(target))
    return str(target)

# ---------------- MathJax 实时渲染模板 ----------------
# MathJax 3.2.2 是稳定版本，v4.0+ 可能有兼容性问题
MATHJAX_CDN_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
# 备用CDN（如主CDN不可用）
MATHJAX_CDN_URL_BACKUP = "https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js"


def _is_dark_ui() -> bool:
    try:
        import qfluentwidgets as qfw
        fn = getattr(qfw, "isDarkTheme", None)
        if callable(fn):
            return bool(fn())
    except Exception:
        pass
    app = QApplication.instance()
    if app is None:
        return False
    c = app.palette().window().color()
    return ((c.red() + c.green() + c.blue()) / 3.0) < 128


def _preview_theme_tokens() -> dict:
    if _is_dark_ui():
        return {
            "body_bg": "#14171d",
            "body_text": "#e8ebf0",
            "latex_formula_text": "#ffffff",
            "panel_bg": "#1d222b",
            "label_text": "#8ec5ff",
            "label_bg": "#1e334a",
            "error_text": "#ff9a9a",
            "error_bg": "#4a1f27",
            "muted_text": "#95a0af",
            "pre_bg": "#342b20",
            "border_formula": "#63a5ff",
            "border_text": "#72d68e",
            "border_table": "#ffb35c",
            "border_mixed": "#d8a4ff",
            "badge_formula_bg": "#23374d",
            "badge_formula_text": "#9fd1ff",
            "badge_text_bg": "#213328",
            "badge_text_text": "#88d5a3",
            "badge_table_bg": "#3a2a18",
            "badge_table_text": "#ffbf7a",
            "badge_mixed_bg": "#35253f",
            "badge_mixed_text": "#e4bcff",
            "table_border": "#3e4958",
            "th_bg": "#27303b",
        }
    return {
        "body_bg": "#fafafa",
        "body_text": "#1f2328",
        "latex_formula_text": "#1f2328",
        "panel_bg": "#f8f9fa",
        "label_text": "#1976d2",
        "label_bg": "#e3f2fd",
        "error_text": "#d32f2f",
        "error_bg": "#ffebee",
        "muted_text": "#888888",
        "pre_bg": "#fff3e0",
        "border_formula": "#1976d2",
        "border_text": "#43a047",
        "border_table": "#f57c00",
        "border_mixed": "#7b1fa2",
        "badge_formula_bg": "#e3f2fd",
        "badge_formula_text": "#1976d2",
        "badge_text_bg": "#e8f5e9",
        "badge_text_text": "#43a047",
        "badge_table_bg": "#fff3e0",
        "badge_table_text": "#f57c00",
        "badge_mixed_bg": "#f3e5f5",
        "badge_mixed_text": "#7b1fa2",
        "table_border": "#dddddd",
        "th_bg": "#f2f2f2",
    }


def _formula_label_theme_tokens() -> dict:
    if _is_dark_ui():
        return {
            "text": "#d7dee9",
            "tooltip_bg": "#27303b",
            "tooltip_text": "#eef3f8",
            "tooltip_border": "#4d5a6b",
        }
    return {
        "text": "#333333",
        "tooltip_bg": "#ffffff",
        "tooltip_text": "#1f2328",
        "tooltip_border": "#cfd6df",
    }


def _dialog_theme_tokens() -> dict:
    if _is_dark_ui():
        return {
            "window_bg": "#1b1f27",
            "panel_bg": "#232934",
            "text": "#e7ebf0",
            "muted": "#a9b3bf",
            "border": "#465162",
            "accent": "#8ec5ff",
        }
    return {
        "window_bg": "#ffffff",
        "panel_bg": "#f7f9fc",
        "text": "#222222",
        "muted": "#666666",
        "border": "#d0d7de",
        "accent": "#1976d2",
    }


# 支持 SVG 渲染的简化模板（不需要 MathJax 脚本）
MATHJAX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<!-- 【关键】允许本地文件加载和不安全内容（桌面应用必需） -->
<meta http-equiv="Content-Security-Policy" content="default-src * 'unsafe-inline' 'unsafe-eval' data: blob: file:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline';">
<style>
body {
  font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
  padding: 12px;
  margin: 0;
    background: __BODY_BG__;
    color: __BODY_TEXT__;
  font-size: 18px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.math-container {
  overflow-x: auto;
  padding: 0;
  text-align: center;
  margin-bottom: 12px;
  position: relative;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.math-container:last-child {
  margin-bottom: 0;
}
.formula-label {
  position: absolute;
  top: 4px;
  left: 8px;
  font-size: 12px;
    color: __LABEL_TEXT__;
    background: __LABEL_BG__;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.formula-content {
  display: inline-block;
  max-width: 100%;
  overflow: auto;
  padding: 0;
  margin: 0;
  font-size: 20px;
}
.error-text {
    color: __ERROR_TEXT__;
  font-size: 12px;
  padding: 8px;
    background: __ERROR_BG__;
  border-radius: 4px;
}
</style>
<!-- MathJax 配置 -->
<script>
  window.MathJax = {
    tex: {
      inlineMath: [['$', '$'], ['\\(', '\\)']],
      displayMath: [['$$', '$$'], ['\\[', '\\]']],
      processEscapes: true
    },
    svg: {
      fontCache: 'global',
            scale: 1.15
    },
    options: {
      enableMenu: false,
      skipHtmlTags: [],
      ignoreHtmlClass: [],
      processHtmlClass: []
    }
  };
</script>
</head>
<body>
__FORMULAS__
<!-- MathJax 加载：优先本地，失败则使用 CDN -->
<script>
(function() {
  var shouldLogLocalFallback = __LOG_MATHJAX_LOCAL_FALLBACK__;
  // 尝试本地加载
  var localScript = 'tex-mml-chtml.js';
  var cdnUrls = [
    'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js',
    'https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js'
  ];
  
  var script = document.createElement('script');
  script.type = 'text/javascript';
  script.async = true;
  
  // 本地加载失败时使用 CDN
  script.onerror = function() {
    if (shouldLogLocalFallback) {
      console.warn('[MathJax] 本地加载失败，尝试使用 CDN...');
    }
    var cdnScript = document.createElement('script');
    cdnScript.src = cdnUrls[0];
    cdnScript.type = 'text/javascript';
    cdnScript.async = true;
    document.body.appendChild(cdnScript);
  };
  
  script.src = localScript;
  document.body.appendChild(script);
})();
</script>
</body>
</html>
"""

_MATHJAX_LOGGED_KEYS = set()


def _get_mathjax_base_url():
    """获取 MathJax 的 base URL (用于 setHtml)
    
    这个函数必须返回一个指向 es5 目录的 file:// URL，
    这样 tex-mml-chtml.js 才能被正确加载。
    
    支持开发模式和 PyInstaller 打包后的两种运行环境。
    """
    from PyQt6.QtCore import QUrl
    from pathlib import Path
    import sys
    
    try:
        # 首先检查当前选择的渲染模式
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                # 如果选择了 CDN MathJax，返回 CDN URL
                if mode == "mathjax_cdn":
                    if "cdn" not in _MATHJAX_LOGGED_KEYS:
                        print("[MathJax] 使用 CDN MathJax")
                        _MATHJAX_LOGGED_KEYS.add("cdn")
                    cdn_url = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/"
                    return QUrl(cdn_url)
                # LaTeX 模式下主窗口/结果窗口仍可能包含 MathJax 内容（如混合文本、回退渲染），
                # 这里继续返回本地 base_url，避免空 base 触发 CDN 回退。
                elif mode and mode.startswith("latex_"):
                    mode_key = f"latex:{mode}"
                    if mode_key not in _MATHJAX_LOGGED_KEYS:
                        print(f"[MathJax] LaTeX 模式下仍使用本地 MathJax base: {mode}")
                        _MATHJAX_LOGGED_KEYS.add(mode_key)
                    # continue: resolve local MathJax base URL below
        except Exception as e:
            print(f"[WARN] 获取渲染模式失败: {e}")
        
        # 否则使用本地 MathJax
        # 第1步：确定 APP_DIR
        actual_app_dir = None
        
        # 优先使用全局 APP_DIR（已初始化的情况）
        if APP_DIR and str(APP_DIR).strip():
            actual_app_dir = Path(APP_DIR)
        
        mathjax_source_desc = "本地资源"

        # 如果 APP_DIR 为空或不可用，尝试其他方法
        if not actual_app_dir or not str(actual_app_dir).strip():
            # 打包模式检查：sys.frozen 表示 PyInstaller 打包
            if getattr(sys, 'frozen', False):
                # 打包后：exe 所在目录的 _internal 或同级 src
                exe_dir = Path(sys.executable).parent
                # 尝试 _internal/assets (PyInstaller --onedir)
                if (exe_dir / "_internal" / "assets").exists():
                    actual_app_dir = exe_dir / "_internal"
                    mathjax_source_desc = "_internal"
                # 尝试 assets (PyInstaller --onefile 解包目录)
                elif (exe_dir / "assets").exists():
                    actual_app_dir = exe_dir
                    mathjax_source_desc = "exe 同级"
                else:
                    # 最后尝试：还原到 exe 目录往上查找
                    parent = exe_dir.parent
                    if (parent / "src" / "assets").exists():
                        actual_app_dir = parent / "src"
                        mathjax_source_desc = "父目录 src"
            else:
                # 开发模式：使用当前脚本所在目录
                actual_app_dir = Path(__file__).parent
                mathjax_source_desc = "__file__"
        
        if not actual_app_dir:
            actual_app_dir = Path(APP_DIR) if APP_DIR else Path.cwd()
        
        # 第2步：检查 MathJax es5 目录
        es5_dir = actual_app_dir / "assets" / "MathJax-3.2.2" / "es5"
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        
        if not tex_chtml.exists():
            print(f"[WARN] MathJax 文件缺失: {tex_chtml}")
        
        # 第3步：生成 file:// URL
        # 在 Windows 上需要正确处理路径分隔符
        # QUrl.fromLocalFile 需要规范化路径
        url_path = str(es5_dir).replace("\\", "/")  # 转换为前向斜杠
        if not url_path.endswith("/"):
            url_path += "/"
        
        # 使用 QUrl.fromLocalFile() 
        # 注意：QUrl.fromLocalFile() 自动处理 file:// 前缀
        url = QUrl.fromLocalFile(str(es5_dir) + "/")
        url_str = url.toString()
        
        if not url_str.startswith("file:///"):
            print(f"[ERROR] URL 格式异常，应以 file:/// 开头: {url_str}")
        else:
            local_key = f"local:{mathjax_source_desc}:{url_str}"
            if local_key not in _MATHJAX_LOGGED_KEYS:
                label = "使用本地资源" if mathjax_source_desc == "本地资源" else f"使用本地资源({mathjax_source_desc})"
                print(f"[MathJax] {label}: {url_str}")
                _MATHJAX_LOGGED_KEYS.add(local_key)
        
        return url
        
    except Exception as e:
        print(f"[ERROR] _get_mathjax_base_url 异常: {e}")
        import traceback
        traceback.print_exc()
        # 返回临时路径作为后备方案
        return QUrl.fromLocalFile("/")

def latex_to_svg(latex: str) -> str:
    """将 LaTeX 公式转换为 SVG 字符串（使用 matplotlib）
    
    Args:
        latex: LaTeX 公式字符串，例如 "\\frac{1}{2}"
        
    Returns:
        SVG 字符串，如果转换失败返回原始 LaTeX 文本
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # 使用无头后端
        import matplotlib.pyplot as plt
        from io import BytesIO
        
        # 创建图形并渲染公式
        fig, ax = plt.subplots(figsize=(8, 1), dpi=150)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        # 使用 mathtext 渲染公式
        ax.text(0.5, 0.5, f'${latex}$', ha='center', va='center', 
            fontsize=16, transform=ax.transAxes)
        
        # 保存为 SVG
        svg_buffer = BytesIO()
        plt.savefig(svg_buffer, format='svg', bbox_inches='tight', pad_inches=0.1, 
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        
        # 获取 SVG 内容
        svg_buffer.seek(0)
        svg_str = svg_buffer.getvalue().decode('utf-8')
        
        # 清理 SVG（移除 XML 声明和样式）
        svg_str = svg_str.replace('<?xml version', '<!-- SVG from matplotlib -->\n<?xml version')
        
        return svg_str
        
    except Exception as e:
        print(f"[ERROR] LaTeX to SVG conversion failed: {e}")
        raise

_MATHML_SUM = "\u2211"
_MATHML_INF = "\u221E"

def _strip_math_delimiters(latex: str) -> str:
    t = (latex or "").strip()
    if len(t) >= 4 and t.startswith("$$") and t.endswith("$$"):
        return t[2:-2].strip()
    if len(t) >= 2 and t.startswith("$") and t.endswith("$"):
        return t[1:-1].strip()
    return t

def _normalize_latex_for_export(latex: str) -> str:
    """规范化导出用 LaTeX：简化单字符上下标、补充必要空格。"""
    t = _strip_math_delimiters(latex)
    if not t:
        return ""
    t = re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", t)
    t = re.sub(r"_\{([A-Za-z0-9])\}", r"_\1", t)
    t = t.replace(":=", " := ")
    t = re.sub(r"(?<=\S)(\\(?:sum))", r" \1", t)
    t = re.sub(r"(?<=\S)(\\(?:frac|dfrac|tfrac))", r" \1", t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t

def _latex_inline(latex: str) -> str:
    return f"${latex}$"

def _latex_display(latex: str) -> str:
    return f"\\[\n{latex}\n\\]"

def _latex_equation(latex: str) -> str:
    return f"\\begin{{equation}}\n{latex}\n\\end{{equation}}"

def _ensure_mathml_block(mathml: str) -> str:
    if not mathml:
        return mathml
    m = re.search(r"<math\b([^>]*)>", mathml)
    if not m:
        return mathml
    attrs = m.group(1) or ""
    if re.search(r"\bdisplay\s*=", attrs):
        return mathml
    sep = " " if attrs and not attrs.endswith(" ") else ""
    new_tag = f"<math{attrs}{sep}display=\"block\">"
    return mathml[:m.start()] + new_tag + mathml[m.end():]

def _mathml_standardize(mathml: str) -> str:
    """标准 MathML：保证 display=block，统一无穷符号样式。"""
    mathml = _ensure_mathml_block(mathml)
    # 合并 := 到单个 <mo>
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        '<mi mathvariant="normal">&#x221E;</mi>',
        mathml,
    )
    mathml = mathml.replace(_MATHML_SUM, "&#x2211;").replace(_MATHML_INF, "&#x221E;")
    return mathml

def _mathml_htmlize(mathml: str) -> str:
    """HTML 用 MathML：display=block，sum 增加 data-mjx-texclass，符号转 Unicode。"""
    mathml = _ensure_mathml_block(mathml)
    # 合并 := 到单个 <mo>
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        f'<mi mathvariant="normal">{_MATHML_INF}</mi>',
        mathml,
    )

    def _sum_repl(match):
        attrs = match.group(1) or ""
        if "data-mjx-texclass" in attrs:
            return f"<mo{attrs}>{_MATHML_SUM}</mo>"
        sep = "" if not attrs or attrs.endswith(" ") else " "
        return f"<mo{attrs}{sep}data-mjx-texclass=\"OP\">{_MATHML_SUM}</mo>"

    mathml = re.sub(
        r"<mo([^>]*)>\s*(?:&#x2211;|&#X2211;|%s)\s*</mo>" % _MATHML_SUM,
        _sum_repl,
        mathml,
        count=1,
    )
    mathml = mathml.replace("&#x2211;", _MATHML_SUM).replace("&#X2211;", _MATHML_SUM)
    mathml = mathml.replace("&#x221E;", _MATHML_INF).replace("&#X221E;", _MATHML_INF)
    return mathml

def _mathml_to_html_fragment(mathml: str) -> str:
    """将 MathML 包装为可直接嵌入网页的 HTML 片段。"""
    html_mathml = _mathml_htmlize(mathml)
    return f'<span class="latexsnipper-math" data-format="mathml">{html_mathml}</span>'

def _mathml_with_prefix(mathml: str, prefix: str) -> str:
    """将 MathML 标签统一加命名空间前缀，如 mml:, m:, attr:。"""
    if not mathml:
        return mathml
    mathml = _ensure_mathml_block(mathml)

    def _root_repl(match):
        attrs = match.group(1) or ""
        attrs = re.sub(r'\s+xmlns="[^"]*"', "", attrs)
        if f"xmlns:{prefix}=" not in attrs:
            sep = " " if attrs and not attrs.endswith(" ") else ""
            attrs = f'{attrs}{sep}xmlns:{prefix}="http://www.w3.org/1998/Math/MathML"'
        return f"<{prefix}:math{attrs}>"

    mathml = re.sub(r"<math\b([^>]*)>", _root_repl, mathml, count=1)
    mathml = re.sub(r"</math>", f"</{prefix}:math>", mathml)

    def _tag_repl(match):
        slash, name, rest = match.group(1), match.group(2), match.group(3)
        if ":" in name:
            return match.group(0)
        return f"<{slash}{prefix}:{name}{rest}>"

    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9:.-]*)(\b[^>]*)>", _tag_repl, mathml)

def build_math_html(latex_or_list, labels=None) -> str:
    """构建 MathJax 渲染 HTML，支持单个公式或公式列表
    
    Args:
        latex_or_list: 单个公式字符串或公式列表
        labels: 可选的标签列表，与公式一一对应
    
    注意：返回的 HTML 使用相对路径加载脚本，必须通过 setHtml(html, base_url) 使用！
    """
    try:
        if isinstance(latex_or_list, str):
            formulas = [latex_or_list] if latex_or_list.strip() else []
        else:
            formulas = [f for f in latex_or_list if f and f.strip()]
        
        if labels is None:
            labels = [None] * len(formulas)
        
        tokens = _preview_theme_tokens()

        # 生成每个公式的 MathJax HTML
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            
            # 使用 MathJax 渲染（不要 HTML 转义，保留 LaTeX）
            formula_html += f'<div class="math-container">{label_html}<div class="formula-content">$${latex}$$</div></div>\n'
        
        if not formula_html:
            formula_html = f'<div class="math-container" style="color:{tokens["muted_text"]};">无公式</div>'

        log_local_fallback = True
        try:
            from backend.latex_renderer import _latex_settings
            mode = _latex_settings.get_render_mode() if _latex_settings else "auto"
            log_local_fallback = mode in ("auto", "mathjax_local")
        except Exception:
            pass
        
        # 使用 MathJax HTML 模板（使用相对路径）
        html = MATHJAX_HTML_TEMPLATE.replace("__FORMULAS__", formula_html)
        html = html.replace("__LOG_MATHJAX_LOCAL_FALLBACK__", "true" if log_local_fallback else "false")
        html = html.replace("__BODY_BG__", tokens["body_bg"])
        html = html.replace("__BODY_TEXT__", tokens["body_text"])
        html = html.replace("__LABEL_TEXT__", tokens["label_text"])
        html = html.replace("__LABEL_BG__", tokens["label_bg"])
        html = html.replace("__ERROR_TEXT__", tokens["error_text"])
        html = html.replace("__ERROR_BG__", tokens["error_bg"])
        
        return html
    except Exception as e:
        print(f"[ERROR] build_math_html 出错: {e}")
        import traceback
        traceback.print_exc()
        # 返回错误提示 HTML
        tokens = _preview_theme_tokens()
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
    <body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>公式渲染出错</h3>
<p><strong>错误信息:</strong> {str(e)}</p>
<p>请检查 MathJax 资源是否正确打包</p>
</body></html>'''

# WebEngine 延迟导入
QWebEngineView = None

def _webengine_diag_enabled() -> bool:
    return str(os.environ.get("LATEXSNIPPER_WEBENGINE_DIAG", "0")).strip() in ("1", "true", "yes", "on")

def _log_webengine_diagnostics(stage: str, err: Exception | None = None) -> None:
    """输出 WebEngine 诊断信息，定位打包环境加载失败原因。"""
    if err is None and not _webengine_diag_enabled():
        return
    try:
        logger = logging.getLogger("webengine")
        log_info = logger.info
        log_warn = logger.warning
    except Exception:
        log_info = print
        log_warn = print

    def _fmt(path: Path | None) -> str:
        try:
            return str(path) if path else "<none>"
        except Exception:
            return "<invalid>"

    log_info(f"[WebEngine] 诊断阶段: {stage}")
    if err is not None:
        log_warn(f"[WebEngine] 异常: {err}")

    # 基础运行环境
    log_info(f"[WebEngine] frozen={getattr(sys, 'frozen', False)} _MEIPASS={getattr(sys, '_MEIPASS', None)}")
    log_info(f"[WebEngine] executable={sys.executable}")
    log_info(f"[WebEngine] APP_DIR={APP_DIR if 'APP_DIR' in globals() else '<unset>'}")

    # QtWebEngineProcess.exe 检查
    exe_name = "QtWebEngineProcess.exe" if os.name == "nt" else "QtWebEngineProcess"
    candidates = []
    try:
        if hasattr(sys, "_MEIPASS"):
            mp = Path(sys._MEIPASS)
            candidates.extend([
                mp / "Qt6" / "bin" / exe_name,
                mp / "PyQt6" / "Qt6" / "bin" / exe_name,
            ])
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "Qt6" / "bin" / exe_name,
            exe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
            exe_dir / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / exe_name,
        ])
        pyexe_env = os.environ.get("LATEXSNIPPER_PYEXE", "")
        if pyexe_env:
            pyexe_dir = Path(pyexe_env).parent
            candidates.extend([
                pyexe_dir / "Qt6" / "bin" / exe_name,
                pyexe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
                pyexe_dir / "Lib" / "site-packages" / "PyQt6" / "Qt6" / "bin" / exe_name,
            ])
    except Exception:
        candidates = []

    found = next((p for p in candidates if p.exists()), None)
    log_info(f"[WebEngine] QtWebEngineProcess found={_fmt(found)}")
    if not found and candidates:
        log_warn(f"[WebEngine] QtWebEngineProcess candidates={', '.join(_fmt(p) for p in candidates)}")

    # 资源文件检查
    resource_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            resource_dirs.append(Path(sys._MEIPASS) / "Qt6" / "resources")
            resource_dirs.append(Path(sys._MEIPASS) / "PyQt6" / "Qt6" / "resources")
        exe_dir = Path(sys.executable).parent
        resource_dirs.append(exe_dir / "Qt6" / "resources")
        resource_dirs.append(exe_dir / "PyQt6" / "Qt6" / "resources")
    except Exception:
        resource_dirs = []

    required = [
        "qtwebengine_resources.pak",
        "qtwebengine_resources_100p.pak",
        "qtwebengine_resources_200p.pak",
        "icudtl.dat",
    ]
    optional = ["qtwebengine_devtools_resources.pak"]

    for rdir in resource_dirs:
        if not rdir.exists():
            continue
        missing = [f for f in required if not (rdir / f).exists()]
        present_opt = [f for f in optional if (rdir / f).exists()]
        log_info(f"[WebEngine] resources_dir={_fmt(rdir)} missing={missing or '<none>'} optional={present_opt or '<none>'}")

    # locales 检查
    locale_dirs = []
    try:
        if hasattr(sys, "_MEIPASS"):
            locale_dirs.append(Path(sys._MEIPASS) / "Qt6" / "translations" / "qtwebengine_locales")
            locale_dirs.append(Path(sys._MEIPASS) / "Qt6" / "resources" / "qtwebengine_locales")
        exe_dir = Path(sys.executable).parent
        locale_dirs.append(exe_dir / "Qt6" / "translations" / "qtwebengine_locales")
        locale_dirs.append(exe_dir / "Qt6" / "resources" / "qtwebengine_locales")
    except Exception:
        locale_dirs = []

    for ldir in locale_dirs:
        if not ldir.exists():
            continue
        try:
            pak_count = len(list(ldir.glob("*.pak")))
        except Exception:
            pak_count = 0
        log_info(f"[WebEngine] locales_dir={_fmt(ldir)} pak_count={pak_count}")

def ensure_webengine_loaded() -> bool:
    """延迟加载 WebEngine"""
    global QWebEngineView
    if QWebEngineView is not None:
        print("[DEBUG] WebEngine 已加载")
        return True
    try:
        _log_webengine_diagnostics("before-import")
        from PyQt6.QtWebEngineWidgets import QWebEngineView as _QEW
        QWebEngineView = _QEW
        print("[DEBUG] WebEngine 成功导入")
        _log_webengine_diagnostics("import-ok")
        return True
    except Exception as e:
        print(f"[WARN] WebEngine 未就绪: {e}")
        import traceback
        traceback.print_exc()
        _log_webengine_diagnostics("import-failed", e)
        return False

class CenterMenu(RoundMenu):
    def __init__(self, title: str = "", parent=None):
        super().__init__(title=title, parent=parent)

    def add_center_button(self, text: str, slot):
        from qfluentwidgets import PushButton
        btn = PushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)

        btn.clicked.connect(slot)
        act = QWidgetAction(self)
        act.setDefaultWidget(btn)
        self.addAction(act)
        return act
class ConfigManager:
    def __init__(self):
        self.path = str(_config_path())
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if not isinstance(self.data, dict):
                    self.data = {}
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[Config] 保存失败:", e)


def normalize_content_type(content_type: str | None) -> str:
    """将内容类型限制为当前支持的内置 MathCraft 类型。"""
    t = (content_type or "").strip().lower()
    allowed = {"mathcraft", "mathcraft_text", "mathcraft_mixed"}
    return t if t in allowed else "mathcraft"

class FavoritesWindow(QMainWindow):
    """收藏夹窗口 - 简化版，只保留列表功能"""
    def __init__(self, cfg: ConfigManager, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._theme_is_dark_cached = None
        self.setWindowFlag(Qt.WindowType.Window, True)
        _apply_close_only_window_flags(self)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("公式收藏夹")
        self.setMinimumSize(400, 350)

        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 使用容器 widget
        container = QWidget()
        main_lay = QVBoxLayout(container)
        main_lay.setContentsMargins(6, 6, 6, 6)
        main_lay.setSpacing(6)
        
        from qfluentwidgets import PushButton, FluentIcon
        
        # 顶部按钮行
        top_btn_layout = QHBoxLayout()
        btn_save_path = PushButton(FluentIcon.FOLDER, "保存路径")
        btn_save_path.clicked.connect(self.select_file)
        top_btn_layout.addWidget(btn_save_path)
        
        btn_clear = PushButton(FluentIcon.DELETE, "清空收藏夹")
        btn_clear.clicked.connect(self._clear_all_favorites)
        top_btn_layout.addWidget(btn_clear)
        main_lay.addLayout(top_btn_layout)

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setWordWrap(True)
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setMinimumHeight(200)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_lay.addWidget(self.list_widget, 1)

        close_btn = PushButton(FluentIcon.CLOSE, "关闭窗口")
        close_btn.clicked.connect(self.close)
        main_lay.addWidget(close_btn, 0)

        # 将容器设置为中心 widget
        self.setCentralWidget(container)

        self.favorites = []
        self._favorite_names = {}   # 收藏名称: {content: name}
        self._favorite_types = {}   # 收藏类型: {content: content_type}
        favorites_path = _resolve_user_data_file(self.cfg, "favorites_path", DEFAULT_FAVORITES_NAME)
        self.file_path = favorites_path
        self.load_favorites()

        # --- 新增: ESC 快捷关闭（备用方案，防止某些子控件截获按键） ---
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.close)
        self.apply_theme_styles(force=True)

    # --- 新增: 捕获 ESC 按键 ---
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _favorites_list_qss(self) -> str:
        t = _preview_theme_tokens()
        return f"""
            QListWidget {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {t['table_border']};
                padding: 8px 6px;
                color: {t['body_text']};
                background: transparent;
                outline: none;
                border-left: none;
                border-right: none;
            }}
            QListWidget::item:hover {{
                background: {t['panel_bg']};
            }}
            QListWidget::item:selected {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:selected:active {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:selected:!active {{
                background: {t['badge_formula_bg']};
                color: {t['body_text']};
                border: none;
                outline: none;
            }}
            QListWidget::item:focus {{
                border: none;
                outline: none;
            }}
        """

    def apply_theme_styles(self, force: bool = False):
        dark = False
        try:
            from qfluentwidgets import isDarkTheme
            dark = bool(isDarkTheme())
        except Exception:
            try:
                pal = self.palette().window().color()
                dark = ((pal.red() + pal.green() + pal.blue()) / 3.0) < 128
            except Exception:
                dark = False
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        try:
            self.list_widget.setStyleSheet(self._favorites_list_qss())
        except Exception:
            pass

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self.apply_theme_styles()
        except Exception:
            pass
        return result

    # ---------- 状态 ----------
    def _set_status(self, msg: str):
        p = self.parent()
        if p and hasattr(p, "set_action_status"):
            p.set_action_status(msg)
    
    def _on_item_double_clicked(self, item):
        """双击加载公式到编辑器并渲染"""
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            latex = item.text()
        
        p = self.parent()
        if p and hasattr(p, 'latex_editor') and hasattr(p, 'render_latex_in_preview'):
            if hasattr(p, "_set_editor_text_silent"):
                p._set_editor_text_silent(latex)
            else:
                p.latex_editor.setPlainText(latex)
            
            # 确保父窗口有这个内容的类型信息
            content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            
            # 获取编号和名称（优先使用收藏夹的名称）
            idx = self.list_widget.row(item) + 1
            name = self._favorite_names.get(latex, "")
            if not name and hasattr(p, '_formula_names'):
                name = p._formula_names.get(latex, "")
            
            if name:
                label = f"#{idx} {name}"
            else:
                label = f"#{idx}"
            p.render_latex_in_preview(latex, label)
            self._set_status("已加载到编辑器")

    # ---------- 菜单 ----------
    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            return
        
        menu = QMenu(self)
        a_copy = menu.addAction("复制")
        
        # 导出子菜单 - 增加更多导出格式
        export_menu = menu.addMenu("导出为...")
        a_latex = export_menu.addAction("LaTeX (行内 $...$)")
        a_latex_display = export_menu.addAction("LaTeX (display \\[...\\])")
        a_latex_equation = export_menu.addAction("LaTeX (equation 编号)")
        export_menu.addSeparator()
        a_md_inline = export_menu.addAction("Markdown (行内 $...$)")
        a_md_block = export_menu.addAction("Markdown (块级 $$...$$)")
        export_menu.addSeparator()
        a_mathml = export_menu.addAction("MathML")
        a_mathml_mml = export_menu.addAction("MathML (.mml)")
        a_mathml_m = export_menu.addAction("MathML (<m>)")
        a_mathml_attr = export_menu.addAction("MathML (attr)")
        export_menu.addSeparator()
        a_html = export_menu.addAction("HTML")
        a_omml = export_menu.addAction("Word OMML")
        a_svgcode = export_menu.addAction("SVG Code")
        
        menu.addSeparator()
        a_add_history = menu.addAction("添加到历史")
        a_rename = menu.addAction("重命名")
        a_edit = menu.addAction("编辑")
        a_del = menu.addAction("删除")
        act = menu.exec(self.list_widget.mapToGlobal(pos))
        if act == a_copy:
            self._copy_item(latex)
        elif act == a_add_history:
            self._add_to_history(latex)
        elif act == a_rename:
            self._rename_item(latex)
        elif act == a_edit:
            self._edit_item(item, latex)
        elif act == a_del:
            self._delete_item(latex)
        elif act == a_latex:
            self._export_as("latex", latex)
        elif act == a_latex_display:
            self._export_as("latex_display", latex)
        elif act == a_latex_equation:
            self._export_as("latex_equation", latex)
        elif act == a_html:
            self._export_as("html", latex)
        elif act == a_md_inline:
            self._export_as("markdown_inline", latex)
        elif act == a_md_block:
            self._export_as("markdown_block", latex)
        elif act == a_mathml:
            self._export_as("mathml", latex)
        elif act == a_mathml_mml:
            self._export_as("mathml_mml", latex)
        elif act == a_mathml_m:
            self._export_as("mathml_m", latex)
        elif act == a_mathml_attr:
            self._export_as("mathml_attr", latex)
        elif act == a_omml:
            self._export_as("omml", latex)
        elif act == a_svgcode:
            self._export_as("svgcode", latex)
    
    def _add_to_history(self, latex: str):
        """将收藏夹公式添加到历史记录（继承标签和类型）"""
        p = self.parent()
        if not p or not hasattr(p, 'history'):
            self._set_status("无法添加到历史")
            return
        
        if latex in p.history:
            self._set_status("公式已在历史中")
            return
        
        # 获取收藏的类型
        content_type = normalize_content_type(self._favorite_types.get(latex, "mathcraft"))
        # 继承名称（先写入历史名称映射，确保新插入行立即显示标签）
        name = self._favorite_names.get(latex, "")
        if name and hasattr(p, '_formula_names'):
            p._formula_names[latex] = name
        
        # 使用 add_history_record 方法添加（会自动处理类型）
        if hasattr(p, 'add_history_record'):
            p.add_history_record(latex, content_type)
        else:
            # 回退方式
            p.history.insert(0, latex)
            if hasattr(p, '_formula_types'):
                p._formula_types[latex] = content_type
            if hasattr(p, 'save_history'):
                p.save_history()
            if hasattr(p, 'rebuild_history_ui'):
                p.rebuild_history_ui()
            self._set_status("已添加到历史记录")

    def _export_as(self, format_type: str, latex: str):
        """导出公式为指定格式（统一使用 matplotlib SVG）"""
        result = ""
        format_name = ""
        clean = _normalize_latex_for_export(latex)

        if format_type == "latex":
            result = _latex_inline(clean)
            format_name = "LaTeX (行内)"
        elif format_type == "latex_display":
            result = _latex_display(clean)
            format_name = "LaTeX (display \\[\\])"
        elif format_type == "latex_equation":
            result = _latex_equation(clean)
            format_name = "LaTeX (equation)"
        elif format_type == "html":
            # HTML 格式
            try:
                result = _mathml_to_html_fragment(self._latex_to_mathml(clean))
            except Exception as e:
                self._set_status(f"HTML 导出失败: {e}")
                return
            format_name = "HTML"
        elif format_type == "markdown_inline":
            result = _latex_inline(clean)
            format_name = "Markdown 行内"
        elif format_type == "markdown_block":
            result = f"$$\n{clean}\n$$"
            format_name = "Markdown 块级"
        elif format_type == "mathml":
            try:
                result = self._latex_to_mathml(clean)
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML"
        elif format_type == "mathml_mml":
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "mml")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (.mml)"
        elif format_type == "mathml_m":
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "m")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (<m>)"
        elif format_type == "mathml_attr":
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "attr")
            except Exception as e:
                self._set_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (attr)"
        elif format_type == "omml":
            try:
                result = self._latex_to_omml(clean)
            except Exception as e:
                self._set_status(f"OMML 导出失败: {e}")
                return
            format_name = "Word OMML"
        elif format_type == "svgcode":
            try:
                result = self._latex_to_svg_code(clean)
            except Exception as e:
                self._set_status(f"SVG 导出失败: {e}")
                return
            format_name = "SVG Code"
        
        if result:
            try:
                from PyQt6.QtWidgets import QApplication
                QApplication.clipboard().setText(result)
                self._set_status(f"已复制 {format_name} 格式")
            except Exception:
                try:
                    import pyperclip
                    pyperclip.copy(result)
                    self._set_status(f"已复制 {format_name} 格式")
                except Exception:
                    self._set_status("复制失败")
    
    def _latex_to_svg_code(self, latex: str) -> str:
        """将 LaTeX 转换为 SVG 代码"""
        return latex_to_svg(latex)
    
    def _latex_to_mathml(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 格式"""
        latex = _normalize_latex_for_export(latex)
        import latex2mathml.converter
        mathml = latex2mathml.converter.convert(latex)
        return _mathml_standardize(mathml)
    
    def _latex_to_mathml_element(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML <m> 元素格式"""
        return _mathml_with_prefix(self._latex_to_mathml(latex), "m")
    
    def _latex_to_mathml_with_attr(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 属性格式"""
        return _mathml_with_prefix(self._latex_to_mathml(latex), "attr")
    def _latex_to_omml(self, latex: str) -> str:
        """将 LaTeX 转换为 OMML 格式"""
        try:
            latex = _normalize_latex_for_export(latex)
            import latex2mathml.converter as _latex2mathml_converter
            _ = _latex2mathml_converter
            mathml = self._latex_to_mathml(latex)

            try:
                from lxml import etree
                import os

                xsl_paths = [
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
                ]

                for xsl_path in xsl_paths:
                    if os.path.exists(xsl_path):
                        xslt = etree.parse(xsl_path)
                        transform = etree.XSLT(xslt)
                        doc = etree.fromstring(mathml.encode())
                        result = transform(doc)
                        return str(result)

                return mathml
            except ImportError:
                return mathml
        except ImportError:
            escaped = latex.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            return f"{{ EQ \\\\o\\\\al(\\\\lc\\\\(({escaped})\\\\rc\\\\))"
        except Exception:
            raise

    def _copy_item(self, latex: str):
        """复制公式到剪贴板"""
        import pyperclip
        if latex:
            pyperclip.copy(latex)
            self._set_status("已复制到剪贴板")

    def _rename_item(self, latex: str):
        """重命名收藏夹中的公式"""
        p = self.parent()
        # 使用收藏夹自己的名称字典
        current_name = self._favorite_names.get(latex, "")
        if not current_name:
            if p and hasattr(p, "_formula_names"):
                current_name = p._formula_names.get(latex, "")
        new_name, ok = _show_formula_rename_dialog(
            self,
            current_name=current_name,
            title="公式命名",
            prompt="输入公式名称（留空则清除名称）：",
        )
        if not ok:
            return
        if new_name:
            self._favorite_names[latex] = new_name
            if p and hasattr(p, "_formula_names"):
                p._formula_names[latex] = new_name
                if hasattr(p, "save_history"):
                    p.save_history()
            self._set_status(f"已命名为: {new_name}")
        else:
            self._favorite_names.pop(latex, None)
            if p and hasattr(p, "_formula_names"):
                p._formula_names.pop(latex, None)
                if hasattr(p, "save_history"):
                    p.save_history()
            self._set_status("已清除名称")

        # 保存收藏夹
        self.save_favorites()

        # 刷新列表显示
        self.refresh_list()
        # 同步刷新主窗口历史记录（否则历史中的同公式名称不会立即更新）
        if p and hasattr(p, "rebuild_history_ui"):
            p.rebuild_history_ui()
        # 同步刷新主窗口预览中的标签（否则预览标签可能保持旧名称）
        if p and hasattr(p, "_rendered_formulas"):
            updated = False
            new_rendered = []
            for formula, label in getattr(p, "_rendered_formulas", []):
                if formula != latex:
                    new_rendered.append((formula, label))
                    continue
                s = (label or "").strip()
                prefix = ""
                if s.startswith("#"):
                    prefix = s.split(" ", 1)[0]
                if new_name:
                    new_label = f"{prefix} {new_name}".strip() if prefix else new_name
                else:
                    new_label = prefix
                new_rendered.append((formula, new_label))
                updated = True
            if updated:
                p._rendered_formulas = new_rendered
                if hasattr(p, "_refresh_preview"):
                    p._refresh_preview()

    def _edit_item(self, item, latex: str):
        """编辑公式内容"""
        dlg = EditFormulaDialog(latex, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new = dlg.value()
            if new and new != latex:
                # 查找在 favorites 中的索引
                if latex in self.favorites:
                    idx = self.favorites.index(latex)
                    self.favorites[idx] = new

                    # 更新收藏夹自己的名称和类型映射
                    if latex in self._favorite_names:
                        self._favorite_names[new] = self._favorite_names.pop(latex)
                    if latex in self._favorite_types:
                        self._favorite_types[new] = self._favorite_types.pop(latex)

                    self.save_favorites()
                    self.refresh_list()
                    self._set_status("已更新")

    def _delete_item(self, latex: str):
        """删除收藏项"""
        if latex in self.favorites:
            self.favorites.remove(latex)
            # 清理名称和类型映射
            self._favorite_names.pop(latex, None)
            self._favorite_types.pop(latex, None)
            self.refresh_list()
            self.save_favorites()
            self._set_status("已删除")

    # ---------- 列表/文件 ----------
    def refresh_list(self):
        self.list_widget.clear()

        # 类型显示名称
        type_names = {
            "mathcraft": "公式",
            "mathcraft_text": "文字",
            "mathcraft_mixed": "混合",
        }

        for idx, formula in enumerate(self.favorites, start=1):
            # 创建带样式的列表项
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, formula)  # 存储原始公式

            # 获取名称和类型（优先使用收藏夹自己的）
            name = self._favorite_names.get(formula, "")
            if not name:
                p = self.parent()
                if p and hasattr(p, "_formula_names"):
                    name = p._formula_names.get(formula, "")
            content_type = normalize_content_type(self._favorite_types.get(formula, "mathcraft"))
            type_display = type_names.get(content_type, "")

            # 构建显示文本
            parts = [f"#{idx}"]
            if name:
                parts.append(f"[{name}]")
            if type_display and type_display != "公式":  # 公式是默认，不显示
                parts.append(f"<{type_display}>")
            display_text = " ".join(parts) + f"\n{formula}"

            item.setText(display_text)
            item.setToolTip(formula)

            # 设置项目大小和样式
            from PyQt6.QtCore import QSize
            item.setSizeHint(QSize(0, 50))  # 最小高度

            self.list_widget.addItem(item)

        self.list_widget.setStyleSheet(self._favorites_list_qss())

    def select_file(self):
        path, _ = _select_save_file_with_icon(
            self,
            "选择收藏夹保存路径",
            os.path.dirname(self.file_path),
            "JSON Files (*.json)",
        )
        if path:
            self.file_path = path
            self.cfg.set("favorites_path", path)
            self.save_favorites()
            self._set_status("已更新保存路径")

    def load_favorites(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # 新格式：包含收藏列表、名称和类型
                    fav_list = data.get("favorites", [])
                    self.favorites = [str(x) for x in fav_list]
                    # 加载名称
                    names = data.get("names", {})
                    if isinstance(names, dict):
                        self._favorite_names = {str(k): str(v) for k, v in names.items()}
                    # 加载类型
                    types = data.get("types", {})
                    if isinstance(types, dict):
                        self._favorite_types = {
                            str(k): normalize_content_type(str(v))
                            for k, v in types.items()
                        }
            except Exception as e:
                print("[Favorites] 加载失败:", e)
        self.refresh_list()

    def save_favorites(self):
        try:
            # 保存收藏列表、名称和类型
            data = {
                "favorites": self.favorites,
                "names": self._favorite_names,
                "types": self._favorite_types
            }
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[Favorites] 保存失败:", e)

    def _clear_all_favorites(self):
        """清空所有收藏"""
        if not self.favorites:
            info_parent = self.parent() if self.parent() is not None else self
            InfoBar.info(
                title="提示",
                content="收藏夹已经是空的",
                parent=info_parent,
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return

        ret = _exec_close_only_message_box(
            self,
            "确认",
            f"确定要清空所有 {len(self.favorites)} 条收藏吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.favorites.clear()
        self._favorite_names.clear()
        self._favorite_types.clear()
        self.save_favorites()
        self.refresh_list()
        self._set_status("已清空收藏夹")

    # ---------- 对外 ----------
    def add_favorite(self, text: str, content_type: str = None, name: str = None):
        """添加收藏

        Args:
            text: 内容文本
            content_type: 内容类型 (mathcraft, mathcraft_mixed 等)
            name: 自定义名称
        """
        t = (text or "").strip()
        if not t:
            self._set_status("空公式，忽略")
            return
        if t in self.favorites:
            self._set_status("已存在")
            return

        self.favorites.append(t)

        # 存储类型（如果没指定，从父窗口获取当前模式）
        if content_type is None:
            p = self.parent()
            if p and hasattr(p, "_formula_types") and t in p._formula_types:
                content_type = p._formula_types.get(t)
            elif p:
                try:
                    content_type = getattr(getattr(p, "model", None), "last_used_model", None)
                except Exception:
                    content_type = None
                if not content_type and hasattr(p, "current_model"):
                    content_type = p.current_model
            if not content_type:
                content_type = "mathcraft"
        self._favorite_types[t] = normalize_content_type(content_type)

        # 存储名称（如果没指定，从父窗口获取）
        if name is None:
            p = self.parent()
            if p and hasattr(p, "_formula_names"):
                name = p._formula_names.get(t, "")
        if name:
            self._favorite_names[t] = name

        self.refresh_list()
        self.save_favorites()
        self.show(); self.raise_(); self.activateWindow()
        self._set_status("已加入收藏")

class PdfResultWindow(QMainWindow):
    """PDF 识别结果独立窗口（非模态，避免阻塞主窗口）。"""
    def __init__(self, status_cb=None, window_icon: QIcon | None = None):
        super().__init__(None)
        self._status_cb = status_cb
        self._fmt_key = "markdown"
        self._preference_label = ""
        self.setWindowTitle("PDF 识别结果")
        if window_icon is not None:
            try:
                self.setWindowIcon(window_icon)
            except Exception:
                pass
        self.resize(780, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        container = QWidget(self)
        lay = QVBoxLayout(container)
        lay.addWidget(BodyLabel("识别结果（可编辑/复制/保存）："))
        self.editor = QPlainTextEdit(self)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lay.addWidget(self.editor, 1)
        btn_row = QHBoxLayout()
        self.btn_copy = PushButton(FluentIcon.COPY, "复制")
        self.btn_save = PushButton(FluentIcon.SAVE, "保存")
        self.btn_close = PushButton(FluentIcon.CLOSE, "关闭")
        for b in (self.btn_copy, self.btn_save, self.btn_close):
            b.setFixedHeight(34)
            btn_row.addWidget(b)
        lay.addLayout(btn_row)
        self.setCentralWidget(container)
        self.btn_copy.clicked.connect(self._do_copy)
        self.btn_save.clicked.connect(self._do_save)
        self.btn_close.clicked.connect(self.close)
        self._theme_is_dark_cached = None
        self._structured_result = None
        self._apply_theme_styles(force=True)

    def set_content(self, text: str, fmt_key: str, preference_label: str = "", structured_result: dict | None = None):
        self._fmt_key = fmt_key
        self._preference_label = str(preference_label or "").strip()
        self._structured_result = structured_result if isinstance(structured_result, dict) else None
        mode = str((self._structured_result or {}).get("mode", "") or "").strip().lower()
        title = "PDF 文档解析结果" if mode == "parse" else "PDF 识别结果"
        if self._preference_label:
            title = f"{title} - {self._preference_label}"
        self.setWindowTitle(title)
        self.editor.setPlainText(text or "")

    def _apply_theme_styles(self, force: bool = False):
        dark = _is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result

    def _show_local_status(self, msg: str):
        InfoBar.success(
            title="提示",
            content=msg,
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
        )

    def _emit_status(self, msg: str):
        try:
            if callable(self._status_cb):
                try:
                    self._status_cb(msg, parent=self)
                    return
                except TypeError:
                    pass
            self._show_local_status(msg)
        except Exception:
            self._show_local_status(msg)

    def _do_copy(self):
        try:
            pyperclip.copy(self.editor.toPlainText())
            self._emit_status("已复制文档")
        except Exception as e:
            custom_warning_dialog("错误", f"复制失败: {e}", self)

    def _do_save(self):
        suffix = "md" if self._fmt_key == "markdown" else "tex"
        filter_ = "Markdown (*.md)" if self._fmt_key == "markdown" else "LaTeX (*.tex)"
        path, _ = _select_save_file_with_icon(
            self,
            "保存识别结果",
            f"识别结果.{suffix}",
            filter_,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self._export_structured_assets(path)
            self._emit_status("已保存文档")
        except Exception as e:
            custom_warning_dialog("错误", f"保存失败: {e}", self)

    def _export_structured_assets(self, document_path: str):
        payload = self._structured_result if isinstance(self._structured_result, dict) else {}
        assets_root = str(payload.get("assets_root", "") or "").strip()
        assets = payload.get("assets") or []
        inline_images = payload.get("inline_images") or {}
        if self._fmt_key != "markdown":
            return
        import shutil
        import re
        import base64

        base_dir = pathlib.Path(document_path).parent
        copied = 0

        if assets_root and isinstance(assets, list) and assets:
            for item in assets:
                if not isinstance(item, dict):
                    continue
                src = pathlib.Path(str(item.get("abs_path", "") or "").strip())
                rel = str(item.get("rel_path", "") or "").strip()
                if not rel and src.name:
                    rel = f"assets/{src.name}"
                if not rel or not src.exists():
                    continue
                dst = base_dir / pathlib.Path(rel)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                copied += 1

        # For MinerU /file_parse markdown, image references are often relative
        # paths like images/*.jpg. When structured assets are unavailable,
        # locate source roots from payload and copy referenced files.
        text = self.editor.toPlainText() if hasattr(self, "editor") else ""
        img_refs = re.findall(r"(?:!|！)\s*\[[^\]]*\]\s*\(([^)]+)\)", text or "")
        if not img_refs:
            return

        def _looks_local_rel_path(p: str) -> bool:
            s = str(p or "").strip()
            if not s:
                return False
            low = s.lower()
            if low.startswith("http://") or low.startswith("https://") or low.startswith("data:"):
                return False
            return True

        def _collect_candidate_dirs(node, acc: set[pathlib.Path]):
            if isinstance(node, dict):
                for v in node.values():
                    _collect_candidate_dirs(v, acc)
                return
            if isinstance(node, list):
                for v in node:
                    _collect_candidate_dirs(v, acc)
                return
            if not isinstance(node, str):
                return
            s = node.strip()
            if not s:
                return
            p = pathlib.Path(s)
            try:
                if p.exists():
                    if p.is_dir():
                        acc.add(p)
                    elif p.is_file():
                        acc.add(p.parent)
            except Exception:
                pass

        candidate_dirs: set[pathlib.Path] = set()
        if assets_root:
            p = pathlib.Path(assets_root)
            if p.exists() and p.is_dir():
                candidate_dirs.add(p)
                candidate_dirs.add(p.parent)
        _collect_candidate_dirs(payload, candidate_dirs)

        for ref in img_refs:
            rel = str(ref or "").strip().strip('"').strip("'")
            if not _looks_local_rel_path(rel):
                continue
            rel_path = pathlib.Path(rel)
            dst = base_dir / rel_path
            if dst.exists():
                continue
            found_src = None
            for d in candidate_dirs:
                src = d / rel_path
                if src.exists() and src.is_file():
                    found_src = src
                    break
            if found_src is not None:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(found_src, dst)
                copied += 1
                continue

            # Fallback: materialize image from MinerU inline image map.
            if isinstance(inline_images, dict):
                key = rel_path.name
                data_uri = str(inline_images.get(key, "") or "").strip()
                if data_uri.startswith("data:") and "," in data_uri:
                    payload_b64 = data_uri.split(",", 1)[1]
                else:
                    payload_b64 = data_uri
                if payload_b64:
                    try:
                        raw = base64.b64decode(payload_b64, validate=False)
                        if raw:
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            dst.write_bytes(raw)
                            copied += 1
                    except Exception:
                        pass

    def closeEvent(self, event):
        try:
            doc = self.editor.document()
            doc.setUndoRedoEnabled(False)
            doc.clearUndoRedoStacks()
            self.editor.blockSignals(True)
        except Exception:
            pass
        print("[DEBUG] PDF 结果窗口关闭")
        return super().closeEvent(event)


class PreviewLatexRenderWorker(QObject):
    finished = pyqtSignal(str, object)

    def render_formula(self, cache_key: str, latex_code: str):
        svg = None
        try:
            renderer = get_latex_renderer()
            if renderer and renderer.is_available():
                svg = renderer.render_to_svg(str(latex_code or ""))
        except Exception:
            svg = None
        self.finished.emit(str(cache_key or ""), svg)

class MainWindow(QMainWindow):
    """主窗口 - 使用 QMainWindow 以正确支持 setCentralWidget"""
    _model_warmup_result_signal = pyqtSignal()
    _preview_latex_render_request = pyqtSignal(str, str)

    def __init__(self, startup_progress=None):
        super().__init__()
        self._startup_progress = startup_progress
        self._report_startup_progress("读取配置与启动参数...")
        self._pending_model_warmup_result = None
        self._model_warmup_result_signal.connect(self._apply_model_warmup_result)
        self._post_show_tasks_started = False
        self._startup_centered_once = False
        self._pending_hotkey_seq = None

        self.setWindowTitle("LaTeX Snipper")
        self.resize(1280, 760)
        self.setMinimumSize(1280, 760)

        self._force_exit = False
        # 状态字段
        self.model_status = "未加载"
        self.action_status = ""
        self._predict_busy = False
        self._last_recognition_cancel_notice_at = 0.0
        self.setAcceptDrops(True)
        self.overlay = None
        self._last_capture_screen_index = None
        self._next_predict_result_screen_index = None
        self.predict_thread = None
        self.predict_worker = None
        self.pdf_predict_thread = None
        self.pdf_predict_worker = None
        self.pdf_progress = None
        self._pdf_output_format = None
        self._pdf_doc_style = None
        self._pdf_dpi = None
        self._pdf_structured_result = None
        self._pdf_result_window = None
        self._predict_result_dialog = None
        self._restore_predict_result_dialog_after_capture = None
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        self._mathcraft_env_state = None
        self._last_capture_toast_ts = 0.0
        self.settings_window = None
        self.shortcut_window = None
        self.handwriting_window = None
        self.bilingual_pdf_window = None
        self._theme_is_dark_cached = None
        self._auto_theme_sync_in_progress = False
        self._auto_theme_refresh_timer = QTimer(self)
        self._auto_theme_refresh_timer.setSingleShot(True)
        self._auto_theme_refresh_timer.setInterval(160)
        self._auto_theme_refresh_timer.timeout.connect(self._on_auto_theme_refresh_timeout)
        self._model_warmup_in_progress = False
        self._model_warmup_notice_shown = False
        self._model_cache_repair_notice_shown = False
        self._preview_svg_cache = {}
        self._preview_svg_pending = set()
        self._preview_render_thread = None
        self._preview_render_worker = None
        self._model_warmup_callbacks = []

        # 配置与模型
        self.cfg = ConfigManager()
        self._sanitize_model_config()
        self._theme_mode = normalize_theme_mode(self.cfg.get("theme_mode", "auto"))
        self.apply_app_theme_mode(self._theme_mode, refresh_preview=False)
        self.current_model = self.cfg.get("default_model", "mathcraft")
        self.desired_model = self.cfg.get("desired_model", "mathcraft")
        try:
            if self.desired_model == "mathcraft":
                preferred = self._get_preferred_model_for_predict()
                if preferred:
                    self.current_model = preferred
        except Exception:
            pass
        self.model_dir = MODEL_DIR

        # 设置图标
        icon_path = resource_path("assets/icon.ico")
        self.icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.setWindowIcon(self.icon)

        # 初始化识别运行时，但不在主线程做模型预热
        self._report_startup_progress("正在加载主窗口组件...")
        try:
            self._report_startup_progress("正在初始化识别运行时...")
            # 在 ModelWrapper 初始化前先注入 MathCraft 运行环境变量
            self._apply_mathcraft_env()
            self.model = create_model_wrapper(self.current_model, auto_warmup=False)
            self.model.status_signal.connect(self.show_status_message)
            print("[DEBUG] ModelWrapper 初始化完成")

            # 根据当前偏好模型和其真实状态设置状态文本
            self.model_status = "未加载"
            self._sync_current_model_status_from_preference()
            self._report_startup_progress("识别运行时已就绪，稍后后台预热")

        except Exception as e:
            app = QApplication.instance() or QApplication([])
            from PyQt6.QtWidgets import QMessageBox as QMsgBox
            apply_theme_mode(read_theme_mode_from_config())
            from PyQt6.QtGui import QFont
            font = QFont("Microsoft YaHei UI", 9)
            font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            app.setFont(font)
            if isinstance(e, ModuleNotFoundError):
                # ====== 情况①：缺失依赖 ======
                clear_deps_state()
                QMsgBox.warning(
                    None, "依赖缺失",
                    "检测到依赖缺失，已重置状态文件。\n请重新选择安装目录并修复依赖。"
                )

                try:
                    # 尝试修复依赖
                    result = ensure_deps(always_show_ui=True, require_layers=("BASIC", "CORE"))
                    if result == "_force_wizard":
                        print("[INFO] 检测到损坏环境，进入依赖修复向导。")
                        show_dependency_wizard(always_show_ui=True)
                    elif not result:
                        print("[WARN] 用户取消了依赖修复，程序退出。")
                        sys.exit(0)
                except Exception as ee:
                    print(f"[FATAL] ensure_deps 失败: {ee}")
                    show_dependency_wizard(always_show_ui=True)
                    return

            else:
                # ====== 情况②：其他错误（比如模型文件损坏） ======
                msg = MessageBox(
                    "错误",
                    f"模型初始化失败：{e}\n程序将进入依赖修复界面。",
                    self
                )
                _apply_app_window_icon(msg)
                msg.exec()
                try:
                    ok = ensure_deps(always_show_ui=True, require_layers=("BASIC", "CORE"))
                    if not ok:
                        sys.exit(1)
                except Exception as ee:
                    print(f"[FATAL] ensure_deps 异常: {ee}")
                    show_dependency_wizard(always_show_ui=True)
                    return

        # 历史文件
        print("[DEBUG] 开始初始化历史记录")
        self._report_startup_progress("正在初始化历史记录...")
        self.history_path = _resolve_user_data_file(self.cfg, "history_path", DEFAULT_HISTORY_NAME)
        self.history = []

        # 状态栏（注意不要与方法同名）
        print("[DEBUG] 开始初始化状态栏")
        self._report_startup_progress("正在初始化状态栏...")
        self.status_label = QLabel()
        self.refresh_status_label()

        # 收藏窗口改为懒加载，降低首屏初始化耗时。
        self.favorites_window = None
        self._report_startup_progress("初始化平台能力与快捷键...")
        self.platform_registry = PlatformCapabilityRegistry(
            parent=self,
            disable_global_hotkey=PLATFORM_DISABLE_GLOBAL_HOTKEY,
        )
        self.platform_providers = self.platform_registry.create()
        self.hotkey_provider = self.platform_providers.hotkey
        self.screenshot_provider = self.platform_providers.screenshot
        self.system_provider = self.platform_providers.system
        if self.hotkey_provider.activated is not None:
            self.hotkey_provider.activated.connect(self.on_hotkey_triggered)
        seq = self.cfg.get("hotkey", "Ctrl+F")
        if not (seq.startswith("Ctrl+") and len(seq) == 6):
            seq = "Ctrl+F"
        self._pending_hotkey_seq = seq

        self._report_startup_progress("构建主窗口界面...")

        # ========== 左侧面板：历史记录 ==========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(8)

        # 截图识别按钮
        self.capture_button = PushButton(FluentIcon.SEARCH, "截图识别")
        self.capture_button.setFixedHeight(40)
        self.capture_button.clicked.connect(self.start_capture)
        left_layout.addWidget(self.capture_button)

        # 历史记录标题与排序切换
        history_header = QHBoxLayout()
        history_header.setContentsMargins(0, 0, 0, 0)
        history_header.setSpacing(6)
        self.history_title_label = QLabel("历史记录")
        history_header.addWidget(self.history_title_label)
        history_header.addStretch()
        self.history_reverse = bool(self.cfg.get("history_reverse", True))
        self.history_order_button = PushButton("最新在前" if self.history_reverse else "最早在前")
        self.history_order_button.setFixedHeight(28)
        self.history_order_button.clicked.connect(self.toggle_history_order)
        history_header.addWidget(self.history_order_button)
        left_layout.addLayout(history_header)

        # 历史记录滚动区域
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(6)
        self.history_layout.addStretch()
        self.history_scroll.setWidget(self.history_container)
        left_layout.addWidget(self.history_scroll, 1)

        # 底部按钮区
        btn_row = QHBoxLayout()
        self.clear_history_button = PushButton(FluentIcon.DELETE, "清空")
        self.change_key_button = PushButton(FluentIcon.CLIPPING_TOOL, "快捷键")
        self.show_fav_button = PushButton(FluentIcon.HEART, "收藏夹")
        self.settings_button = PushButton(FluentIcon.SETTING, "设置")
        self.clear_history_button.clicked.connect(self.clear_history)
        self.change_key_button.clicked.connect(self.set_shortcut)
        self.show_fav_button.clicked.connect(self.open_favorites)
        self.settings_button.clicked.connect(self.open_settings)
        btn_row.addWidget(self.clear_history_button)
        btn_row.addWidget(self.change_key_button)
        btn_row.addWidget(self.show_fav_button)
        btn_row.addWidget(self.settings_button)
        left_layout.addLayout(btn_row)

        left_layout.addWidget(self.status_label)

        # ========== 右侧面板：编辑器 + 渲染区域 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(8)

        # LaTeX 编辑区标题和工具栏
        editor_header = QHBoxLayout()
        editor_header.setContentsMargins(0, 0, 0, 0)
        editor_header.setSpacing(0)
        self.editor_title_label = QLabel("LaTeX 编辑器")
        editor_header.addWidget(self.editor_title_label)
        editor_header.addSpacing(6)
        self.upload_image_btn = PushButton(FluentIcon.PHOTO, "图片识别")
        self.upload_image_btn.clicked.connect(self._upload_image_recognition)
        self.upload_pdf_btn = PushButton(FluentIcon.DOCUMENT, "PDF识别")
        self.upload_pdf_btn.clicked.connect(self._upload_pdf_recognition)
        try:
            img_exts = self._get_supported_image_extensions()
            self.upload_image_btn.setToolTip("支持格式: " + ", ".join(img_exts))
        except Exception:
            pass
        self.upload_pdf_btn.setToolTip("支持格式: PDF")
        self.copy_editor_btn = PushButton(FluentIcon.COPY, "复制")
        self.copy_editor_btn.clicked.connect(self._copy_editor_content)
        self.export_btn = PushButton(FluentIcon.SHARE, "导出")
        self.export_btn.clicked.connect(self._show_export_menu)
        self.handwriting_btn = PushButton(FluentIcon.FINGERPRINT, "手写识别")
        self.handwriting_btn.clicked.connect(self.open_handwriting_window)
        self.bilingual_reading_btn = PushButton(FluentIcon.BOOK_SHELF, "双语阅读")
        self.bilingual_reading_btn.clicked.connect(self.open_bilingual_reader)
        self.workbench_btn = PushButton(FluentIcon.PROJECTOR, "数学工作台")
        self.workbench_btn.clicked.connect(self.open_workbench)
        editor_actions = QHBoxLayout()
        editor_actions.setContentsMargins(0, 0, 0, 0)
        editor_actions.setSpacing(6)
        editor_actions.addWidget(self.upload_image_btn)
        editor_actions.addWidget(self.upload_pdf_btn)
        editor_actions.addWidget(self.handwriting_btn)
        editor_actions.addWidget(self.copy_editor_btn)
        editor_actions.addWidget(self.export_btn)
        editor_actions.addWidget(self.bilingual_reading_btn)
        editor_actions.addWidget(self.workbench_btn)
        editor_header.addLayout(editor_actions)
        right_layout.addLayout(editor_header)

        # LaTeX 编辑器
        from qfluentwidgets import PlainTextEdit
        self.latex_editor = PlainTextEdit()
        self.latex_editor.setPlaceholderText("在此输入 LaTeX 公式，下方将实时渲染...")
        self.latex_editor.setMinimumHeight(100)
        self.latex_editor.setMaximumHeight(150)
        right_layout.addWidget(self.latex_editor)

        # 渲染区域标题和清空按钮
        preview_header = QHBoxLayout()
        self.preview_title_label = QLabel("实时渲染预览")
        preview_header.addWidget(self.preview_title_label)
        preview_header.addStretch()
        self.clear_preview_btn = PushButton(FluentIcon.BROOM, "清空预览")
        self.clear_preview_btn.clicked.connect(self._clear_preview)
        preview_header.addWidget(self.clear_preview_btn)
        right_layout.addLayout(preview_header)

        # 初始化 WebEngine 渲染视图
        self._report_startup_progress("初始化公式预览引擎...")
        self.preview_view = None
        self._render_timer = None
        self._pending_latex = ""
        self._rendered_formulas = []  # 存储已渲染的公式列表: [(formula, label), ...]
        self._formula_names = {}  # 存储公式名称映射: {formula: name}
        self._formula_types = {}  # 存储公式内容类型: {formula: content_type}
        if ensure_webengine_loaded():
            self.preview_view = QWebEngineView()
            
            # 允许本地 MathJax 资源访问
            try:
                from PyQt6.QtWebEngineCore import QWebEngineSettings
                settings = self.preview_view.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            except Exception:
                pass  # 安全设置配置失败（可能是版本差异）
            
            self.preview_view.setMinimumHeight(200)
            try:
                self.preview_view.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
            except Exception:
                pass
            # 连接调试信号，定位渲染空白问题
            try:
                pg = self.preview_view.page()
                pg.loadStarted.connect(lambda: None)
                pg.loadFinished.connect(lambda ok: print(f"[WebEngine] loadFinished ok={ok}"))
                pg.renderProcessTerminated.connect(lambda status, code: print(f"[WebEngine] renderProcessTerminated status={status} code={code}"))
            except Exception:
                pass
            # 初始显示空白渲染
            html = build_math_html("")
            base_url = _get_mathjax_base_url()
            
            try:
                self.preview_view.setHtml(html, base_url)
            except Exception:
                pass  # setHtml 异常
            right_layout.addWidget(self.preview_view, 1)

            # 设置渲染防抖定时器
            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._do_render_latex)

            # 连接编辑器文本变化信号
            self.latex_editor.textChanged.connect(self._on_editor_text_changed)
        else:
            # WebEngine 不可用时显示提示
            self.preview_fallback_label = QLabel("WebEngine 未加载，无法渲染公式预览。\n请确保已安装 PyQtWebEngine。")
            self.preview_fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            right_layout.addWidget(self.preview_fallback_label, 1)

        # ========== 主布局：左右分栏 ==========
        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([420, 900])  # 初始宽度比例
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        container = QWidget()
        for drop_target in (
            left_panel,
            right_panel,
            splitter,
            container,
            self.latex_editor,
            self.preview_view,
            getattr(self, "preview_fallback_label", None),
        ):
            self._enable_file_drop_target(drop_target)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # 设置中心 widget
        self.setCentralWidget(container)

        # 托盘
        self._report_startup_progress("初始化系统托盘与历史记录...")
        self.tray_icon = self.system_provider.create_tray(self.icon, self)
        self.update_tray_tooltip()
        try:
            from PyQt6.QtGui import QGuiApplication

            qapp = QGuiApplication.instance()
            if qapp is not None:
                qapp.screenAdded.connect(lambda _screen: QTimer.singleShot(0, self.update_tray_menu))
                qapp.screenRemoved.connect(lambda _screen: QTimer.singleShot(0, self.update_tray_menu))
        except Exception:
            pass
        # 初始化界面
        self.load_history()
        self.update_history_ui()
        self.refresh_status_label()

        # 收藏夹窗口按需创建，启动阶段不提前初始化。

        self.update_tray_menu()

        self._apply_primary_buttons()
        self._apply_theme_styles(force=True)
        QApplication.instance().aboutToQuit.connect(self._graceful_shutdown)

    def _center_on_startup_screen_once(self) -> None:
        if getattr(self, "_startup_centered_once", False):
            return
        self._startup_centered_once = True
        try:
            from PyQt6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app is not None else None
            if screen is None:
                return
            geo = screen.availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(geo.center())
            top_left = frame.topLeft()
            max_x = geo.right() - frame.width() + 1
            max_y = geo.bottom() - frame.height() + 1
            x = max(geo.left(), min(top_left.x(), max_x))
            y = max(geo.top(), min(top_left.y(), max_y))
            self.move(x, y)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._center_on_startup_screen_once()

    def start_post_show_tasks(self):
        """Start deferred tasks after the main window is visible."""
        if getattr(self, "_post_show_tasks_started", False):
            return
        self._post_show_tasks_started = True

        seq = getattr(self, "_pending_hotkey_seq", None)
        if seq:
            QTimer.singleShot(0, lambda seq=seq: self.register_hotkey(seq))

        try:
            if self.model:
                QTimer.singleShot(0, self._warmup_desired_model)
        except Exception:
            pass

    def _ensure_favorites_window(self):
        if self.favorites_window is None:
            print("[DEBUG] 延迟初始化收藏窗口")
            self.favorites_window = FavoritesWindow(self.cfg, self)
        return self.favorites_window

    def _apply_primary_buttons(self) -> None:
        """
        兼容方法：为窗口内的 PrimaryPushButton 应用统一样式。
        若无按钮或 qfluentwidgets 版本差异导致失败，则安全忽略。
        """
        try:
            btns = self.findChildren(PrimaryPushButton)
        except Exception:
            return
        for b in btns or []:
            try:
                b.setStyleSheet(_action_btn_style())
            except Exception:
                pass

    def _main_theme_tokens(self) -> dict:
        if _is_dark_ui():
            return {
                "title": "#8ec5ff",
                "muted": "#95a0af",
            }
        return {
            "title": "#1976d2",
            "muted": "#888888",
        }

    def _apply_theme_styles(self, force: bool = False):
        dark = _is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        t = self._main_theme_tokens()
        title_style = f"font-size: 14px; font-weight: 500; color: {t['title']}; padding: 4px 0;"
        try:
            if hasattr(self, "history_title_label"):
                self.history_title_label.setStyleSheet(title_style)
            if hasattr(self, "editor_title_label"):
                self.editor_title_label.setStyleSheet(title_style)
            if hasattr(self, "preview_title_label"):
                self.preview_title_label.setStyleSheet(title_style)
            if hasattr(self, "preview_fallback_label") and self.preview_fallback_label:
                self.preview_fallback_label.setStyleSheet(f"color: {t['muted']}; padding: 20px;")
        except Exception:
            pass
        try:
            if self.settings_window and self.settings_window.isVisible() and hasattr(self.settings_window, "apply_theme_styles"):
                self.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            self._refresh_preview()
        except Exception:
            pass
        try:
            self._refresh_history_rows_theme()
        except Exception:
            pass

    def _schedule_auto_theme_refresh(self) -> None:
        if getattr(self, "_theme_mode", "auto") != "auto":
            return
        try:
            if hasattr(self, "_auto_theme_refresh_timer") and self._auto_theme_refresh_timer is not None:
                self._auto_theme_refresh_timer.start()
        except Exception:
            pass

    def _on_auto_theme_refresh_timeout(self) -> None:
        if getattr(self, "_theme_mode", "auto") != "auto":
            return
        if getattr(self, "_auto_theme_sync_in_progress", False):
            return
        self._auto_theme_sync_in_progress = True
        try:
            # 在 auto 模式下按 Qt 调色板强制落到 LIGHT/DARK，避免 isDarkTheme 状态滞后。
            dark_by_palette = False
            try:
                app = QApplication.instance()
                if app is not None:
                    c = app.palette().window().color()
                    dark_by_palette = ((c.red() + c.green() + c.blue()) / 3.0) < 128
            except Exception:
                dark_by_palette = _is_dark_ui()
            apply_theme("DARK" if dark_by_palette else "LIGHT")
            self._apply_theme_styles(force=True)
            try:
                if self.settings_window and self.settings_window.isVisible() and hasattr(self.settings_window, "apply_theme_styles"):
                    self.settings_window.apply_theme_styles(force=True)
            except Exception:
                pass
            try:
                if getattr(self, "workbench_window", None) and self.workbench_window.isVisible() and hasattr(self.workbench_window, "apply_theme_styles"):
                    self.workbench_window.apply_theme_styles(force=True)
            except Exception:
                pass
            try:
                if getattr(self, "favorites_window", None) and self.favorites_window.isVisible() and hasattr(self.favorites_window, "apply_theme_styles"):
                    self.favorites_window.apply_theme_styles(force=True)
            except Exception:
                pass
            try:
                if getattr(self, "handwriting_window", None) and self.handwriting_window.isVisible() and hasattr(self.handwriting_window, "apply_theme_styles"):
                    self.handwriting_window.apply_theme_styles(force=True)
            except Exception:
                pass
            try:
                global _LSN_RUNTIME_LOG_DIALOG
                if _LSN_RUNTIME_LOG_DIALOG is not None and hasattr(_LSN_RUNTIME_LOG_DIALOG, "_apply_theme_styles"):
                    _LSN_RUNTIME_LOG_DIALOG._apply_theme_styles(force=True)
            except Exception:
                pass
        finally:
            self._auto_theme_sync_in_progress = False

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                if getattr(self, "_theme_mode", "auto") == "auto":
                    self._schedule_auto_theme_refresh()
                else:
                    self._apply_theme_styles()
        except Exception:
            pass
        return result

    def _show_history_context_menu(self, row: QWidget, global_pos):
        if not self._row_is_alive(row):
            return
        latex = self._safe_row_text(row)
        m = CenterMenu(parent=self)
        m.addAction(Action("编辑", triggered=lambda: self._edit_history_row(row)))
        m.addAction(Action("复制", triggered=lambda: self._do_copy_row(row)))
        m.addAction(Action("收藏", triggered=lambda: self._do_fav_row(row)))

        # 导出子菜单 - 增加更多导出格式
        export_menu = CenterMenu("导出为...", parent=m)
        export_menu.addAction(Action("LaTeX (行内 $...$)", triggered=lambda: self._export_as("latex", latex)))
        export_menu.addAction(Action("LaTeX (display \\[...\\])", triggered=lambda: self._export_as("latex_display", latex)))
        export_menu.addAction(Action("LaTeX (equation 编号)", triggered=lambda: self._export_as("latex_equation", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("Markdown (行内 $...$)", triggered=lambda: self._export_as("markdown_inline", latex)))
        export_menu.addAction(Action("Markdown (块级 $$...$$)", triggered=lambda: self._export_as("markdown_block", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("MathML", triggered=lambda: self._export_as("mathml", latex)))
        export_menu.addAction(Action("MathML (.mml)", triggered=lambda: self._export_as("mathml_mml", latex)))
        export_menu.addAction(Action("MathML (<m>)", triggered=lambda: self._export_as("mathml_m", latex)))
        export_menu.addAction(Action("MathML (attr)", triggered=lambda: self._export_as("mathml_attr", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("HTML", triggered=lambda: self._export_as("html", latex)))
        export_menu.addAction(Action("Word OMML", triggered=lambda: self._export_as("omml", latex)))
        export_menu.addAction(Action("SVG Code", triggered=lambda: self._export_as("svgcode", latex)))
        m.addMenu(export_menu)

        m.addAction(Action("重命名", triggered=lambda: self._rename_history_row(row)))
        m.addAction(Action("删除", triggered=lambda: self._do_delete_row(row)))
        m.exec(global_pos)

    def _rename_history_row(self, row: QWidget):
        """重命名公式"""
        latex = self._safe_row_text(row)
        if not latex:
            return
        current_name = self._formula_names.get(latex, "")
        new_name, ok = _show_formula_rename_dialog(
            self,
            current_name=current_name,
            title="重命名公式",
            prompt="输入公式名称（留空则清除名称）：",
        )
        if not ok:
            return
        if new_name:
            self._formula_names[latex] = new_name
            if hasattr(self, "favorites_window") and self.favorites_window:
                self.favorites_window._favorite_names[latex] = new_name
                self.favorites_window.save_favorites()
                self.favorites_window.refresh_list()
        else:
            self._formula_names.pop(latex, None)
            if (
                hasattr(self, "favorites_window")
                and self.favorites_window
            ):
                self.favorites_window._favorite_names.pop(latex, None)
                self.favorites_window.save_favorites()
                self.favorites_window.refresh_list()
        self.save_history()

        # 同步更新渲染列表中的标签
        # 更新 _rendered_formulas 中的标签（保留原编号前缀）
        for i, (formula, label) in enumerate(self._rendered_formulas):
            if formula == latex:
                s = (label or "").strip()
                prefix = ""
                if s.startswith("#"):
                    prefix = s.split(" ", 1)[0]
                if new_name:
                    new_label = f"{prefix} {new_name}".strip() if prefix else new_name
                else:
                    new_label = prefix
                self._rendered_formulas[i] = (formula, new_label)

        # 刷新 UI
        self.rebuild_history_ui()
        self._refresh_preview()
        self.set_action_status(f"已命名: {new_name}" if new_name else "已清除名称")

    def update_tray_tooltip(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        mode = self._get_capture_display_mode()
        if mode == "index":
            idx = self._get_capture_display_index()
            disp = f"屏幕{idx + 1}" if idx is not None else "指定屏幕"
        else:
            disp = "自动屏幕"
        if getattr(self, "tray_icon", None):
            self.system_provider.set_tray_tooltip(self.tray_icon, f"LaTeXSnipper - 截图识别快捷键: {hk} | {disp}")

    def _get_capture_display_mode(self) -> str:
        mode = str(self.cfg.get("capture_display_mode", "auto") or "auto").strip().lower()
        return mode if mode in ("auto", "index") else "auto"

    def _get_capture_display_index(self) -> int | None:
        try:
            idx = int(self.cfg.get("capture_display_index", 0))
            return idx if idx >= 0 else 0
        except Exception:
            return 0

    def _set_capture_display_mode(self, mode: str, index: int | None = None):
        m = (mode or "auto").strip().lower()
        if m not in ("auto", "index"):
            m = "auto"
        self.cfg.set("capture_display_mode", m)
        if index is not None:
            try:
                self.cfg.set("capture_display_index", max(0, int(index)))
            except Exception:
                pass
        self.update_tray_tooltip()
        self.update_tray_menu()
        if m == "auto":
            self.set_action_status("截图屏幕模式: 自动")
        else:
            idx = self._get_capture_display_index() or 0
            self.set_action_status(f"截图屏幕模式: 屏幕 {idx + 1}")

    def _build_capture_display_submenu(self, tray_menu: QMenu):
        from PyQt6.QtGui import QGuiApplication

        submenu = tray_menu.addMenu("截图屏幕模式")
        mode = self._get_capture_display_mode()
        idx = self._get_capture_display_index() or 0

        act_auto = submenu.addAction("自动（按鼠标释放点）")
        act_auto.setCheckable(True)
        act_auto.setChecked(mode == "auto")
        act_auto.triggered.connect(lambda _=False: self._set_capture_display_mode("auto"))

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            g = screen.geometry()
            title = f"屏幕 {i + 1}: {screen.name()} ({g.width()}x{g.height()} @ {g.x()},{g.y()})"
            act = submenu.addAction(title)
            act.setCheckable(True)
            act.setChecked(mode == "index" and idx == i)
            act.triggered.connect(lambda _=False, screen_idx=i: self._set_capture_display_mode("index", screen_idx))

    def _safe_call(self, name, fn):
        print(f"[SlotEnter] {name}")
        try:
            fn()
            print(f"[SlotExit] {name}")
        except Exception as e:
            print(f"[SlotError] {name}: {e}")
    def _defer(self, fn):
        QTimer.singleShot(0, fn)
    # ---------- 状态管理 ----------
    def _get_status_model_display_name(self) -> str:
        current = str(getattr(self, "current_model", "") or "").strip()
        if current != "external_model":
            return current
        try:
            cfg = self._get_external_model_config()
            if cfg.normalized_provider() == "mineru":
                return "MinerU"
            model_name = cfg.normalized_model_name()
            if model_name:
                return model_name
        except Exception:
            pass
        return current

    def _sync_current_model_status_from_preference(self) -> None:
        preferred = str(self._get_preferred_model_for_predict() or getattr(self, "current_model", "mathcraft") or "mathcraft").strip()
        self.current_model = preferred
        try:
            self.cfg.set("default_model", preferred)
        except Exception:
            pass
        if preferred == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            return
        if not getattr(self, "model", None):
            self.set_model_status(f"待识别时加载 ({preferred})")
            return
        if self.model.is_model_ready(preferred):
            self.set_model_status("已加载")
        elif preferred.startswith("mathcraft") and getattr(self.model, "_import_failed", False):
            self.set_model_status(f"加载失败 ({preferred})")
        else:
            self.set_model_status(f"待识别时加载 ({preferred})")

    def refresh_status_label(self):
        model_display = self._get_status_model_display_name()
        base = f"当前模型: {model_display} | 状态: {self.model_status}"
        lbl = getattr(self, "status_label", None)
        if lbl is None:
            return
        lbl.setText(base)

    def _apply_formula_label_theme(self, lbl: QLabel):
        if lbl is None:
            return
        t = _formula_label_theme_tokens()
        lbl.setToolTip("点击加载到编辑器并渲染")
        lbl.setStyleSheet(
            "QLabel {"
            f"color: {t['text']}; padding: 2px;"
            "}"
        )

    def _history_row_theme_tokens(self) -> dict:
        if _is_dark_ui():
            return {
                "index": "#8ec5ff",
                "name": "#ffb74d",
            }
        return {
            "index": "#1976d2",
            "name": "#f57c00",
        }

    def _apply_history_row_theme(self, row: QWidget):
        if row is None:
            return
        content_lbl = getattr(row, "_content_label", None)
        if isinstance(content_lbl, QLabel):
            self._apply_formula_label_theme(content_lbl)

        t = self._history_row_theme_tokens()
        index_lbl = getattr(row, "_index_label", None)
        if isinstance(index_lbl, QLabel):
            index_lbl.setStyleSheet(
                f"color: {t['index']}; font-weight: bold; font-size: 11px;"
            )

        name_lbl = getattr(row, "_name_label", None)
        if isinstance(name_lbl, QLabel):
            name_lbl.setStyleSheet(
                f"color: {t['name']}; font-size: 10px; margin-right: 4px;"
            )

    def _refresh_history_rows_theme(self):
        if not hasattr(self, "history_layout"):
            return
        row_count = max(0, self.history_layout.count() - 1)  # 最后一个是 stretch
        for i in range(row_count):
            item = self.history_layout.itemAt(i)
            row = item.widget() if item else None
            if isinstance(row, QWidget):
                self._apply_history_row_theme(row)

    def _history_row_index(self, row: QWidget):
        actual_index = getattr(row, "_history_index", None)
        if isinstance(actual_index, int) and 0 <= actual_index < len(self.history):
            return actual_index
        # layout 最后一个是 stretch, 所以有效行数 = count - 1
        total = self.history_layout.count() - 1
        for i in range(total):
            item = self.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w is row:
                return i
        return None
    def _edit_history_row(self, row: QWidget):
        old_latex = getattr(row, "_latex_text", "")
        dlg = EditFormulaDialog(old_latex, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_latex = dlg.value()
        if not new_latex or new_latex == old_latex:
            return

        # 迁移名称和类型到新内容
        if old_latex in self._formula_names:
            self._formula_names[new_latex] = self._formula_names.pop(old_latex)
        if old_latex in self._formula_types:
            self._formula_types[new_latex] = self._formula_types.pop(old_latex)

        # 更新 row 内部文本
        row._latex_text = new_latex
        lbl = getattr(row, "_content_label", None)
        if lbl:
            lbl.setText(new_latex)
            self._apply_formula_label_theme(lbl)
        # 定位并更新 self.history
        idx = self._history_row_index(row)
        if idx is not None and 0 <= idx < len(self.history):
            self.history[idx] = new_latex
            try:
                self.save_history()
            except Exception as e:
                print("[WARN] 保存历史失败:", e)

        # 更新渲染列表中的内容
        for i, (formula, label) in enumerate(self._rendered_formulas):
            if formula == old_latex:
                self._rendered_formulas[i] = (new_latex, label)
        self._refresh_preview()

        self.set_action_status("已更新")
    def _qpixmap_to_pil(self, pixmap):
        buf = QBuffer()
        if not buf.open(QIODevice.OpenModeFlag.ReadWrite):
            raise RuntimeError("QBuffer 打开失败")
        if not pixmap.save(buf, "PNG"):
            raise RuntimeError("QPixmap 保存失败")
        data = bytes(buf.data())
        buf.close()
        return Image.open(BytesIO(data)).convert("RGB")

    def set_model_status(self, msg: str):
        self.model_status = msg
        self.refresh_status_label()

    def set_action_status(self, msg: str, auto_clear_ms: int = 2500, parent=None):
        InfoBar.success(
            title="提示",
            content=msg,
            parent=parent or self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=auto_clear_ms
        )

    def show_status_message(self, msg: str):
        # 模型后台线程回调
        text = str(msg or "").strip()
        if not text:
            return
        if text.startswith("[INFO] MathCraft model cache:"):
            self._show_mathcraft_cache_repair_infobar(text.split(":", 1)[-1].strip())
            return
        # 技术日志保留在运行日志，不污染底部状态文案。
        if text.startswith("["):
            return
        self.set_model_status(text)

    def _mathcraft_profile_for_model(self, model_name: str | None) -> str:
        model = str(model_name or "mathcraft").strip().lower()
        if model == "mathcraft_text":
            return "text"
        if model == "mathcraft_mixed":
            return "mixed"
        return "formula"

    def _mathcraft_required_models_incomplete(self, model_name: str | None) -> bool:
        try:
            from mathcraft_ocr.cache import inspect_model_roots, resolve_model_roots
            from mathcraft_ocr.manifest import load_manifest
            from mathcraft_ocr.profiles import PROFILE_MODEL_IDS

            profile = self._mathcraft_profile_for_model(model_name)
            manifest = load_manifest()
            roots = resolve_model_roots()
            for model_id in PROFILE_MODEL_IDS.get(profile, ()):
                spec = manifest.models.get(model_id)
                if spec is None:
                    return True
                if not inspect_model_roots(roots, spec).complete:
                    return True
            return False
        except Exception:
            return False

    def _should_show_mathcraft_warmup_started_infobar(self, model_name: str | None) -> bool:
        if self._mathcraft_required_models_incomplete(model_name):
            return True
        return not bool(self.cfg.get("mathcraft_warmup_notice_done", False))

    def _show_mathcraft_warmup_started_infobar(self) -> None:
        if self._model_warmup_notice_shown:
            return
        self._model_warmup_notice_shown = True
        try:
            InfoBar.info(
                title="MathCraft OCR 正在预热",
                content="首次预热可能需要下载或初始化模型权重，网速较慢时耗时会更长，请稍候。",
                parent=self._get_infobar_parent(),
                duration=5200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def _show_mathcraft_cache_repair_infobar(self, detail: str = "") -> None:
        if self._model_cache_repair_notice_shown:
            return
        self._model_cache_repair_notice_shown = True
        content = "检测到 MathCraft 模型权重缺失或不完整，正在自动补全。"
        if detail:
            content = f"{content}\n{detail[:180]}"
        try:
            InfoBar.warning(
                title="正在修复模型缓存",
                content=content,
                parent=self._get_infobar_parent(),
                duration=6500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    # ---------- 实时渲染相关 ----------
    def _on_editor_text_changed(self):
        """编辑器文本变化时触发，使用防抖延迟渲染"""
        if self._render_timer:
            self._render_timer.stop()
            self._render_timer.start(300)  # 300ms 防抖

    def _set_editor_text_silent(self, text: str) -> None:
        """设置编辑器内容但不触发实时渲染（避免重复渲染）。"""
        if not self.latex_editor:
            return
        if self._render_timer:
            self._render_timer.stop()
        try:
            was_blocked = self.latex_editor.blockSignals(True)
            self.latex_editor.setPlainText(text)
        finally:
            try:
                self.latex_editor.blockSignals(was_blocked)
            except Exception:
                pass

    def _do_render_latex(self):
        """执行实时渲染"""
        self._refresh_preview()

    def _build_preview_latex_cache_key(self, latex_code: str) -> str:
        try:
            from backend.latex_renderer import _latex_settings
            mode = _latex_settings.get_render_mode() if _latex_settings else "latex_pdflatex"
        except Exception:
            mode = "latex_pdflatex"
        return f"{str(mode or '').strip()}|{str(latex_code or '').strip()}"

    def _namespace_preview_svg_ids(self, svg: str, namespace: str) -> str:
        text = str(svg or "")
        ns = re.sub(r"[^0-9A-Za-z_]+", "_", str(namespace or "").strip())
        if not text or not ns:
            return text

        id_pattern = re.compile(r'\bid="([^"]+)"')
        ids = id_pattern.findall(text)
        if not ids:
            return text

        mapping = {old: f"{ns}_{old}" for old in ids}
        for old, new in mapping.items():
            text = re.sub(rf'\bid="{re.escape(old)}"', f'id="{new}"', text)
            text = re.sub(rf'url\(#({re.escape(old)})\)', f'url(#{new})', text)
            text = re.sub(rf'(["\'])#({re.escape(old)})(["\'])', rf'\1#{new}\3', text)
        return text

    def _ensure_preview_latex_render_worker(self):
        if self._preview_render_thread and self._preview_render_worker:
            return
        self._preview_render_thread = QThread(self)
        self._preview_render_worker = PreviewLatexRenderWorker()
        self._preview_render_worker.moveToThread(self._preview_render_thread)
        self._preview_latex_render_request.connect(self._preview_render_worker.render_formula)
        self._preview_render_worker.finished.connect(self._on_preview_latex_render_finished)
        self._preview_render_thread.start()

    def _schedule_preview_latex_render(self, latex_code: str):
        text = str(latex_code or "").strip()
        if not text:
            return None
        cache_key = self._build_preview_latex_cache_key(text)
        if cache_key in self._preview_svg_cache or cache_key in self._preview_svg_pending:
            return cache_key
        self._ensure_preview_latex_render_worker()
        self._preview_svg_pending.add(cache_key)
        self._preview_latex_render_request.emit(cache_key, text)
        return cache_key

    def _on_preview_latex_render_finished(self, cache_key: str, svg: object):
        key = str(cache_key or "")
        if not key:
            return
        self._preview_svg_pending.discard(key)
        self._preview_svg_cache[key] = str(svg) if svg else ""
        try:
            self._refresh_preview()
        except Exception:
            pass

    def _copy_editor_content(self):
        """复制编辑器内容到剪贴板"""
        text = self.latex_editor.toPlainText().strip()
        if not text:
            self.set_action_status("编辑器为空")
            return
        try:
            QApplication.clipboard().setText(text)
            self.set_action_status("已复制公式")
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(text)
                self.set_action_status("已复制公式")
            except Exception:
                self.set_action_status("复制失败")

    def _add_editor_to_fav(self):
        """将编辑器内容添加到收藏夹"""
        text = self.latex_editor.toPlainText().strip()
        if not text:
            self.set_action_status("编辑器为空")
            return
        content_type = None
        try:
            if hasattr(self, "_formula_types") and text in self._formula_types:
                content_type = self._formula_types.get(text)
        except Exception:
            content_type = None
        if not content_type:
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
        if not content_type:
            content_type = getattr(self, "current_model", "mathcraft")
        self._ensure_favorites_window().add_favorite(text, content_type=content_type)

    def _show_export_menu(self):
        """显示导出格式菜单"""
        self._show_export_menu_for_source(
            self.export_btn,
            lambda: self.latex_editor.toPlainText(),
            empty_hint="编辑器为空",
        )

    def _show_export_menu_for_source(self, anchor_widget, text_source, empty_hint: str = "内容为空", info_parent=None):
        """在指定控件下方显示导出菜单，支持编辑器和结果对话框复用。"""
        def _current_text() -> str:
            try:
                if callable(text_source):
                    return (text_source() or "").strip()
            except Exception:
                return ""
            return (str(text_source) if text_source is not None else "").strip()

        text = _current_text()
        if not text:
            self.set_action_status(empty_hint, parent=info_parent)
            return

        def _export_current(format_type: str):
            current = _current_text()
            if not current:
                self.set_action_status(empty_hint, parent=info_parent)
                return
            self._export_as(format_type, current, info_parent=info_parent)

        menu = CenterMenu(parent=self)
        menu.addAction(Action("LaTeX (行内 $...$)", triggered=lambda: _export_current("latex")))
        menu.addAction(Action("LaTeX (display \\[...\\])", triggered=lambda: _export_current("latex_display")))
        menu.addAction(Action("LaTeX (equation 编号)", triggered=lambda: _export_current("latex_equation")))
        menu.addSeparator()
        menu.addAction(Action("Markdown (行内 $...$)", triggered=lambda: _export_current("markdown_inline")))
        menu.addAction(Action("Markdown (块级 $$...$$)", triggered=lambda: _export_current("markdown_block")))
        menu.addSeparator()
        menu.addAction(Action("MathML", triggered=lambda: _export_current("mathml")))
        menu.addAction(Action("MathML (.mml)", triggered=lambda: _export_current("mathml_mml")))
        menu.addAction(Action("MathML (<m>)", triggered=lambda: _export_current("mathml_m")))
        menu.addAction(Action("MathML (attr)", triggered=lambda: _export_current("mathml_attr")))
        menu.addSeparator()
        menu.addAction(Action("HTML", triggered=lambda: _export_current("html")))
        menu.addAction(Action("Word OMML", triggered=lambda: _export_current("omml")))
        menu.addAction(Action("SVG Code", triggered=lambda: _export_current("svgcode")))

        if anchor_widget:
            pos = anchor_widget.mapToGlobal(anchor_widget.rect().bottomLeft())
        else:
            pos = self.mapToGlobal(self.rect().center())
        menu.exec(pos)

    def _export_as(self, format_type: str, latex: str, info_parent=None):
        """导出公式为指定格式（支持多种格式）"""
        result = ""
        format_name = ""
        clean = _normalize_latex_for_export(latex)

        if format_type == "latex":
            result = _latex_inline(clean)
            format_name = "LaTeX (行内)"

        elif format_type == "latex_display":
            result = _latex_display(clean)
            format_name = "LaTeX (display \\[\\])"

        elif format_type == "latex_equation":
            result = _latex_equation(clean)
            format_name = "LaTeX (equation)"

        elif format_type == "html":
            # HTML 格式，可在网页中使用
            try:
                result = _mathml_to_html_fragment(self._latex_to_mathml(clean))
            except Exception as e:
                self.set_action_status(f"HTML 导出失败: {e}", parent=info_parent)
                return
            format_name = "HTML"

        elif format_type == "markdown_inline":
            # 修复：使用标准 Markdown 行内公式格式
            result = _latex_inline(clean)
            format_name = "Markdown 行内"

        elif format_type == "markdown_block":
            # 修复：使用标准 Markdown 块级公式格式（双美元符号）
            result = f"$$\n{clean}\n$$"
            format_name = "Markdown 块级"

        elif format_type == "mathml":
            try:
                result = self._latex_to_mathml(clean)
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}", parent=info_parent)
                return
            format_name = "MathML"

        elif format_type == "mathml_mml":
            # MathML 带 .mml 扩展名格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "mml")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}", parent=info_parent)
                return
            format_name = "MathML (.mml)"

        elif format_type == "mathml_m":
            # MathML 数学元素格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "m")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}", parent=info_parent)
                return
            format_name = "MathML (<m>)"

        elif format_type == "mathml_attr":
            # MathML 属性格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "attr")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}", parent=info_parent)
                return
            format_name = "MathML (attr)"

        elif format_type == "omml":
            try:
                result = self._latex_to_omml(clean)
            except Exception as e:
                self.set_action_status(f"OMML 导出失败: {e}", parent=info_parent)
                return
            format_name = "Word OMML"

        elif format_type == "svgcode":
            # SVG 代码格式
            try:
                result = self._latex_to_svg_code(clean)
            except Exception as e:
                self.set_action_status(f"SVG 导出失败: {e}", parent=info_parent)
                return
            format_name = "SVG Code"

        if result:
            try:
                QApplication.clipboard().setText(result)
                self.set_action_status(f"已复制 {format_name} 格式", parent=info_parent)
            except Exception:
                try:
                    import pyperclip
                    pyperclip.copy(result)
                    self.set_action_status(f"已复制 {format_name} 格式", parent=info_parent)
                except Exception:
                    self.set_action_status("复制失败", parent=info_parent)

    def _latex_to_svg_code(self, latex: str) -> str:
        """将 LaTeX 转换为 SVG 代码"""
        return latex_to_svg(latex)

    def _latex_to_mathml(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 格式（使用 latex2mathml 库）"""
        latex = _normalize_latex_for_export(latex)
        import latex2mathml.converter
        mathml = latex2mathml.converter.convert(latex)
        return _mathml_standardize(mathml)

    def _latex_to_mathml_element(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML <m> 元素格式"""
        return _mathml_with_prefix(self._latex_to_mathml(latex), "m")

    def _latex_to_mathml_with_attr(self, latex: str) -> str:
        """将 LaTeX 转换为 MathML 属性格式（用于 HTML 属性）"""
        return _mathml_with_prefix(self._latex_to_mathml(latex), "attr")

    def _latex_to_omml(self, latex: str) -> str:
        """将 LaTeX 转换为 Office Math Markup Language (OMML) 格式
        
        OMML 是 Microsoft Office 使用的公式格式，可以直接粘贴到 Word 中。
        """
        try:
            latex = _normalize_latex_for_export(latex)
            import latex2mathml.converter
            # 获取标准 MathML 输出
            mathml = latex2mathml.converter.convert(latex)
            
            # 尝试使用 lxml 转换为 OMML
            try:
                from lxml import etree
                import os
                
                # 加载 MML2OMML.XSL 转换样式表（Office 自带）
                xsl_paths = [
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office19\MML2OMML.XSL"),
                ]
                
                xsl_path = None
                for p in xsl_paths:
                    if os.path.exists(p):
                        xsl_path = p
                        break
                
                if xsl_path:
                    xsl_doc = etree.parse(xsl_path)
                    transform = etree.XSLT(xsl_doc)
                    mathml_doc = etree.fromstring(mathml.encode('utf-8'))
                    omml_doc = transform(mathml_doc)
                    result = etree.tostring(omml_doc, encoding='unicode')
                    # 返回 OMML 结果（通常是 <m:oMath> 标签）
                    return result if result else mathml
            except Exception:
                # 如果转换失败，返回 MathML（Word 也支持）
                return mathml
            
        except ImportError:
            # 没有 latex2mathml，尝试返回 Word 域代码格式
            escaped = latex.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            # Word 域代码格式：{ EQ ... }
            return f"{{ EQ \\\\o\\\\al(\\\\lc\\\\(({escaped})\\\\rc\\\\))"
        except Exception:
            raise

    def render_latex_in_preview(self, latex: str, label: str = None):
        """渲染指定的 LaTeX 公式到预览区域（点击历史记录时添加到列表）"""
        if not self.preview_view:
            return
        latex = latex.strip()
        if not latex:
            return
        # 跳过重复渲染相同公式
        existing_formulas = [f for f, _ in self._rendered_formulas]
        if latex in existing_formulas:
            return
        # 如果没有记录类型，使用当前模式作为默认类型
        if hasattr(self, "_formula_types") and latex not in self._formula_types:
            self._formula_types[latex] = getattr(self, "current_model", "mathcraft")
        # 获取公式名称
        if label is None:
            label = self._formula_names.get(latex, "")
        # 添加到已渲染列表最前面
        self._rendered_formulas.insert(0, (latex, label))
        # 限制最多显示 20 个公式
        if len(self._rendered_formulas) > 20:
            self._rendered_formulas = self._rendered_formulas[:20]
        
        # 渲染
        self._refresh_preview()
    
    def _refresh_preview(self):
        """刷新预览区域 - 根据每条记录的类型进行智能渲染"""
        if not self.preview_view:
            return
        
        # 构建公式列表、标签和类型
        all_items = []  # [(formula, label, content_type), ...]
        
        # 编辑器内容（如果有且不在已渲染列表中）
        editor_text = self.latex_editor.toPlainText().strip()
        existing_formulas = [f for f, _ in self._rendered_formulas]
        if editor_text and editor_text not in existing_formulas:
            # 编辑中的内容使用当前模式
            current_mode = getattr(self, "current_model", "mathcraft")
            all_items.append((editor_text, "编辑中", current_mode))
        
        # 已渲染的公式列表 - 使用各自存储的类型
        for formula, label in self._rendered_formulas:
            content_type = self._formula_types.get(formula, "mathcraft")  # 默认公式模式
            all_items.append((formula, label, content_type))
        
        try:
            # 构建智能渲染的 HTML
            html = self._build_smart_preview_html(all_items)
            base_url = _get_mathjax_base_url()
            self.preview_view.setHtml(html, base_url)
        except Exception as e:
            # 在 WebEngine 中显示错误信息
            try:
                tokens = _preview_theme_tokens()
                error_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>⚠️ 公式渲染失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: {tokens['pre_bg']}; color: {tokens['body_text']}; padding: 10px; border-radius: 4px; overflow-x: auto;">{str(e)}</pre>
<p><strong>检查项:</strong></p>
<ul>
<li>MathJax 资源是否存在</li>
<li>资源路径是否正确</li>
<li>PyQt6 WebEngine 是否正常工作</li>
</ul>
</body></html>'''
                self.preview_view.setHtml(error_html, _get_mathjax_base_url())
            except Exception:
                pass  # 显示错误信息也失败了
    
    def _build_smart_preview_html(self, items: list) -> str:
        """根据每条记录的类型构建智能渲染 HTML
        
        Args:
            items: [(content, label, content_type), ...]
        """
        try:
            tokens = _preview_theme_tokens()
            
            if not items:
                return build_math_html("")
            
            # 构建各个内容块
            content_blocks = []
            
            for content, label, content_type in items:
                block_html = self._render_content_block(content, label, content_type)
                content_blocks.append(block_html)
            
            body_content = "\n".join(content_blocks)
            
            # 构建完整 HTML
            mathjax_config = '''
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$','$'], ['\\(','\\)']],
    displayMath: [['$$','$$'], ['\\[','\\]']],
    processEscapes: true
  },
  svg: {
    fontCache: 'global',
    scale: 1
  },
  options: {
    enableMenu: false,
    processHtmlClass: 'formula-content'
  }
};
</script>
<!-- 本地 MathJax 加载（使用相对路径） -->
<script src="tex-mml-chtml.js" type="text/javascript"></script>'''
            
            return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
{mathjax_config}
<style>
body {{ 
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    padding: 16px; 
    line-height: 1.6;
    background: {tokens['body_bg']};
    color: {tokens['body_text']};
}}
.content-block {{
    margin-bottom: 16px;
    padding: 12px;
    background: {tokens['panel_bg']};
    border-radius: 8px;
    border-left: 4px solid {tokens['border_formula']};
}}
.content-block.text-type {{
    border-left-color: {tokens['border_text']};
}}
.content-block.table-type {{
    border-left-color: {tokens['border_table']};
}}
.content-block.mixed-type {{
    border-left-color: {tokens['border_mixed']};
}}
.block-label {{
    font-size: 12px;
    color: {tokens['muted_text']};
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.type-badge {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: {tokens['badge_formula_bg']};
    color: {tokens['badge_formula_text']};
}}
.type-badge.text {{ background: {tokens['badge_text_bg']}; color: {tokens['badge_text_text']}; }}
.type-badge.table {{ background: {tokens['badge_table_bg']}; color: {tokens['badge_table_text']}; }}
.type-badge.mixed {{ background: {tokens['badge_mixed_bg']}; color: {tokens['badge_mixed_text']}; }}
.block-content {{
    font-size: 14px;
    text-align: center;
}}
.formula-content {{
    text-align: center;
    padding: 0.15em 0.35em;
    margin: 0.05em 0;
    display: inline-block;
    max-width: 100%;
    box-sizing: border-box;
}}
.formula-content img,
.formula-content svg {{
    max-width: 100%;
    height: auto;
    vertical-align: middle;
    display: block;
    margin: 0 auto;
}}
.formula-content.latex-svg svg {{
    display: block;
    margin: 0 auto;
    max-width: calc(100% / 1.25);
    height: auto;
    transform: scale(1.25);
    transform-origin: center center;
}}
.formula-content.latex-svg {{
    color: {tokens['latex_formula_text']};
    padding-top: 0.25em;
    padding-bottom: 0.25em;
}}
.formula-content.latex-svg svg[fill]:not([fill="none"]),
.formula-content.latex-svg svg *[fill]:not([fill="none"]) {{
    fill: currentColor !important;
}}
.formula-content.latex-svg svg[stroke]:not([stroke="none"]),
.formula-content.latex-svg svg *[stroke]:not([stroke="none"]) {{
    stroke: currentColor !important;
}}
.formula-content.latex-svg svg[style*="fill:"]:not([style*="fill:none"]):not([style*="fill: none"]),
.formula-content.latex-svg svg *[style*="fill:"]:not([style*="fill:none"]):not([style*="fill: none"]) {{
    fill: currentColor !important;
}}
.formula-content.latex-svg svg[style*="stroke:"]:not([style*="stroke:none"]):not([style*="stroke: none"]),
.formula-content.latex-svg svg *[style*="stroke:"]:not([style*="stroke:none"]):not([style*="stroke: none"]) {{
    stroke: currentColor !important;
}}
.text-content {{
    white-space: pre-wrap;
    word-wrap: break-word;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0;
}}
th, td {{
    border: 1px solid {tokens['table_border']};
    padding: 8px;
    text-align: left;
}}
th {{
    background-color: {tokens['th_bg']};
}}
.MathJax {{ font-size: 1.4em; }}
.formula-content mjx-container,
.block-content mjx-container {{
    font-size: 140% !important;
}}
</style>
</head>
<body>{body_content}</body>
</html>'''
        except Exception as e:
            # 返回错误提示 HTML
            tokens = _preview_theme_tokens()
            return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: {tokens['error_text']}; background: {tokens['body_bg']}; padding: 20px; font-family: sans-serif;">
<h3>⚠️ HTML 构建失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: {tokens['pre_bg']}; color: {tokens['body_text']}; padding: 10px; border-radius: 4px; overflow-x: auto;">{str(e)}</pre>
</body></html>'''
    
    def _render_content_block(self, content: str, label: str, content_type: str) -> str:
        """渲染单个内容块"""
        import html as html_module
        
        try:
            # 确保参数是正确的类型
            if content is None:
                content = ""
            else:
                content = str(content)
            
            if label is None:
                label = ""
            else:
                label = str(label)
            
            if content_type is None:
                content_type = "mathcraft"
            else:
                content_type = str(content_type)
            
            if not getattr(sys, "frozen", False):
                print(f"[RenderBlock] 处理内容块: type={content_type}, label_len={len(label)}, content_len={len(content)}")
            
            # 类型显示名称和样式
            content_type = normalize_content_type(content_type)
            type_info = {
                "mathcraft": ("公式", ""),
                "mathcraft_text": ("文字", "text"),
                "mathcraft_mixed": ("混合", "mixed"),
            }
            
            type_name, type_class = type_info.get(content_type, ("内容", ""))
            block_class = f"content-block {type_class}-type" if type_class else "content-block"
            badge_class = f"type-badge {type_class}" if type_class else "type-badge"
            
            # 根据类型渲染内容
            if content_type == "mathcraft":
                # 公式模式：根据当前选择的渲染引擎来渲染
                try:
                    from backend.latex_renderer import _latex_settings
                    if _latex_settings:
                        mode = _latex_settings.get_render_mode()
                        # 如果选择了 LaTeX 渲染，使用 LaTeX 渲染
                        if mode and mode.startswith("latex_"):
                            cache_key = self._build_preview_latex_cache_key(content)
                            if cache_key in self._preview_svg_cache:
                                svg = self._preview_svg_cache.get(cache_key) or ""
                                if svg:
                                    safe_svg = self._namespace_preview_svg_ids(svg, cache_key)
                                    rendered_content = f'<div class="formula-content latex-svg">{safe_svg}</div>'
                                else:
                                    rendered_content = f'<div class="formula-content">$${content}$$</div>'
                            else:
                                self._schedule_preview_latex_render(content)
                                rendered_content = f'<div class="formula-content">$${content}$$</div>'
                        else:
                            # 使用 MathJax 渲染
                            rendered_content = f'<div class="formula-content">$${content}$$</div>'
                    else:
                        # 没有设置，使用 MathJax
                        rendered_content = f'<div class="formula-content">$${content}$$</div>'
                except Exception:
                    # 异常处理，使用 MathJax
                    rendered_content = f'<div class="formula-content">$${content}$$</div>'
            elif content_type == "mathcraft_mixed":
                # 混合模式：文字和公式混合，由 MathJax 处理
                rendered_content = self._render_mixed_content(content)
            else:
                # 文字模式
                escaped = html_module.escape(content)
                rendered_content = f'<div class="text-content">{escaped}</div>'
            
            result = f'''<div class="{block_class}">
    <div class="block-label">
        <span>{html_module.escape(label or "")}</span>
        <span class="{badge_class}">{type_name}</span>
    </div>
    <div class="block-content">{rendered_content}</div>
</div>'''
            if not getattr(sys, "frozen", False):
                print(f"[RenderBlock] 渲染成功，输出长度: {len(result)}")
            return result
        except Exception as e:
            print(f"[RenderBlock] 处理内容块失败: {e}")
            import traceback
            traceback.print_exc()
            # 返回错误提示
            error_msg = f"内容块渲染失败: {str(e)}"
            tokens = _preview_theme_tokens()
            return (
                f'<div style="color: {tokens["error_text"]}; padding: 10px; '
                f'background: {tokens["error_bg"]}; border-radius: 4px;">{html_module.escape(error_msg)}</div>'
            )
    
    def _render_mixed_content(self, content: str) -> str:
        """渲染混合内容（文字和公式混合，由 MathJax 统一处理）"""
        import html as html_module
        import re
        
        try:
            if not content:
                return ""
            
            # 提取并保护公式部分
            # 先匹配块级公式 $$...$$，再匹配行内公式 $...$
            formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'
            parts = re.split(formula_pattern, content)
            result_parts = []
            
            for part in parts:
                if not part:
                    continue
                if part.startswith('$$') and part.endswith('$$'):
                    result_parts.append(part)  # 块级公式保持原样
                elif part.startswith('$') and part.endswith('$'):
                    result_parts.append(part)  # 行内公式保持原样
                else:
                    # 普通文本转义并保留换行
                    escaped = html_module.escape(part).replace('\n', '<br>')
                    result_parts.append(escaped)
            
            return ''.join(result_parts)
        except Exception as e:
            print(f"[RenderMixed] 混合内容渲染失败: {e}")
            return f'<div style="color: red;">{html_module.escape(f"混合内容渲染失败: {str(e)}")}</div>'

    def _render_table_content(self, content: str) -> str:
        """渲染表格内容"""
        import html as html_module

        try:
            if not content:
                return ""
            
            if '<table' in content.lower():
                return content  # 已经是 HTML 表格
            else:
                # Markdown 或纯文本表格
                return f'<pre>{html_module.escape(content)}</pre>'
        except Exception as e:
            print(f"[RenderTable] 表格内容渲染失败: {e}")
            return f'<div style="color: red;">{html_module.escape(f"表格渲染失败: {str(e)}")}</div>'

    def _clear_preview(self):
        """清空预览区域的公式列表"""
        self._rendered_formulas = []
        self._refresh_preview()
        self.set_action_status("已清空预览")
    
    def _add_preview_to_history(self):
        """将预览中的公式添加到历史记录（继承标签）"""
        if not self._rendered_formulas:
            self.set_action_status("预览中没有公式")
            return
        
        added_count = 0
        for formula, label in self._rendered_formulas:
            if formula and formula not in self.history:
                # 添加到历史
                self.history.insert(0, formula)
                # 继承或补充类型（避免默认成 mathcraft）
                if hasattr(self, "_formula_types"):
                    if formula not in self._formula_types:
                        self._formula_types[formula] = getattr(self, "current_model", "mathcraft")
                # 继承标签（提取名称部分）
                if label:
                    # 标签格式可能是 "#1 名称" 或纯名称
                    name = label.strip()
                    if name.startswith('#'):
                        # 提取 # 后面的名称部分
                        parts = name.split(' ', 1)
                        if len(parts) > 1:
                            name = parts[1].strip()
                        else:
                            name = ""  # 只有编号，没有名称
                    if name:
                        self._formula_names[formula] = name
                added_count += 1
        
        if added_count > 0:
            self.save_history()
            self.rebuild_history_ui()
            self.set_action_status(f"已添加 {added_count} 个公式到历史")
        else:
            self.set_action_status("公式已在历史中")

    def _history_display_entries(self):
        entries = list(enumerate(self.history))
        if self.history_reverse:
            entries.reverse()
        return [
            (display_index + 1, history_index, text)
            for display_index, (history_index, text) in enumerate(entries)
        ]

    def _refresh_history_order_button(self):
        if not hasattr(self, "history_order_button"):
            return
        if self.history_reverse:
            self.history_order_button.setText("最新在前")
            self.history_order_button.setToolTip("当前按最新记录在前显示，点击切换为最早在前")
        else:
            self.history_order_button.setText("最早在前")
            self.history_order_button.setToolTip("当前按最早记录在前显示，点击切换为最新在前")

    def toggle_history_order(self):
        self.history_reverse = not bool(getattr(self, "history_reverse", False))
        self.cfg.set("history_reverse", self.history_reverse)
        self._refresh_history_order_button()
        self.rebuild_history_ui()

    def rebuild_history_ui(self):
        for i in reversed(range(self.history_layout.count() - 1)):
            item = self.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                self.history_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
        for display_index, history_index, text in self._history_display_entries():
            self.history_layout.insertWidget(
                self.history_layout.count() - 1,
                self.create_history_row(text, display_index, history_index),
            )
        self._refresh_history_order_button()
        self.update_history_ui()

    def _row_is_alive(self, row):
        if not row:
            return False
        if getattr(row, "_deleted", False):
            return False
        if sip and hasattr(sip, "isdeleted"):
            if sip.isdeleted(row):
                return False
        # 已被脱离父容器也视为无效
        if row.parent() is None:
            return False
        return True

    def _safe_row_text(self, row):
        if not self._row_is_alive(row):
            return ""
        return (getattr(row, "_latex_text", "") or "").strip()

    def _do_copy_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("内容不存在")
            return
        try:
            QApplication.clipboard().setText(txt)
            self.set_action_status("已复制")
        except Exception:
            try:
                pyperclip.copy(txt)
                self.set_action_status("已复制")
            except Exception:
                self.set_action_status("复制失败")

    def _do_fav_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("内容不存在")
            return
        content_type = None
        try:
            if hasattr(self, "_formula_types"):
                content_type = self._formula_types.get(txt)
        except Exception:
            content_type = None
        if not content_type:
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
        if not content_type:
            content_type = getattr(self, "current_model", "mathcraft")
        self._ensure_favorites_window().add_favorite(txt, content_type=content_type)

    def _do_delete_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("已删除（空）")
            return
        # 不标记 _deleted，直接调用
        self.delete_history_item(row, txt)

    def create_history_row(self, t: str, index: int = 0, history_index: int | None = None):
        row = QWidget(self.history_container)
        row._latex_text = t
        row._index = index
        row._history_index = history_index
        row._deleted = False
        row._index_label = None
        hl = QHBoxLayout(row)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(6)
        
        # 编号标签
        if index > 0:
            num_lbl = QLabel(f"#{index}")
            num_lbl.setFixedWidth(35)
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            row._index_label = num_lbl
            hl.addWidget(num_lbl)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        
        # 公式名称（如果有）
        formula_name = self._formula_names.get(t, "")
        if formula_name:
            name_lbl = QLabel(f"[{formula_name}]")
            name_lbl.setWordWrap(True)
            name_lbl.setMinimumWidth(0)
            name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            text_col.addWidget(name_lbl)
            row._name_label = name_lbl
        else:
            row._name_label = None
        
        lbl = QLabel(t)
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        # 优化字体显示
        from PyQt6.QtGui import QFont
        label_font = QFont("Consolas", 9)
        label_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        lbl.setFont(label_font)
        text_col.addWidget(lbl)
        hl.addLayout(text_col, 1)
        row._content_label = lbl
        self._apply_history_row_theme(row)

        # 点击标签时加载到编辑器（仅左键）
        import weakref
        from PyQt6.QtCore import Qt as QtCore_Qt
        row_ref = weakref.ref(row)
        def _load_to_editor(event):
            # 仅左键点击时触发加载和渲染
            if event.button() != QtCore_Qt.MouseButton.LeftButton:
                return
            r = row_ref()
            if not self._row_is_alive(r):
                return
            txt = self._safe_row_text(r)
            if txt:
                self._set_editor_text_silent(txt)
                # 获取编号和名称作为标签
                idx = getattr(r, '_index', 0)
                name = self._formula_names.get(txt, "")
                if name:
                    label = f"#{idx} {name}"
                elif idx > 0:
                    label = f"#{idx}"
                else:
                    label = ""
                self.render_latex_in_preview(txt, label)
                self.set_action_status("已加载到编辑器")
        lbl.mousePressEvent = _load_to_editor

        def add_btn(text, tip, handler, icon):
            b = PushButton(icon, text)
            b.setToolTip(tip)
            b.setFixedSize(85, 30)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row_ref2 = weakref.ref(row)

            def _wrapped():
                r = row_ref2()
                if not self._row_is_alive(r):
                    return
                handler(r)

            b.clicked.connect(_wrapped)
            hl.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            return b

        add_btn("复制", "复制到剪贴板", self._do_copy_row, FluentIcon.COPY)
        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def _ctx(pos):
            self._show_history_context_menu(row, row.mapToGlobal(pos))

        row.customContextMenuRequested.connect(_ctx)
        return row
    def add_history_record(self, text: str, content_type: str = None):
        t = (text or "").strip()
        if not t:
            return
        # 确定内容类型（如果没指定，使用当前模型）
        if content_type is None:
            content_type = getattr(self, "current_model", "mathcraft")
        self._formula_types[t] = normalize_content_type(content_type)
        # 允许重复；如需“去重并上浮”可替换为： if t in self.history: self.history.remove(t)
        self.history.append(t)
        # 限制长度
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
        self.save_history()
        self.rebuild_history_ui()
        self.set_action_status("已加入历史")
        print(f"[HistoryAdd] total={len(self.history)} type={content_type} last='{t[:60]}'")
    def load_history(self):
        if not os.path.exists(self.history_path):
            return
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                history_list = data.get("history", [])
                self.history = [str(x) for x in history_list if isinstance(x, (str, int, float))]
                # 加载公式名称
                formula_names = data.get("formula_names", {})
                if isinstance(formula_names, dict):
                    self._formula_names = {str(k): str(v) for k, v in formula_names.items()}
                # 加载公式类型
                formula_types = data.get("formula_types", {})
                if isinstance(formula_types, dict):
                    self._formula_types = {
                        str(k): normalize_content_type(str(v))
                        for k, v in formula_types.items()
                    }
        except Exception as e:
            print("加载历史失败:", e)
            self.history = []
        self.rebuild_history_ui()

    def delete_history_item(self, widget, text):
        print(f"[Delete] request text='{text}' history_len={len(self.history)}")
        if text in self.history:
            self.history.remove(text)
        if widget:
            # 即使之前被标记 _deleted 也强制移除
            try:
                if self.history_layout.indexOf(widget) != -1:
                    self.history_layout.removeWidget(widget)
            except Exception:
                pass
            widget.setParent(None)
            widget.deleteLater()
        self.save_history()
        self.set_action_status("已删除")
        self.update_history_ui()
    def update_history_ui(self):
        self.clear_history_button.setText("清空历史记录")
        if self.history:
            # 有历史
            self.clear_history_button.setToolTip("清空所有历史记录")
        else:
            # 无历史但仍可点，点击会弹出提示（逻辑已在 clear_history 内）
            self.clear_history_button.setToolTip("当前无历史记录，点击会提示")
        # 始终保持可点
        self.clear_history_button.setEnabled(True)

    def save_history(self):
        try:
            # 保存历史记录、公式名称和公式类型
            data = {
                "history": self.history,
                "formula_names": self._formula_names,
                "formula_types": self._formula_types
            }
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("历史保存失败:", e)

    # ---------- 模型/预测 ----------
    def _get_infobar_parent(self):
        try:
            if self.settings_window and self.settings_window.isVisible():
                return self.settings_window
        except Exception:
            pass
        return self

    def _report_startup_progress(self, message: str):
        cb = getattr(self, "_startup_progress", None)
        if not callable(cb):
            return
        try:
            cb(str(message or ""))
        except Exception:
            pass

    def apply_app_theme_mode(self, mode: str | None, refresh_preview: bool = True):
        normalized = normalize_theme_mode(mode)
        self._theme_mode = normalized
        try:
            self.cfg.set("theme_mode", normalized)
        except Exception:
            pass
        apply_theme_mode(normalized)
        try:
            self._apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            if getattr(self, "workbench_window", None) and self.workbench_window.isVisible():
                self.workbench_window.apply_theme_styles(force=True)
        except Exception:
            pass
        try:
            global _LSN_RUNTIME_LOG_DIALOG
            if _LSN_RUNTIME_LOG_DIALOG is not None:
                _LSN_RUNTIME_LOG_DIALOG._apply_theme_styles(force=True)
        except Exception:
            pass
        if refresh_preview:
            try:
                self._refresh_preview()
            except Exception:
                pass

    def _sanitize_model_config(self):
        """校验并收敛当前仍支持的模型配置。"""
        try:
            valid_models = {"mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model"}
            default_model = (self.cfg.get("default_model", "") or "").lower()
            desired_model = (self.cfg.get("desired_model", "") or "").lower()
            changed = False
            if default_model not in valid_models:
                self.cfg.set("default_model", "mathcraft")
                changed = True
            if desired_model not in valid_models:
                self.cfg.set("desired_model", "mathcraft")
                changed = True
            mode = (self.cfg.get("mathcraft_mode", "formula") or "formula").lower()
            if mode not in ("formula", "mixed", "text"):
                self.cfg.set("mathcraft_mode", "formula")
                changed = True
            theme_mode = normalize_theme_mode(self.cfg.get("theme_mode", "auto"))
            if self.cfg.get("theme_mode", "auto") != theme_mode:
                self.cfg.set("theme_mode", theme_mode)
                changed = True
            external_defaults = load_config_from_mapping(self.cfg).to_mapping()
            for key, default in external_defaults.items():
                current = self.cfg.get(key, None)
                if current is None:
                    self.cfg.set(key, default)
                    changed = True
            if changed:
                print("[INFO] 已校正当前模型配置。")
        except Exception as e:
            print(f"[WARN] 模型配置校验失败: {e}")

    def _get_preferred_model_for_predict(self) -> str:
        desired = (self.cfg.get("desired_model", "mathcraft") or "mathcraft").lower()
        if desired == "external_model":
            return "external_model"
        mode = (self.cfg.get("mathcraft_mode", "formula") or "formula").lower()
        mode_map = {
            "formula": "mathcraft",
            "mixed": "mathcraft_mixed",
            "text": "mathcraft_text",
        }
        return mode_map.get(mode, "mathcraft")

    def _get_external_model_config(self):
        return load_config_from_mapping(self.cfg)

    def _get_external_model_display_name(self, config=None, result=None) -> str:
        try:
            model_name = str(getattr(result, "model_name", "") or "").strip()
            if model_name:
                return model_name
        except Exception:
            pass
        try:
            if config is None:
                config = self._get_external_model_config()
            model_name = str(getattr(config, "normalized_model_name", lambda: "")() or "").strip()
            if model_name:
                return model_name
            provider = str(getattr(config, "normalized_provider", lambda: "external_model")() or "").strip()
            return provider or "external_model"
        except Exception:
            return "external_model"

    def _is_external_model_configured(self) -> bool:
        cfg = self._get_external_model_config()
        if not cfg.normalized_base_url():
            return False
        if cfg.normalized_provider() == "mineru":
            return bool(cfg.normalized_mineru_endpoint())
        return bool(cfg.normalized_model_name())

    def _get_external_model_required_fields_hint(self) -> str:
        cfg = self._get_external_model_config()
        if cfg.normalized_provider() == "mineru":
            return "请先在设置页填写 Base URL、MinerU 解析接口路径，并点击“测试连接”。"
        return "请先在设置页填写 Base URL、模型名，并点击“测试连接”。"

    def _get_external_model_status_text(self) -> str:
        config = self._get_external_model_config()
        if self._is_external_model_configured():
            model_name = "" if config.normalized_provider() == "mineru" else config.normalized_model_name()
            sig = (
                f"{config.normalized_provider()}|{config.normalized_base_url()}|"
                f"{model_name}|{config.normalized_mineru_endpoint()}"
            )
            tested_sig = str(self.cfg.get("external_model_last_test_signature", "") or "")
            tested_ok = bool(self.cfg.get("external_model_last_test_ok", False))
            if tested_ok and sig == tested_sig:
                return "已连接"
            return "外部模型待连接"
        return "外部模型未配置"

    def _warmup_desired_model(self):
        if not self.model:
            return
        preferred = self._get_preferred_model_for_predict()
        if not preferred:
            return
        if preferred == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            self._report_startup_progress("外部模型模式已启用，跳过 MathCraft 预热")
            return
        self._report_startup_progress("正在后台预热 MathCraft OCR...")
        self._ensure_model_warmup_async(
            preferred_model=preferred,
            announce_success=True,
            success_message="MathCraft OCR 预热完成，可直接识别",
        )

    def _ensure_model_warmup_async(
        self,
        preferred_model: str | None = None,
        on_ready=None,
        on_fail=None,
        announce_success: bool = False,
        success_message: str = "",
    ):
        if not self.model:
            return
        preferred = (preferred_model or self._get_preferred_model_for_predict() or "mathcraft").lower()
        if self.model.is_model_ready(preferred):
            self.current_model = preferred
            self.cfg.set("default_model", preferred)
            self.set_model_status("已加载")
            if callable(on_ready):
                QTimer.singleShot(0, on_ready)
            return

        if callable(on_ready) or callable(on_fail):
            self._model_warmup_callbacks.append((on_ready, on_fail))

        if self._model_warmup_in_progress:
            self.set_model_status(f"预热中 ({preferred})")
            self._report_startup_progress("正在预热 MathCraft OCR...")
            return

        self._model_warmup_in_progress = True
        self._model_warmup_notice_shown = False
        self._model_cache_repair_notice_shown = False
        self.current_model = preferred
        self.cfg.set("default_model", preferred)
        self.desired_model = "mathcraft"
        self.cfg.set("desired_model", "mathcraft")
        try:
            if hasattr(self.model, "set_default_model"):
                self.model.set_default_model(preferred)
        except Exception:
            pass
        self.set_model_status(f"预热中 ({preferred})")
        self._report_startup_progress("正在预热 MathCraft OCR...")
        if self._should_show_mathcraft_warmup_started_infobar(preferred):
            self._show_mathcraft_warmup_started_infobar()

        def worker():
            ok = False
            err = ""
            try:
                self._apply_mathcraft_env()
                ok = bool(self.model._lazy_load_mathcraft())
                if (not ok) and not err:
                    getter = getattr(self.model, "get_error", None)
                    if callable(getter):
                        err = str(getter() or "")
            except Exception as e:
                ok = False
                err = str(e)
            self._pending_model_warmup_result = {
                "ok": ok,
                "err": err,
                "preferred": preferred,
                "announce_success": bool(announce_success),
                "success_message": str(success_message or ""),
                "on_ready": on_ready,
                "on_fail": on_fail,
            }
            self._model_warmup_result_signal.emit()

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _apply_model_warmup_result(self):
        from qfluentwidgets import InfoBar, InfoBarPosition

        data = getattr(self, "_pending_model_warmup_result", None)
        self._pending_model_warmup_result = None
        if not isinstance(data, dict):
            return

        ok = bool(data.get("ok"))
        err = str(data.get("err", "") or "")
        preferred = str(data.get("preferred", self.current_model) or self.current_model)
        announce_success = bool(data.get("announce_success"))
        success_message = str(data.get("success_message", "") or "")
        direct_on_ready = data.get("on_ready")
        direct_on_fail = data.get("on_fail")

        self._model_warmup_in_progress = False
        callbacks = list(self._model_warmup_callbacks)
        self._model_warmup_callbacks.clear()

        if ok:
            self._report_startup_progress("MathCraft OCR 预热完成")
            self.set_model_status("已加载")
            if not bool(self.cfg.get("mathcraft_warmup_notice_done", False)):
                self.cfg.set("mathcraft_warmup_notice_done", True)
            if self.settings_window:
                self.settings_window.update_model_selection()
            if announce_success:
                InfoBar.success(
                        title="模型预热完成",
                        content=success_message or "MathCraft OCR 已就绪",
                    parent=self._get_infobar_parent(),
                    duration=2500,
                    position=InfoBarPosition.TOP
                )
            for cb_ok, _ in callbacks:
                if callable(cb_ok):
                    try:
                        cb_ok()
                    except Exception:
                        pass
            if callable(direct_on_ready) and not callbacks:
                try:
                    direct_on_ready()
                except Exception:
                    pass
            return

        self._report_startup_progress("模型预热未完成，首次识别时重试")
        self.set_model_status(f"未就绪 ({preferred})")
        fail_info = classify_mathcraft_failure(err)
        if announce_success:
            InfoBar.warning(
                title=fail_info["title"] or "模型预热未完成",
                content=fail_info["user_message"] or "MathCraft OCR 预热失败，将在首次识别时重试",
                parent=self._get_infobar_parent(),
                duration=4200,
                position=InfoBarPosition.TOP
            )
        fail_msg = fail_info["user_message"] or err or "MathCraft OCR 模型未部署或加载失败。"
        for _, cb_fail in callbacks:
            if callable(cb_fail):
                try:
                    cb_fail(fail_msg)
                except Exception:
                    pass
        if callable(direct_on_fail) and not callbacks:
            try:
                direct_on_fail(fail_msg)
            except Exception:
                pass

    def on_model_changed(self, model_name: str):
        from qfluentwidgets import InfoBar, InfoBarPosition
        info_parent = self._get_infobar_parent()
        m = (model_name or "").lower()
        valid_modes = ("mathcraft", "mathcraft_text", "mathcraft_mixed", "external_model")
        if m not in valid_modes:
            m = "mathcraft"
        prev_model = str(getattr(self, "current_model", "") or "")
        prev_desired = str(getattr(self, "desired_model", "") or "")
        if m != prev_model and self.is_recognition_busy(source="mode_switch"):
            self._cancel_active_recognition_for_mode_switch()

        # 同一目标模式重复触发时直接刷新状态，避免重复切换导致潜在竞态。
        if m == prev_model:
            if m == "external_model" and prev_desired == "external_model":
                self.set_model_status(self._get_external_model_status_text())
                return
            if m.startswith("mathcraft") and prev_desired == "mathcraft":
                if self.model and self.model.is_model_ready(m):
                    self.set_model_status("已加载")
                else:
                    self.set_model_status(f"待识别时加载 ({m})")
                return

        mode_names = {
            "mathcraft": "MathCraft 公式识别",
            "mathcraft_text": "MathCraft 纯文字识别",
            "mathcraft_mixed": "MathCraft 混合识别",
            "external_model": "外部模型",
        }
        mode_display = mode_names.get(m, m)
        InfoBar.success(
            title="模式切换成功",
            content=f"已切换到 {mode_display}",
            parent=info_parent,
            duration=3000,
            position=InfoBarPosition.TOP
        )

        self.current_model = m
        self.cfg.set("default_model", m)
        self.desired_model = "external_model" if m == "external_model" else "mathcraft"
        self.cfg.set("desired_model", self.desired_model)
        if m.startswith("mathcraft"):
            mode_map = {
                "mathcraft": "formula",
                "mathcraft_mixed": "mixed",
                "mathcraft_text": "text",
            }
            self.cfg.set("mathcraft_mode", mode_map.get(m, "formula"))

        if m == "external_model":
            self.set_model_status(self._get_external_model_status_text())
            if self.settings_window:
                self.settings_window.update_model_selection()
            if not self._is_external_model_configured():
                InfoBar.warning(
                    title="外部模型未配置",
                    content=self._get_external_model_required_fields_hint(),
                    parent=info_parent,
                    duration=5000,
                    position=InfoBarPosition.TOP
                )
            return

        # 根据模型实际状态设置状态文本
        if self.model:
            if self.model.is_model_ready(m):
                self.set_model_status("已加载")
            else:
                self.set_model_status(f"预热中 ({m})")
        else:
            self.set_model_status(f"预热中 ({m})")
            
        # 更新设置窗口选择状态
        if self.settings_window:
            self.settings_window.update_model_selection()

        # mathcraft 模式切换统一延后到首次识别时加载，
        # 避免在设置页频繁切换识别类型触发预热线程并造成不稳定。
        if m.startswith("mathcraft"):
            if self.model and self.model.is_model_ready(m):
                self.set_model_status("已加载")
            else:
                self.set_model_status(f"待识别时加载 ({m})")
            return

    def _get_supported_image_patterns(self):
        """返回图片文件筛选格式列表（用于文件对话框）。"""
        try:
            exts = sorted({ext.lower().lstrip(".") for ext in Image.registered_extensions().keys()})
            common = {"png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "webp"}
            exts = [e for e in exts if e in common] or exts
            patterns = [f"*.{e}" for e in exts if e]
            if patterns:
                return patterns
        except Exception:
            pass
        return ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.tif", "*.tiff", "*.webp"]

    def _get_supported_image_extensions(self):
        """返回可读的图片扩展名列表（用于提示）。"""
        return [p.replace("*.", "").upper() for p in self._get_supported_image_patterns()]

    def _get_supported_image_suffixes(self) -> set[str]:
        return {p.replace("*", "").lower() for p in self._get_supported_image_patterns() if p.startswith("*.")}

    def _local_drop_paths(self, event) -> list[Path]:
        try:
            mime = event.mimeData()
            if mime is None or not mime.hasUrls():
                return []
            paths: list[Path] = []
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                path = Path(url.toLocalFile())
                if path.is_file():
                    paths.append(path)
            return paths
        except Exception:
            return []

    def _drop_file_kind(self, path: Path) -> str | None:
        suffix = str(path.suffix or "").lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix in self._get_supported_image_suffixes():
            return "image"
        return None

    def _drag_contains_local_file(self, event) -> bool:
        return bool(self._local_drop_paths(event))

    def _show_drop_file_warning(self, content: str) -> None:
        try:
            InfoBar.warning(
                title="无法处理拖入文件",
                content=content,
                parent=self,
                duration=3200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("提示", content, self)

    def _enable_file_drop_target(self, widget) -> None:
        if widget is None:
            return
        try:
            widget.setAcceptDrops(True)
        except Exception:
            pass
        try:
            widget.installEventFilter(self)
        except Exception:
            pass

    def dragEnterEvent(self, event):
        if self._drag_contains_local_file(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_contains_local_file(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = self._local_drop_paths(event)
        if len(paths) != 1:
            if paths:
                self._show_drop_file_warning("请一次只拖入一个图片或 PDF 文件。")
                event.acceptProposedAction()
            else:
                img_exts = ", ".join(self._get_supported_image_extensions())
                self._show_drop_file_warning(f"请拖入单个图片或 PDF 文件。支持图片格式：{img_exts}。")
                event.ignore()
            return

        path = paths[0]
        kind = self._drop_file_kind(path)
        if not kind:
            img_exts = ", ".join(self._get_supported_image_extensions())
            self._show_drop_file_warning(f"请拖入单个图片或 PDF 文件。支持图片格式：{img_exts}。")
            event.ignore()
            return

        event.acceptProposedAction()
        if kind == "image":
            self._recognize_image_file(path)
        elif kind == "pdf":
            self._recognize_pdf_file(path)

    def _show_recognition_busy_info(self, content: str = "正在识别，请稍候") -> None:
        try:
            InfoBar.info(
                title="提示",
                content=content,
                parent=self,
                duration=2200,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("提示", content, self)

    def is_recognition_busy(self, source: str = "main") -> bool:
        main_busy = bool(
            getattr(self, "_predict_busy", False)
            or (self.predict_thread and self.predict_thread.isRunning())
            or (self.pdf_predict_thread and self.pdf_predict_thread.isRunning())
        )
        if main_busy:
            return True
        if source != "handwriting":
            try:
                hw = getattr(self, "handwriting_window", None)
                if hw and hasattr(hw, "is_recognizing_busy") and hw.isVisible():
                    return bool(hw.is_recognizing_busy())
            except Exception:
                pass
        return False

    def _cancel_active_recognition_for_mode_switch(self) -> None:
        cancelled = False
        self._recognition_cancel_requested = True
        worker = getattr(self, "predict_worker", None)
        if worker and hasattr(worker, "cancel"):
            try:
                worker.cancel()
                cancelled = True
            except Exception:
                pass
        pdf_worker = getattr(self, "pdf_predict_worker", None)
        if pdf_worker and hasattr(pdf_worker, "cancel"):
            try:
                pdf_worker.cancel()
                cancelled = True
            except Exception:
                pass
        model = getattr(self, "model", None)
        if model and hasattr(model, "_stop_mathcraft_worker"):
            try:
                model._stop_mathcraft_worker()
                cancelled = True
            except Exception:
                pass
        for thread_name in ("predict_thread", "pdf_predict_thread"):
            thread = getattr(self, thread_name, None)
            if thread:
                try:
                    thread.requestInterruption()
                except Exception:
                    pass
                try:
                    thread.quit()
                except Exception:
                    pass
        if cancelled:
            self._predict_busy = False
            self.set_model_status("识别已中断")
            self._show_recognition_cancelled_infobar(reset_cancel_flag=False)

    def _is_user_cancelled_recognition_error(self, msg: str) -> bool:
        text = str(msg or "").strip().lower()
        if bool(getattr(self, "_recognition_cancel_requested", False)):
            return True
        return (
            "cancel" in text
            or "cancelled" in text
            or "canceled" in text
            or "已取消" in text
            or "已中断" in text
        )

    def _show_recognition_cancelled_infobar(self, *, reset_cancel_flag: bool = True) -> None:
        if reset_cancel_flag:
            self._recognition_cancel_requested = False
        self.set_model_status("已中断")
        now = time.monotonic()
        if now - float(getattr(self, "_last_recognition_cancel_notice_at", 0.0) or 0.0) < 2.5:
            return
        self._last_recognition_cancel_notice_at = now
        try:
            InfoBar.info(
                title="识别已中断",
                content="已停止当前识别任务，可重新截图或切换识别类型后再试。",
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            pass

    def _start_predict_with_pil(self, img: Image.Image, external_prompt_template: str | None = None):
        if self.is_recognition_busy(source="main"):
            self._restore_hidden_unpinned_predict_result_dialog()
            self._show_recognition_busy_info()
            return
        if self.current_model == "external_model" or self._get_preferred_model_for_predict() == "external_model":
            self._start_external_predict_with_pil(img, external_prompt_template=external_prompt_template)
            return
        if not self.model:
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        if self.predict_thread and self.predict_thread.isRunning():
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", "前一识别线程尚未结束", self)
            return
        preferred = self._get_preferred_model_for_predict()
        if preferred != self.current_model:
            self.current_model = preferred
        if self.model and not self.model.is_model_ready(preferred):
            self.set_model_status(f"预热中 ({preferred})")
            self.set_action_status("模型预热中，完成后将自动开始识别", auto_clear_ms=2200)
            self._ensure_model_warmup_async(
                preferred_model=preferred,
                on_ready=lambda img=img, template=external_prompt_template: self._start_predict_with_pil(img, template),
                on_fail=lambda msg: self.on_predict_fail(f"模型预热失败: {msg}"),
            )
            return
        active_model = self.current_model
        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status("识别中...")

        self.predict_thread = QThread()
        self.predict_worker = PredictionWorker(self.model, img, active_model)
        self.predict_worker.moveToThread(self.predict_thread)

        def _cleanup():
            self._predict_busy = False
            if self.predict_worker:
                self.predict_worker.deleteLater()
                self.predict_worker = None
            if self.predict_thread:
                self.predict_thread.deleteLater()
                self.predict_thread = None

        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self.on_predict_ok)
        self.predict_worker.failed.connect(self.on_predict_fail)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(_cleanup)
        self.predict_thread.start()

    def _start_external_predict_with_pil(self, img: Image.Image, external_prompt_template: str | None = None):
        if self.predict_thread and self.predict_thread.isRunning():
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", "前一识别线程尚未结束", self)
            return
        config = self._get_external_model_config()
        one_shot_template = str(external_prompt_template or "").strip()
        if one_shot_template:
            config.prompt_template = one_shot_template
        if not self._is_external_model_configured():
            self._restore_hidden_unpinned_predict_result_dialog()
            self.set_model_status("外部模型未配置")
            self.set_action_status("请先在设置中配置外部模型", auto_clear_ms=3000)
            self.open_settings()
            custom_warning_dialog("提示", f"外部模型未配置，{self._get_external_model_required_fields_hint()}", self)
            return
        self.current_model = "external_model"
        self.cfg.set("default_model", "external_model")
        self.cfg.set("desired_model", "external_model")
        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status("外部模型识别中...")
        self.predict_thread = QThread()
        self.predict_worker = ExternalModelWorker(config, img)
        self.predict_worker.moveToThread(self.predict_thread)

        def _cleanup():
            self._predict_busy = False
            if self.predict_worker:
                self.predict_worker.deleteLater()
                self.predict_worker = None
            if self.predict_thread:
                self.predict_thread.deleteLater()
                self.predict_thread = None

        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self._on_external_predict_ok)
        self.predict_worker.failed.connect(self._on_external_predict_fail)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(_cleanup)
        self.predict_thread.start()

    def _open_terminal_from_settings(self, env_key: str | None = None):
        try:
            if not self.settings_window:
                self.settings_window = SettingsWindow(self)
            self.settings_window._open_terminal(env_key=env_key)
        except Exception as e:
            custom_warning_dialog("错误", f"打开终端失败: {e}", self)

    def _apply_mathcraft_env(self):
        env_pyexe = ""
        try:
            # MathCraft 与主依赖环境统一。
            pyexe = (os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip()
            if not pyexe or not os.path.exists(pyexe):
                pyexe = sys.executable
            if pyexe and os.path.exists(pyexe):
                env_pyexe = pyexe
        except Exception:
            pass
        try:
            os.environ.pop("LATEXSNIPPER_SHARED_TORCH_SITE", None)
        except Exception:
            pass
        try:
            new_state = (
                (env_pyexe or os.environ.get("LATEXSNIPPER_PYEXE", "") or "").strip(),
            )
            old_state = getattr(self, "_mathcraft_env_state", None)
            self._mathcraft_env_state = new_state
            old_key = old_state
            new_key = new_state
            if old_state is not None and old_key != new_key:
                self._restart_mathcraft_worker("环境切换")
        except Exception:
            pass

    def _restart_mathcraft_worker(self, reason: str = "环境更新"):
        m = getattr(self, "model", None)
        if not m:
            return
        try:
            if hasattr(m, "_stop_mathcraft_worker"):
                m._stop_mathcraft_worker()
        except Exception:
            pass
        try:
            m._ready = False
            m._import_failed = False
        except Exception:
            pass
        try:
            print(f"[INFO] MathCraft OCR 运行进程已重启: {reason}")
        except Exception:
            pass

    def _upload_image_recognition(self):
        """上传图片并识别公式/文本。"""
        patterns = self._get_supported_image_patterns()
        filter_ = f"图片文件 ({' '.join(patterns)})"
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择图片",
            "",
            f"{filter_};;所有文件 (*.*)",
        )
        if not file_path:
            return
        self._recognize_image_file(Path(file_path))

    def _recognize_image_file(self, file_path: str | Path):
        """Recognize a local image file selected by dialog or dropped onto the window."""
        self._next_predict_result_screen_index = None
        path = Path(file_path)
        if not path.is_file():
            custom_warning_dialog("错误", f"图片文件不存在: {path}", self)
            return
        if self._drop_file_kind(path) != "image":
            img_exts = ", ".join(self._get_supported_image_extensions())
            custom_warning_dialog("提示", f"不支持的图片格式。支持格式：{img_exts}", self)
            return
        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return
        if not self.model and self._get_preferred_model_for_predict() != "external_model":
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        try:
            img = Image.open(path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
        except Exception as e:
            custom_warning_dialog("错误", f"图片加载失败: {e}", self)
            return
        self._start_predict_with_pil(img)

    def _model_supports_pdf(self, model_name: str) -> bool:
        m = (model_name or "").lower()
        return m == "mathcraft_mixed" or m == "external_model"

    def _prompt_pdf_output_options(self):
        """选择 PDF 识别的导出格式与 DPI。"""
        def _pick_item(title: str, label: str, items: list[str], current: int = 0):
            dlg = QInputDialog(self)
            dlg.setWindowTitle(title)
            dlg.setLabelText(label)
            dlg.setComboBoxItems(items)
            dlg.setComboBoxEditable(False)
            if 0 <= current < len(items):
                dlg.setTextValue(items[current])
            dlg.setWindowFlags(
                (
                    dlg.windowFlags()
                    | Qt.WindowType.CustomizeWindowHint
                    | Qt.WindowType.WindowTitleHint
                    | Qt.WindowType.WindowCloseButtonHint
                    | Qt.WindowType.WindowSystemMenuHint
                )
                & ~Qt.WindowType.WindowMinimizeButtonHint
                & ~Qt.WindowType.WindowMaximizeButtonHint
                & ~Qt.WindowType.WindowMinMaxButtonsHint
                & ~Qt.WindowType.WindowContextHelpButtonHint
            )
            dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
            dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
            dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
            dlg.setFixedSize(dlg.sizeHint())
            _apply_app_window_icon(dlg)
            if dlg.exec() != int(QDialog.DialogCode.Accepted):
                return None
            return dlg.textValue()

        doc_mode = "document"
        external_cfg = self._get_external_model_config() if self.current_model == "external_model" else None
        external_provider = external_cfg.normalized_provider() if external_cfg is not None else ""

        if self.current_model == "external_model" and external_provider == "mineru":
            # MinerU PDF flow is parse-only to keep behavior aligned with
            # its markdown-first document parsing capabilities.
            doc_mode = "parse"

        if doc_mode == "parse":
            fmt_key = "markdown"
        else:
            fmt_items = ["Markdown", "LaTeX"]
            fmt = _pick_item("导出格式", "请选择导出格式：", fmt_items, 0)
            if not fmt:
                return None
            fmt_key = "markdown" if fmt.lower().startswith("markdown") else "latex"

        from PyQt6.QtWidgets import QDialogButtonBox, QSlider

        dlg = QDialog(self)
        dlg.setWindowTitle("PDF 渲染分辨率")
        dlg.setWindowFlags(
            (
                dlg.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        _apply_app_window_icon(dlg)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("请选择 PDF 渲染分辨率（DPI）："))

        dpi_label = QLabel()
        dpi_label.setWordWrap(True)
        layout.addWidget(dpi_label)

        slider = QSlider(Qt.Orientation.Horizontal, dlg)
        slider.setRange(90, 300)
        slider.setSingleStep(10)
        slider.setPageStep(10)
        slider.setTickInterval(10)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        default_dpi = 150 if self.current_model == "external_model" else 200
        slider.setValue(default_dpi)
        layout.addWidget(slider)

        tip = QLabel("建议根据文档清晰度动态调整：清晰文档可用较低 DPI，普通文档建议 140-170 DPI，模糊文档可适当提高；过高 DPI 可能降低识别稳定性。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color: {_dialog_theme_tokens()['muted']}; font-size: 11px;")
        layout.addWidget(tip)

        def _refresh_dpi_label(value: int):
            if value < 120:
                zone = "清晰文档"
            elif 140 <= value <= 170:
                zone = "推荐"
            elif value > 220:
                zone = "高 DPI：模糊文档"
            else:
                zone = "可选"
            dpi_label.setText(f"当前 DPI：{value}（{zone}）")

        slider.valueChanged.connect(_refresh_dpi_label)
        _refresh_dpi_label(default_dpi)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        dlg.setFixedSize(420, 180)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return None
        dpi = int(slider.value())
        return fmt_key, dpi, doc_mode

    def _upload_pdf_recognition(self):
        """上传 PDF 并识别（输出 Markdown/LaTeX 文档）。"""
        file_path, _ = _select_open_file_with_icon(
            self,
            "选择 PDF 文件",
            "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)",
        )
        if not file_path:
            return
        self._recognize_pdf_file(Path(file_path))

    def _recognize_pdf_file(self, file_path: str | Path):
        """Recognize a local PDF file selected by dialog or dropped onto the window."""
        self._next_predict_result_screen_index = None
        path = Path(file_path)
        if not path.is_file():
            custom_warning_dialog("错误", f"PDF 文件不存在: {path}", self)
            return
        if self._drop_file_kind(path) != "pdf":
            custom_warning_dialog("提示", "请拖入或选择 PDF 文件。", self)
            return
        if not self.model and self._get_preferred_model_for_predict() != "external_model":
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        preferred = self._get_preferred_model_for_predict()
        try:
            if preferred != self.current_model or (self.model and not self.model.is_model_ready(preferred)):
                self.on_model_changed(preferred)
        except Exception:
            if preferred != self.current_model:
                self.on_model_changed(preferred)
        if self.current_model == "external_model" and not self._is_external_model_configured():
            custom_warning_dialog("提示", "外部模型未配置，请先完成配置并测试连接。", self)
            return
        if self.current_model.startswith("mathcraft") and self.current_model != "mathcraft_mixed":
            from qfluentwidgets import MessageBox
            tip = MessageBox(
                "推荐模式",
                "PDF 识别会使用 MathCraft 混合识别并进行文档整理。\n是否切换并继续？",
                self
            )
            _apply_app_window_icon(tip)
            tip.yesButton.setText("切换并继续")
            tip.cancelButton.setText("取消")
            if tip.exec():
                self.on_model_changed("mathcraft_mixed")
                if not self._model_supports_pdf(self.current_model):
                    custom_warning_dialog("提示", "当前模型仍不支持 PDF 识别。", self)
                    return
            else:
                return
        if not self._model_supports_pdf(self.current_model):
            custom_warning_dialog("提示", "当前模型不支持 PDF 识别。", self)
            return
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            custom_warning_dialog("错误", f"缺少 PyMuPDF 依赖: {e}\n请在依赖环境中安装 pymupdf。", self)
            return
        try:
            doc = fitz.open(str(path))
            total_pages = doc.page_count
            doc.close()
        except Exception as e:
            custom_warning_dialog("错误", f"PDF 打开失败: {e}", self)
            return

        default_pages = min(total_pages, 5) if total_pages > 0 else 1
        page_dlg = QInputDialog(self)
        page_dlg.setWindowTitle("选择页数")
        page_dlg.setLabelText(f"PDF 共 {total_pages} 页，选择要识别的页数：")
        page_dlg.setInputMode(QInputDialog.InputMode.IntInput)
        page_dlg.setIntRange(1, max(total_pages, 1))
        page_dlg.setIntValue(default_pages)
        page_dlg.setIntStep(1)
        page_dlg.setWindowFlags(
            (
                page_dlg.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        page_dlg.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        page_dlg.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        page_dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        page_dlg.setFixedSize(page_dlg.sizeHint())
        _apply_app_window_icon(page_dlg)
        if page_dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        pages = page_dlg.intValue()

        opts = self._prompt_pdf_output_options()
        if not opts:
            return
        fmt_key, dpi, doc_mode = opts
        self._pdf_output_format = fmt_key
        self._pdf_doc_style = doc_mode
        self._pdf_dpi = dpi
        self._pdf_structured_result = None

        if self.is_recognition_busy(source="main"):
            self._show_recognition_busy_info()
            return

        self._recognition_cancel_requested = False
        self._predict_busy = True
        self.set_model_status("识别中...")

        self.pdf_predict_thread = QThread()
        if self.current_model == "external_model":
            config = self._get_external_model_config()
            config.output_mode = fmt_key
            config.prompt_template = "ocr_document_parse_v1" if doc_mode == "parse" else "ocr_document_page_v1"
            self.pdf_predict_worker = ExternalModelPdfWorker(
                config,
                str(path),
                pages,
                fmt_key,
                dpi,
                doc_mode,
            )
        else:
            self.pdf_predict_worker = PdfPredictWorker(self.model, str(path), pages, self.current_model, fmt_key, dpi)
        self.pdf_predict_worker.moveToThread(self.pdf_predict_thread)

        progress_text = "正在解析 PDF 文档结构..." if doc_mode == "parse" else "正在识别 PDF..."
        self.pdf_progress = QProgressDialog(progress_text, "取消", 0, pages, self)
        # 进度框改为非模态，避免父窗口被锁死后无法恢复交互
        self.pdf_progress.setWindowModality(Qt.WindowModality.NonModal)
        self.pdf_progress.setMinimumDuration(0)
        self.pdf_progress.setWindowFlags(
            (
                self.pdf_progress.windowFlags()
                | Qt.WindowType.CustomizeWindowHint
                | Qt.WindowType.WindowTitleHint
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowSystemMenuHint
            )
            & ~Qt.WindowType.WindowMinimizeButtonHint
            & ~Qt.WindowType.WindowMaximizeButtonHint
            & ~Qt.WindowType.WindowMinMaxButtonsHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.pdf_progress.setFixedSize(420, 120)
        self.pdf_progress.canceled.connect(self._on_pdf_cancel_requested)
        self.pdf_predict_worker.progress.connect(self._on_pdf_progress)

        def _cleanup():
            self._predict_busy = False
            self._release_pdf_progress()
            # 线程收尾阶段避免 deleteLater 触发跨线程对象析构时序问题
            self.pdf_predict_worker = None
            self.pdf_predict_thread = None

        self.pdf_predict_thread.started.connect(self.pdf_predict_worker.run)
        self.pdf_predict_worker.finished.connect(self._on_pdf_predict_ok)
        self.pdf_predict_worker.failed.connect(self._on_pdf_predict_fail)
        self.pdf_predict_worker.finished.connect(self.pdf_predict_thread.quit)
        self.pdf_predict_worker.failed.connect(self.pdf_predict_thread.quit)
        self.pdf_predict_thread.finished.connect(_cleanup)
        self.pdf_predict_thread.start()
        try:
            self.pdf_progress.show()
        except Exception:
            pass

    def _release_pdf_progress(self):
        pd = getattr(self, "pdf_progress", None)
        self.pdf_progress = None
        if not pd:
            return
        try:
            pd.canceled.disconnect(self._on_pdf_cancel_requested)
        except Exception:
            pass
        try:
            pd.setWindowModality(Qt.WindowModality.NonModal)
        except Exception:
            pass
        try:
            pd.hide()
        except Exception:
            pass
        try:
            pd.setParent(None)
        except Exception:
            pass
        try:
            pd.deleteLater()
        except Exception:
            pass
        try:
            app = QApplication.instance()
            if app:
                app.processEvents()
        except Exception:
            pass
        try:
            # 防止 QProgressDialog 模态残留导致主窗口及其子窗口被禁用
            self.setEnabled(True)
        except Exception:
            pass

    def _on_pdf_progress(self, current: int, total: int):
        if self.pdf_progress:
            try:
                self.pdf_progress.setMaximum(total)
                self.pdf_progress.setValue(current)
            except Exception:
                pass

    def _on_pdf_cancel_requested(self):
        self._recognition_cancel_requested = True
        if self.pdf_predict_worker:
            try:
                self.pdf_predict_worker.cancel()
            except Exception:
                pass
        model = getattr(self, "model", None)
        if model and hasattr(model, "_stop_mathcraft_worker"):
            try:
                model._stop_mathcraft_worker()
            except Exception:
                pass
        if self.pdf_progress:
            try:
                self.pdf_progress.setLabelText("正在取消识别...")
            except Exception:
                pass
        if self.pdf_predict_thread:
            try:
                self.pdf_predict_thread.requestInterruption()
            except Exception:
                pass
        self.set_action_status("已取消", auto_clear_ms=3000)

    def _wrap_document_output(self, content: str, fmt_key: str, style_key: str) -> str:
        from core.pdf_output_contract import wrap_document_output

        return wrap_document_output(content, fmt_key, style_key)

    def _show_document_dialog(self, text: str, fmt_key: str, structured_result: dict | None = None):
        if not self._pdf_result_window:
            self._pdf_result_window = PdfResultWindow(status_cb=self.set_action_status, window_icon=self.icon)
        self._pdf_result_window.set_content(text, fmt_key, structured_result=structured_result)
        print(f"[DEBUG] PDF 结果窗口打开 length={len(text or '')}")
        self._pdf_result_window.show()
        self._pdf_result_window.raise_()
        self._pdf_result_window.activateWindow()

    def _on_pdf_predict_ok(self, content: str):
        self._recognition_cancel_requested = False
        used = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "pdf_predict_worker", None), "config", None)
                )
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            used = None
        if not used:
            used = getattr(self, "current_model", "mathcraft")
        self.set_model_status("完成")
        self.set_action_status("PDF 识别完成", auto_clear_ms=3500)
        self._release_pdf_progress()
        try:
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] PDF 识别完成 model={used} time={elapsed:.2f}s")
            else:
                print(f"[INFO] PDF 识别完成 model={used}")
        except Exception:
            pass
        fmt_key = self._pdf_output_format or "markdown"
        style_key = self._pdf_doc_style or "document"
        structured_result = getattr(getattr(self, "pdf_predict_worker", None), "structured_result", None)
        self._pdf_structured_result = structured_result if isinstance(structured_result, dict) else None
        doc = self._wrap_document_output(content, fmt_key, style_key)
        if not doc:
            custom_warning_dialog("提示", "识别结果为空", self)
            return
        # 延迟到下一轮事件循环打开，确保线程 quit/cleanup 与模态释放先完成
        QTimer.singleShot(0, lambda d=doc, f=fmt_key, s=self._pdf_structured_result: self._show_document_dialog(d, f, s))

    def _on_pdf_predict_fail(self, msg: str):
        self._release_pdf_progress()
        if msg == "已取消" or self._is_user_cancelled_recognition_error(msg):
            try:
                print(f"[INFO] PDF 识别已中断: {msg}")
            except Exception:
                pass
            self._show_recognition_cancelled_infobar()
            return
        self.set_model_status("失败")
        self.set_action_status(f"PDF 识别失败: {msg}", auto_clear_ms=4500)
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "pdf_predict_worker", None), "config", None)
                )
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] PDF 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                print(f"[INFO] PDF 识别失败 model={used} err={msg}")
        except Exception:
            pass

        info = classify_mathcraft_failure(msg)
        content = info.get("user_message") or str(msg)
        self.set_action_status(content, auto_clear_ms=4500)
        try:
            InfoBar.error(
                title="识别失败",
                content=content,
                parent=self,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("错误", content, self)

    def start_capture(self):
        self._last_capture_screen_index = None
        self._next_predict_result_screen_index = None
        self._prepare_predict_result_dialog_for_capture()
        pinned_dialog = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        if not self.isVisible() and pinned_dialog is None:
            self.showMinimized()  # 只最小化显示，不抢前台
        if not self.model:
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        perm = self.screenshot_provider.request_permission()
        if getattr(perm, "state", None) == "denied":
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("权限不足", getattr(perm, "message", "截图权限被拒绝"), self)
            return
        cfg = ScreenshotConfig(
            capture_display_mode=self._get_capture_display_mode(),
            preferred_screen_index=self._get_capture_display_index(),
        )
        self.overlay = self.screenshot_provider.create_overlay(cfg)
        self.overlay.installEventFilter(self)
        self.overlay.selection_done.connect(self.on_capture_done)
        self.system_provider.activate_window(self.overlay)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self._drag_contains_local_file(event):
                event.acceptProposedAction()
                return True
        if event.type() == QEvent.Type.Drop:
            if self._local_drop_paths(event):
                self.dropEvent(event)
                return True
        if obj is getattr(self, "overlay", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                try:
                    obj.close()
                except Exception:
                    pass
                self.overlay = None
                QTimer.singleShot(0, self._restore_predict_result_dialog_visibility)
                QTimer.singleShot(0, self._restore_hidden_unpinned_predict_result_dialog)
                self.set_action_status("已取消截图")
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        capture_failure_message = ""
        if self.overlay:
            capture_failure_message = str(getattr(self.overlay, "last_capture_failure_message", "") or "").strip()
            screen_index = getattr(self.overlay, "last_capture_screen_index", None)
            self._last_capture_screen_index = int(screen_index) if screen_index is not None else None
            self._next_predict_result_screen_index = self._last_capture_screen_index
            self.overlay.close()
            self.overlay = None
        QTimer.singleShot(0, self._restore_predict_result_dialog_visibility)
        if pixmap is None:
            QTimer.singleShot(0, self._restore_hidden_unpinned_predict_result_dialog)
            if capture_failure_message:
                QTimer.singleShot(0, lambda msg=capture_failure_message: self._show_capture_failure_info(msg))
            return
        if self.is_recognition_busy(source="main"):
            self._restore_hidden_unpinned_predict_result_dialog()
            self._show_recognition_busy_info()
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
            self._restore_hidden_unpinned_predict_result_dialog()
            custom_warning_dialog("错误", f"图片处理失败: {e}", self)
            return
        self._start_predict_with_pil(img)

    def _show_capture_failure_info(self, message: str):
        text = str(message or "").strip()
        if not text:
            return
        try:
            self.system_provider.activate_window(self)
        except Exception:
            try:
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception:
                pass
        InfoBar.warning(
            title="截图屏幕不匹配",
            content=text,
            parent=self,
            duration=6200,
            position=InfoBarPosition.TOP,
        )

    def update_tray_menu(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        handlers = TrayMenuHandlers(
            on_open=self.show_window,
            on_capture=self.start_capture,
            on_exit=self.truly_exit,
            build_capture_submenu=self._build_capture_display_submenu,
        )
        self.system_provider.update_tray_menu(self.tray_icon, hk, handlers)

    def _on_external_predict_ok(self, result):
        try:
            output_mode = self._get_external_model_config().normalized_output_mode()
        except Exception:
            output_mode = "latex"
        try:
            text = result.best_text(output_mode) if result is not None else ""
        except Exception:
            text = ""
        try:
            self._last_external_model_name = self._get_external_model_display_name(result=result)
        except Exception:
            pass
        self.on_predict_ok(text)

    def _on_external_predict_fail(self, msg: str):
        self.on_predict_fail(msg)

    def _clear_predict_result_dialog_ref(self, dialog_obj=None):
        """仅在回调对象仍是当前窗口时，清理结果窗口引用，避免并发回调误清空。"""
        current = getattr(self, "_predict_result_dialog", None)
        if dialog_obj is None or current is dialog_obj:
            self._predict_result_dialog = None
        hidden = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        if dialog_obj is None or hidden is dialog_obj:
            self._hidden_unpinned_predict_result_dialog_for_capture = None
        restoring = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        if dialog_obj is None or restoring is dialog_obj:
            self._restore_predict_result_dialog_after_capture = None

    def _is_predict_result_dialog_alive(self, dlg) -> bool:
        if dlg is None:
            return False
        try:
            if sip is not None and sip.isdeleted(dlg):
                return False
        except Exception:
            pass
        return True

    def _move_predict_result_dialog_to_screen(self, dlg: QDialog, screen_index: int | None) -> None:
        if screen_index is None or bool(getattr(dlg, "_predict_result_pinned", False)):
            return
        try:
            from PyQt6.QtGui import QGuiApplication

            screens = QGuiApplication.screens()
            idx = int(screen_index)
            if idx < 0 or idx >= len(screens):
                return
            geo = screens[idx].availableGeometry()
            size = dlg.size()
            main_screen = None
            try:
                handle = self.windowHandle()
                if handle is not None:
                    main_screen = handle.screen()
            except Exception:
                main_screen = None
            if main_screen is None:
                try:
                    main_screen = QGuiApplication.screenAt(self.frameGeometry().center())
                except Exception:
                    main_screen = None
            same_screen_as_main = bool(main_screen is screens[idx])

            if self.isVisible() and not self.isMinimized() and same_screen_as_main:
                width = min(int(size.width()), int(geo.width()))
                height = min(int(size.height()), int(geo.height()))
                x = int(geo.x() + max(0, (geo.width() - width) // 2))
                y = int(geo.y() + max(0, (geo.height() - height) // 2))
            else:
                margin = 24
                x = int(geo.x() + margin)
                y = int(geo.y() + margin)
            max_x = geo.right() - int(size.width()) + 1
            max_y = geo.bottom() - int(size.height()) + 1
            x = max(geo.left(), min(x, max_x))
            y = max(geo.top(), min(y, max_y))
            dlg.move(x, y)
        except Exception:
            pass

    def _predict_result_pinned_size(self) -> tuple[int, int]:
        """识别结果窗口置顶固定后的紧凑尺寸。"""
        return (320, 380)

    def _predict_result_mode_title(self, current_mode: str) -> str:
        mode_titles = {
            "mathcraft": "确认或修改 LaTeX：",
            "mathcraft_text": "识别的文字内容：",
            "mathcraft_mixed": "识别结果（文字+公式）：",
        }
        return mode_titles.get(current_mode, "确认或修改内容：")

    def _set_predict_result_pin_button_style(self, button, pinned: bool):
        try:
            t = _dialog_theme_tokens()
            icon = FluentIcon.UNPIN if pinned else FluentIcon.PIN
            button.setIcon(icon.icon())
            button.setIconSize(QSize(18, 18))
            button.setToolTip("固定为小窗口并保持置顶，再点一次恢复可调整大小")
            if pinned:
                dark = _is_dark_ui()
                bg = "#2f6ea8" if dark else "#3daee9"
                hover = "#3e82c3" if dark else "#5dbff2"
                pressed = "#245a8d" if dark else "#319fd9"
                border = "#4d8dca" if dark else "#2b94cb"
                button.setStyleSheet(
                    f"""
                    QToolButton {{
                        background: {bg};
                        color: #ffffff;
                        border: 1px solid {border};
                        border-radius: 4px;
                        padding: 0;
                    }}
                    QToolButton:hover {{
                        background: {hover};
                        border: 1px solid {border};
                    }}
                    QToolButton:pressed {{
                        background: {pressed};
                        border: 1px solid {border};
                    }}
                    """
                )
            else:
                button.setStyleSheet(
                    f"""
                    QToolButton {{
                        background: transparent;
                        color: {t["muted"]};
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 0;
                        min-width: 30px;
                        min-height: 30px;
                    }}
                    QToolButton:hover {{
                        background: {t["panel_bg"]};
                        border: 1px solid {t["accent"]};
                    }}
                    QToolButton:pressed {{
                        background: {t["panel_bg"]};
                    }}
                    """
                )
        except Exception:
            pass

    def _set_predict_result_native_caption_buttons(self, dlg: QDialog, pinned: bool) -> bool:
        if os.name != "nt":
            return False
        try:
            hwnd = int(dlg.winId())
            if not hwnd:
                return False
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -16)
            if not style:
                return False
            ws_minimizebox = 0x00020000
            ws_maximizebox = 0x00010000
            if pinned:
                style &= ~ws_minimizebox
                style &= ~ws_maximizebox
            else:
                style &= ~ws_minimizebox
                style |= ws_maximizebox
            user32.SetWindowLongW(hwnd, -16, style)
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOMOVE | NOSIZE | NOZORDER | NOACTIVATE | FRAMECHANGED
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
            return True
        except Exception:
            return False

    def _set_predict_result_native_topmost(self, dlg: QDialog, topmost: bool) -> bool:
        if os.name != "nt":
            return False
        try:
            hwnd = int(dlg.winId())
            if not hwnd:
                return False
            user32 = ctypes.windll.user32
            insert_after = -1 if topmost else -2  # HWND_TOPMOST / HWND_NOTOPMOST
            flags = 0x0010 | 0x0001 | 0x0002 | 0x0040  # NOACTIVATE | NOSIZE | NOMOVE | SHOWWINDOW
            ok = user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags)
            return bool(ok)
        except Exception:
            return False

    def _set_predict_result_pinned(self, dlg: QDialog, pin_btn, pinned: bool):
        dlg._predict_result_pinned = bool(pinned)
        try:
            if pinned and not dlg.isMaximized():
                dlg._pin_restore_geometry = dlg.geometry()
        except Exception:
            pass

        try:
            dlg.setMinimumSize(0, 0)
            dlg.setMaximumSize(16777215, 16777215)
        except Exception:
            pass

        if pinned:
            width, height = self._predict_result_pinned_size()
            dlg.setFixedSize(width, height)
        else:
            restore_geometry = getattr(dlg, "_pin_restore_geometry", None)
            if restore_geometry is not None:
                try:
                    dlg.resize(restore_geometry.size())
                    dlg.move(restore_geometry.topLeft())
                except Exception:
                    pass

        if not self._set_predict_result_native_topmost(dlg, pinned):
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pinned)
            dlg.show()
        self._set_predict_result_native_caption_buttons(dlg, pinned)

        self._set_predict_result_pin_button_style(pin_btn, pinned)
        try:
            pin_btn.setChecked(pinned)
        except Exception:
            pass
        dlg.raise_()
        dlg.activateWindow()

    def _try_refresh_predict_result_dialog(self, dlg: QDialog, code: str, current_mode: str) -> bool:
        try:
            if not bool(getattr(dlg, "_predict_result_pinned", False)):
                return False
            if getattr(dlg, "_predict_result_mode", None) != current_mode:
                return False
            editor = getattr(dlg, "_predict_result_editor", None)
            info_label = getattr(dlg, "_predict_result_info_label", None)
            if editor is None or info_label is None:
                return False
            info_label.setText(self._predict_result_mode_title(current_mode))
            editor.setPlainText(code)
            dlg.raise_()
            dlg.activateWindow()
            return True
        except Exception:
            return False

    def _prepare_predict_result_dialog_for_capture(self):
        dlg = getattr(self, "_predict_result_dialog", None)
        self._restore_predict_result_dialog_after_capture = None
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            if bool(getattr(dlg, "_predict_result_pinned", False)) and dlg.isVisible():
                self._restore_predict_result_dialog_after_capture = dlg
            elif dlg.isVisible():
                self._hidden_unpinned_predict_result_dialog_for_capture = dlg
                dlg.hide()
        except Exception:
            self._restore_predict_result_dialog_after_capture = None
            self._hidden_unpinned_predict_result_dialog_for_capture = None

    def _restore_predict_result_dialog_visibility(self):
        dlg = getattr(self, "_restore_predict_result_dialog_after_capture", None)
        self._restore_predict_result_dialog_after_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            dlg.show()
            if bool(getattr(dlg, "_predict_result_pinned", False)):
                self._set_predict_result_native_topmost(dlg, True)
                self._set_predict_result_native_caption_buttons(dlg, True)
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _restore_hidden_unpinned_predict_result_dialog(self):
        dlg = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        self._hidden_unpinned_predict_result_dialog_for_capture = None
        if not self._is_predict_result_dialog_alive(dlg):
            return
        try:
            if bool(getattr(dlg, "_predict_result_pinned", False)):
                return
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _discard_hidden_unpinned_predict_result_dialog(self, dialog_obj=None):
        hidden = getattr(self, "_hidden_unpinned_predict_result_dialog_for_capture", None)
        if dialog_obj is None or hidden is dialog_obj:
            self._hidden_unpinned_predict_result_dialog_for_capture = None

    def on_predict_ok(self, latex: str):
        self._recognition_cancel_requested = False
        used = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "predict_worker", None), "config", None)
                )
                if not used:
                    used = getattr(self, "_last_external_model_name", None)
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            used = None
        if not used:
            used = getattr(self, "current_model", "mathcraft")
        self.set_model_status("完成")
        self.set_action_status("识别完成", auto_clear_ms=3000)
        try:
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] 识别完成 model={used} time={elapsed:.2f}s")
            else:
                print(f"[INFO] 识别完成 model={used}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            # 默认关闭识别完成系统托盘弹窗，避免连续识别场景刷屏。
            show_toast = bool(self.cfg.get("show_capture_success_toast", False))
            if show_toast:
                try:
                    now_ts = datetime.datetime.now().timestamp()
                    cooldown_ok = (now_ts - float(getattr(self, "_last_capture_toast_ts", 0.0) or 0.0)) >= 12.0
                    bg_mode = (not self.isVisible()) or self.isMinimized() or (not self.isActiveWindow())
                    if cooldown_ok and bg_mode:
                        hk = self.cfg.get("hotkey", "Ctrl+F")
                        self.system_provider.show_notification(
                            self.tray_icon,
                            "识别完成",
                            f"公式已识别。使用快捷键 {hk} 可再次截图。",
                            critical=False,
                            timeout_ms=2500,
                        )
                        self._last_capture_toast_ts = now_ts
                except Exception:
                    pass
        self.show_confirm_dialog(latex)
        self._discard_hidden_unpinned_predict_result_dialog()

    def show_confirm_dialog(self, latex_code: str):
        """显示识别结果确认对话框"""
        result_screen_index = self._next_predict_result_screen_index
        self._next_predict_result_screen_index = None
        code = (latex_code or "").strip()
        if not code:
            _exec_close_only_message_box(self, "提示", "结果为空")
            return

        # 获取当前识别模式（优先使用实际使用的模型，便于正确标注类型）
        current_mode = None
        try:
            if getattr(self, "current_model", "") == "external_model":
                current_mode = "external_model"
            else:
                current_mode = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            current_mode = None
        if not current_mode:
            current_mode = getattr(self, "current_model", "mathcraft")

        # 识别结果窗口保持单实例：固定小窗时直接刷新内容，避免销毁重建。
        old_dialog = getattr(self, "_predict_result_dialog", None)
        if old_dialog is not None and self._try_refresh_predict_result_dialog(old_dialog, code, current_mode):
            return
        if old_dialog is not None:
            try:
                old_dialog.close()
            except Exception:
                pass
            self._clear_predict_result_dialog_ref(old_dialog)

        dlg = QDialog(self)
        _apply_no_minimize_window_flags(dlg)
        dlg.setWindowTitle("识别结果")
        dlg.resize(700, 500)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg._predict_result_mode = current_mode
        dlg._predict_result_pinned = False
        self._predict_result_dialog = dlg
        dlg.destroyed.connect(lambda *_args, _d=dlg: self._clear_predict_result_dialog_ref(_d))

        lay = QVBoxLayout(dlg)

        # 根据模式显示不同的标题
        info = BodyLabel(self._predict_result_mode_title(current_mode))
        dlg._predict_result_info_label = info
        header_row = QHBoxLayout()
        header_row.addWidget(info)
        header_row.addStretch()
        pin_btn = PrimaryToolButton(FluentIcon.PIN, dlg)
        pin_btn.setCheckable(True)
        pin_btn.setFixedSize(30, 30)
        self._set_predict_result_pin_button_style(pin_btn, False)
        header_row.addWidget(pin_btn)
        lay.addLayout(header_row)

        te = QTextEdit()
        te.setText(code)
        dlg._predict_result_editor = te
        lay.addWidget(te)
        
        # 根据模式选择不同的预览策略
        preview_label = None
        preview_view = None
        
        # 公式模式：使用 MathJax 渲染
        if normalize_content_type(current_mode) == "mathcraft":
            preview_label = BodyLabel("公式预览：")
            lay.addWidget(preview_label)
            
            if ensure_webengine_loaded():
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                preview_view = QWebEngineView()
                preview_view.setMinimumHeight(150)
                preview_view.setHtml(build_math_html(code), _get_mathjax_base_url())
                lay.addWidget(preview_view, 1)
                
                # 设置防抖定时器
                render_timer = QTimer(dlg)
                render_timer.setSingleShot(True)

                def do_render():
                    latex = te.toPlainText().strip()
                    if latex and preview_view:
                        preview_view.setHtml(build_math_html(latex), _get_mathjax_base_url())

                render_timer.timeout.connect(do_render)
                te.textChanged.connect(lambda: render_timer.start(300))
            else:
                fallback = QLabel("WebEngine 未加载，无法渲染预览")
                fallback.setStyleSheet(f"color: {_dialog_theme_tokens()['muted']}; padding: 10px;")
                lay.addWidget(fallback)

        # 混合模式：渲染文字和公式
        elif current_mode == "mathcraft_mixed":
            preview_label = BodyLabel("混合内容预览：")
            lay.addWidget(preview_label)
            
            if ensure_webengine_loaded():
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                preview_view = QWebEngineView()
                preview_view.setMinimumHeight(150)
                # 混合模式使用特殊渲染
                preview_view.setHtml(self._build_mixed_html(code), _get_mathjax_base_url())
                lay.addWidget(preview_view, 1)
                
                render_timer = QTimer(dlg)
                render_timer.setSingleShot(True)
                
                def do_render_mixed():
                    content = te.toPlainText().strip()
                    if content and preview_view:
                        preview_view.setHtml(self._build_mixed_html(content), _get_mathjax_base_url())
                
                render_timer.timeout.connect(do_render_mixed)
                te.textChanged.connect(lambda: render_timer.start(300))

        # 纯文字模式：简单文本预览
        elif current_mode == "mathcraft_text":
            preview_label = BodyLabel("文本预览：")
            lay.addWidget(preview_label)
            
            preview_text = QTextEdit()
            preview_text.setReadOnly(True)
            preview_text.setPlainText(code)
            preview_text.setMinimumHeight(100)
            lay.addWidget(preview_text, 1)
            
            # 同步更新预览
            def update_preview():
                preview_text.setPlainText(te.toPlainText())
            te.textChanged.connect(update_preview)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        export_btn = PushButton(FluentIcon.SHARE, "导出")
        export_btn.setFixedHeight(32)
        export_btn.clicked.connect(
            lambda: self._show_export_menu_for_source(
                export_btn,
                lambda: te.toPlainText(),
                empty_hint="识别结果为空",
                info_parent=dlg,
            )
        )
        confirm_btn = PrimaryPushButton(FluentIcon.ACCEPT, "确定")
        confirm_btn.setFixedHeight(32)
        confirm_btn.clicked.connect(lambda: self.accept_latex(dlg, te))
        btn_row.addWidget(export_btn)
        btn_row.addWidget(confirm_btn)
        lay.addLayout(btn_row)
        pin_btn.toggled.connect(lambda checked: self._set_predict_result_pinned(dlg, pin_btn, checked))

        self._move_predict_result_dialog_to_screen(dlg, result_screen_index)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _build_mixed_html(self, content: str) -> str:
        """构建混合内容（文字+公式）的 HTML"""
        import html
        import re
        tokens = _preview_theme_tokens()
        
        # 提取并保护公式部分
        # 先匹配块级公式 $$...$$，再匹配行内公式 $...$
        formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'
        
        parts = re.split(formula_pattern, content)
        result_parts = []
        
        for part in parts:
            if part.startswith('$$') and part.endswith('$$'):
                # 块级公式，保持原样
                result_parts.append(part)
            elif part.startswith('$') and part.endswith('$'):
                # 行内公式，保持原样
                result_parts.append(part)
            else:
                # 普通文本，转义 HTML 特殊字符，保留换行
                escaped = html.escape(part)
                escaped = escaped.replace('\n', '<br>')
                result_parts.append(escaped)
        
        body_content = ''.join(result_parts)
        
        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script>
  window.MathJax = {{
    tex: {{
      inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
      displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
      processEscapes: true
    }},
    svg: {{
      fontCache: 'global',
            scale: 1.2
    }},
    options: {{
      enableMenu: false,
      skipHtmlTags: [],
      ignoreHtmlClass: [],
      processHtmlClass: []
    }}
  }};
</script>
<script src="tex-mml-chtml.js" async></script>
<style>
html, body {{
       margin: 0;
       padding: 0;
       background: {tokens['body_bg']};
       color: {tokens['body_text']};
}}
body {{
       font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       padding: 16px;
       line-height: 1.8;
       font-size: 14px;
}}
.content {{
       min-height: calc(100vh - 32px);
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
       box-sizing: border-box;
}}
.content br {{
       line-height: 1.8;
}}
.MathJax, .mjx-container {{
    font-size: 1.45em !important;
       color: {tokens['body_text']} !important;
}}
a {{
       color: {tokens['label_text']};
}}
pre, code {{
       background: {tokens['pre_bg']};
       color: {tokens['body_text']};
       border-radius: 6px;
}}
</style>
</head>
<body><div class="content">{body_content}</div></body>
</html>'''

    def _build_mixed_preview_html(self, formulas: list, labels: list) -> str:
        """构建混合模式的预览 HTML（支持多个公式）"""
        import html
        import re
        tokens = _preview_theme_tokens()
        
        items_html = []
        for i, (formula, label) in enumerate(zip(formulas, labels)):
            # 提取并保护公式部分
            # 先匹配块级公式 $$...$$，再匹配行内公式 $...$
            formula_pattern = r'(\$\$(?:[^$]|\$(?!\$))+?\$\$|\$(?:[^$]|\$(?!\$))+?\$)'
            parts = re.split(formula_pattern, formula)
            result_parts = []
            
            for part in parts:
                if part.startswith('$$') and part.endswith('$$'):
                    result_parts.append(part)
                elif part.startswith('$') and part.endswith('$'):
                    result_parts.append(part)
                else:
                    escaped = html.escape(part)
                    escaped = escaped.replace('\n', '<br>')
                    result_parts.append(escaped)
            
            body_content = ''.join(result_parts)
            label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
            items_html.append(f'<div class="item">{label_html}<div class="content">{body_content}</div></div>')
        
        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script>
    window.MathJax = {{
        tex: {{
            inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
            displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
            processEscapes: true
        }},
        svg: {{
            fontCache: 'global',
            scale: 1.15
        }},
        options: {{
            enableMenu: false,
            skipHtmlTags: [],
            ignoreHtmlClass: [],
            processHtmlClass: []
        }}
    }};
</script>
<script src="es5/tex-mml-chtml.js" async></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_formula']}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.8; font-size: 14px; }}
.MathJax, .mjx-container {{ font-size: 1.45em !important; color: {tokens['body_text']} !important; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''

    def _build_text_preview_html(self, formulas: list, labels: list) -> str:
        """构建纯文本模式的预览 HTML"""
        import html
        tokens = _preview_theme_tokens()
        
        items_html = []
        for i, (formula, label) in enumerate(zip(formulas, labels)):
            escaped = html.escape(formula).replace('\n', '<br>')
            label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
            items_html.append(f'<div class="item">{label_html}<div class="content">{escaped}</div></div>')
        
        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_text']}; color: {tokens['body_bg']}; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.6; font-size: 14px; white-space: pre-wrap; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''

    def _build_table_preview_html(self, formulas: list, labels: list) -> str:
        """构建表格模式的预览 HTML"""
        import html
        tokens = _preview_theme_tokens()
        
        items_html = []
        for i, (formula, label) in enumerate(zip(formulas, labels)):
            # 如果是 HTML 表格，直接使用；否则显示为代码
            if formula.strip().startswith('<'):
                content = formula
            else:
                content = f"<pre>{html.escape(formula)}</pre>"
            
            label_html = f'<span class="label">#{i+1} {html.escape(label)}</span>' if label else f'<span class="label">#{i+1}</span>'
            items_html.append(f'<div class="item">{label_html}<div class="content">{content}</div></div>')
        
        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
.item {{ margin-bottom: 16px; padding: 12px; background: {tokens['panel_bg']}; border: 1px solid {tokens['table_border']}; border-radius: 8px; }}
.label {{ display: inline-block; background: {tokens['border_table']}; color: {tokens['body_bg']}; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ font-size: 14px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid {tokens['table_border']}; padding: 8px; text-align: left; }}
th {{ background-color: {tokens['th_bg']}; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0; }}
</style>
</head>
<body>{"".join(items_html) if items_html else f"<p style='color:{tokens['muted_text']};'>暂无内容</p>"}</body>
</html>'''

    def _build_table_html(self, content: str) -> str:
        """构建表格的 HTML 预览"""
        tokens = _preview_theme_tokens()
        # 如果内容已经是 HTML 格式，直接使用
        if content.strip().startswith('<'):
            table_content = content
        else:
            # 尝试将 Markdown 表格转为 HTML
            import html
            table_content = f"<pre>{html.escape(content)}</pre>"

        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       padding: 16px; background: {tokens['body_bg']}; color: {tokens['body_text']}; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid {tokens['table_border']}; padding: 8px; text-align: left; }}
th {{ background-color: {tokens['th_bg']}; }}
tr:nth-child(even) {{ background-color: {tokens['panel_bg']}; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; }}
</style>
</head>
<body>{table_content}</body>
</html>'''

    def on_predict_fail(self, msg: str):
        self._next_predict_result_screen_index = None
        self._restore_hidden_unpinned_predict_result_dialog()
        if self._is_user_cancelled_recognition_error(msg):
            try:
                print(f"[INFO] 识别已中断: {msg}")
            except Exception:
                pass
            self._show_recognition_cancelled_infobar()
            return
        self.set_model_status("失败")
        try:
            if getattr(self, "current_model", "") == "external_model":
                used = self._get_external_model_display_name(
                    config=getattr(getattr(self, "predict_worker", None), "config", None)
                )
                if not used:
                    used = getattr(self, "_last_external_model_name", None)
            else:
                used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "mathcraft")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            if elapsed is not None:
                print(f"[INFO] 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                print(f"[INFO] 识别失败 model={used} err={msg}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            hk = self.cfg.get("hotkey", "Ctrl+F")
            try:
                self.system_provider.show_notification(
                    self.tray_icon,
                    "识别失败",
                    f"{msg}\n可使用快捷键 {hk} 重试。",
                    critical=True,
                    timeout_ms=4000,
                )
            except Exception:
                pass
        info = classify_mathcraft_failure(msg)
        content = info.get("user_message") or str(msg)
        self.set_action_status(content, auto_clear_ms=4500)
        try:
            InfoBar.error(
                title="识别失败",
                content=content,
                parent=self,
                duration=4500,
                position=InfoBarPosition.TOP,
            )
        except Exception:
            custom_warning_dialog("错误", content, self)

    def accept_latex(self, dialog, te: QTextEdit):
        t = te.toPlainText().strip()
        if not t:
            if bool(getattr(dialog, "_predict_result_pinned", False)):
                self.set_action_status("识别结果为空", parent=dialog)
                return
            dialog.reject()
            return
        try:
            try:
                pyperclip.copy(t)
            except Exception:
                QApplication.clipboard().setText(t)
        except Exception as e:
            custom_warning_dialog("错误", f"复制失败: {e}",self)
        try:
            content_type = None
            try:
                content_type = getattr(getattr(self, "model", None), "last_used_model", None)
            except Exception:
                content_type = None
            if not content_type:
                content_type = getattr(self, "current_model", "mathcraft")
            self.add_history_record(t, content_type=content_type)
        except Exception as e:
            custom_warning_dialog("错误", f"写入历史失败: {e}", self)
        if bool(getattr(dialog, "_predict_result_pinned", False)):
            self.set_action_status("已确认并复制到剪贴板", parent=dialog)
            try:
                dialog.raise_()
                dialog.activateWindow()
            except Exception:
                pass
            return
        dialog.accept()

    def clear_history(self):
        # 若无记录给提示
        if not self.history:
            InfoBar.info(
                title="提示",
                content="当前没有历史记录可清空",
                parent=self._get_infobar_parent(),
                duration=2500,
                position=InfoBarPosition.TOP,
            )
            return
        ret = _exec_close_only_message_box(
            self,
            "确认",
            f"确定要清空所有 {len(self.history)} 条历史记录吗？",
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.history.clear()
        self.save_history()
        self.rebuild_history_ui()
        self.update_history_ui()  # 确保按钮状态刷新
        self.set_action_status("已清空历史")
    def register_hotkey(self, seq: str):
        if not getattr(self, "hotkey_provider", None):
            return
        print(f"[Hotkey] try register {seq}")
        try:
            self.hotkey_provider.register(seq)
            print(f"[Hotkey] global registered={self.hotkey_provider.is_registered()}")
        except Exception as e:
            print(f"[Hotkey] global failed: {e}")

    def _has_blocking_window(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        try:
            modal = app.activeModalWidget()
            if modal is not None and modal is not self and modal.isVisible():
                return True
        except Exception:
            pass
        try:
            popup = app.activePopupWidget()
            if popup is not None and popup.isVisible():
                return True
        except Exception:
            pass
        try:
            for widget in app.topLevelWidgets():
                if widget is None or widget is self or (not widget.isVisible()):
                    continue
                try:
                    if bool(widget.isModal()) or widget.windowModality() != Qt.WindowModality.NonModal:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def on_hotkey_triggered(self):
        print("[Hotkey] Triggered")
        if self._has_blocking_window():
            try:
                InfoBar.info(
                    title="提示",
                    content="请先关闭当前对话框，再执行截图识别",
                    parent=self._get_infobar_parent(),
                    duration=2200,
                    position=InfoBarPosition.TOP,
                )
            except Exception:
                pass
            return
        self.start_capture()

    # 设置快捷键窗口支持 ESC 关闭
    def set_shortcut(self):
        from PyQt6.QtWidgets import QLineEdit
        if self.shortcut_window and self.shortcut_window.isVisible():
            self.shortcut_window.raise_()
            self.shortcut_window.activateWindow()
            return

        dlg = QDialog(self)
        _apply_close_only_window_flags(dlg)
        dlg.setWindowTitle("设置快捷键")
        dlg.setFixedSize(320, 120)
        dlg.setModal(False)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dlg.destroyed.connect(lambda: setattr(self, "shortcut_window", None))
        t = _dialog_theme_tokens()
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"当前: {self.cfg.get('hotkey', 'Ctrl+F')} 按下新的 Ctrl+字母以创建，或按 Esc 取消"))
        edit = QLineEdit(dlg)
        edit.setReadOnly(True)
        edit.setFixedHeight(34)
        edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        edit.setStyleSheet(
            f"""
QLineEdit {{
    background: {t['panel_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {"#3b4756" if _is_dark_ui() else "#d7e3f1"};
    selection-color: {t['text']};
}}
QLineEdit:focus {{
    border: 1px solid {"#66788a" if _is_dark_ui() else "#9aa9bb"};
}}
"""
        )

        def keyPressEvent(ev):
            if ev.key() == Qt.Key.Key_Escape:
                dlg.reject()
                return
            k = ev.key()
            if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
                edit.setText(f"Ctrl+{chr(k)}")
                edit.setFocus()
                edit.selectAll()
            else:
                edit.setText("")
                edit.setFocus()

        edit.keyPressEvent = keyPressEvent
        lay.addWidget(edit)
        btn = PushButton(FluentIcon.ACCEPT, "确定")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda: self.update_hotkey(edit.text().strip(), dlg))
        lay.addWidget(btn)
        self.shortcut_window = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        QTimer.singleShot(0, edit.setFocus)

    def update_hotkey(self, text: str, dialog: QDialog):
        from qfluentwidgets import InfoBar, InfoBarPosition

        if not (text.startswith("Ctrl+") and len(text) == 6 and text[-1].isalpha()):
            InfoBar.error(
                title="快捷键格式错误",
                content="格式必须为 Ctrl+字母",
                parent=self._get_infobar_parent(),
                duration=3000,
                position=InfoBarPosition.TOP,
            )
            return
        self.register_hotkey(text)
        if (
            getattr(self, "hotkey_provider", None)
            and (not self.hotkey_provider.is_registered())
        ):
            InfoBar.error(
                title="快捷键注册失败",
                content="请更换其他 Ctrl+字母组合后重试",
                parent=self._get_infobar_parent(),
                duration=3500,
                position=InfoBarPosition.TOP,
            )
            return
        self.cfg.set("hotkey", text)
        try:
            dialog.close()
        except Exception:
            pass
        InfoBar.success(
            title="快捷键已更新",
            content=f"已更新为 {text}",
            parent=self._get_infobar_parent(),
            duration=2500,
            position=InfoBarPosition.TOP,
        )
        self.update_tray_tooltip()
        self.update_tray_menu()

    def apply_startup_console_preference(self, enabled: bool):
        """应用“启动是否显示日志窗口”的偏好。"""
        try:
            os.environ["LATEXSNIPPER_SHOW_CONSOLE"] = "1" if enabled else "0"
            open_debug_console(force=False, tee=True)
        except Exception as e:
            print(f"[WARN] apply_startup_console_preference failed: {e}")

    def prepare_restart(self):
        """Called by settings restart flow: close heavy resources and release app lock early."""
        try:
            self._graceful_shutdown()
        except Exception:
            pass
        try:
            _cleanup_runtime_log_session()
        except Exception:
            pass
        try:
            _release_single_instance_lock()
        except Exception:
            pass
        try:
            if getattr(self, "hotkey_provider", None):
                self.hotkey_provider.cleanup()
        except Exception:
            pass

    # ---------- 其它 UI ----------
    def open_settings(self):
        if self.settings_window and self.settings_window.isVisible():
            try:
                if hasattr(self.settings_window, "apply_theme_styles"):
                    self.settings_window.apply_theme_styles(force=True)
            except Exception:
                pass
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if not self.settings_window:
            self.settings_window = SettingsWindow(self)
            self.settings_window.model_changed.connect(self.on_model_changed)
            self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
        self.settings_window.show()
        try:
            if hasattr(self.settings_window, "apply_theme_styles"):
                self.settings_window.apply_theme_styles(force=True)
        except Exception:
            pass
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def open_favorites(self):
        fav = self._ensure_favorites_window()
        fav.show()
        fav.raise_()
        fav.activateWindow()

    def _on_workbench_insert(self, latex: str):
        text = (latex or "").strip()
        if text == "__LOAD_FROM_MAIN__":
            text = self.latex_editor.toPlainText().strip()
            if not text:
                if getattr(self, "workbench_window", None):
                    self.workbench_window.show_info("当前无内容", "主编辑器为空，没有可载入的公式")
                return
            self.workbench_window.set_latex(text)
            self.workbench_window.show_success("已载入", "主编辑器内容已载入数学工作台")
            return
        if not text:
            if getattr(self, "workbench_window", None):
                self.workbench_window.show_info("当前无内容", "数学工作台为空，没有可写回的内容")
            return
        self.latex_editor.setPlainText(text)
        self.render_latex_in_preview(text)
        self.set_action_status("工作台内容已回填到主编辑器")
        if getattr(self, "workbench_window", None):
            self.workbench_window.show_success("已写回", "数学工作台内容已写回主编辑器")

    def _on_handwriting_insert(self, latex: str):
        text = (latex or "").strip()
        if not text:
            return
        self._set_editor_text_silent(text)
        try:
            ctype = self._get_preferred_model_for_predict()
            if not ctype:
                ctype = getattr(self, "current_model", "mathcraft")
            self._formula_types[text] = ctype
        except Exception:
            pass
        self._refresh_preview()
        self.set_action_status("手写识别结果已写入主编辑器")
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def open_handwriting_window(self):
        preferred = self._get_preferred_model_for_predict()
        self._sync_current_model_status_from_preference()
        if not self.model and preferred != "external_model":
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        if preferred == "external_model" and not self._is_external_model_configured():
            custom_warning_dialog("提示", "外部模型未配置，请先完成配置并测试连接。", self)
            self.open_settings()
            return
        if getattr(self, "handwriting_window", None) and self.handwriting_window.isVisible():
            self.handwriting_window.raise_()
            self.handwriting_window.activateWindow()
            if preferred.startswith("mathcraft"):
                self._ensure_model_warmup_async(preferred_model=preferred)
            return
        self.handwriting_window = HandwritingWindow(self.model, owner=self, parent=None)
        self.handwriting_window.latexInserted.connect(self._on_handwriting_insert)
        self.handwriting_window.destroyed.connect(lambda: setattr(self, "handwriting_window", None))
        self.handwriting_window.show()
        self.handwriting_window.raise_()
        self.handwriting_window.activateWindow()
        if preferred.startswith("mathcraft"):
            self._ensure_model_warmup_async(preferred_model=preferred)

    def open_workbench(self):
        if getattr(self, "workbench_window", None) and self.workbench_window.isVisible():
            self.workbench_window.raise_()
            self.workbench_window.activateWindow()
        else:
            self.workbench_window = WorkbenchWindow(None, on_insert_latex=self._on_workbench_insert)
            self.workbench_window.destroyed.connect(lambda: setattr(self, "workbench_window", None))
            self.workbench_window.apply_theme_styles(force=True)
            self.workbench_window.show()
        current = self.latex_editor.toPlainText().strip()
        if current:
            self.workbench_window.set_latex(current)
        self.workbench_window.raise_()
        self.workbench_window.activateWindow()

    def open_bilingual_reader(self):
        window = getattr(self, "bilingual_pdf_window", None)
        if window is not None:
            try:
                if window.isVisible():
                    window.raise_()
                    window.activateWindow()
                    return
            except RuntimeError:
                pass
            self.bilingual_pdf_window = None
        try:
            window = BilingualPdfWindow(cfg=self.cfg, parent=None)
        except Exception as exc:
            custom_warning_dialog("错误", f"双语阅读窗口初始化失败: {exc}", self)
            return
        self.bilingual_pdf_window = window
        window.destroyed.connect(lambda: setattr(self, "bilingual_pdf_window", None))
        window.show()
        window.raise_()
        window.activateWindow()

    def show_window(self):
        self.system_provider.activate_window(self)
        self.set_action_status("主窗口已显示")

    # ---------- 关闭 / 资源清理 ----------

    # python
    def _graceful_shutdown(self):
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True  # 防止多次调用
        
        # 保存历史记录和公式名称
        try:
            self.save_history()
            print("[关闭] 历史记录已保存")
        except Exception as e:
            print(f"[关闭] 保存历史失败: {e}")
        
        # 保存收藏夹
        try:
            if hasattr(self, 'favorites_window') and self.favorites_window:
                self.favorites_window.save_favorites()
                print("[关闭] 收藏夹已保存")
        except Exception as e:
            print(f"[关闭] 保存收藏夹失败: {e}")
        
        # 保存配置
        try:
            self.cfg.save()
            print("[关闭] 配置已保存")
        except Exception as e:
            print(f"[关闭] 保存配置失败: {e}")

        # 显式关闭模型子进程 worker，避免残留后台进程
        try:
            m = getattr(self, "model", None)
            if m:
                fn = getattr(m, "_stop_mathcraft_worker", None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        except Exception:
            pass
        
        if self.predict_thread:
            try:
                if self.predict_thread.isRunning():
                    self.predict_thread.quit()
                    self.predict_thread.wait(3000)  # 等待线程结束
            except Exception:
                pass
        if self.predict_worker:
            try:
                self.predict_worker.deleteLater()
            except Exception:
                pass
        self.predict_thread = None
        self.predict_worker = None
        self._predict_busy = False

        if self.pdf_predict_thread:
            try:
                if self.pdf_predict_thread.isRunning():
                    self.pdf_predict_thread.quit()
                    self.pdf_predict_thread.wait(3000)
            except Exception:
                pass
        if self.pdf_predict_worker:
            try:
                self.pdf_predict_worker.deleteLater()
            except Exception:
                pass
        self.pdf_predict_thread = None
        self.pdf_predict_worker = None
        if self.pdf_progress:
            try:
                self.pdf_progress.close()
            except Exception:
                pass
            self.pdf_progress = None
        if self._pdf_result_window:
            try:
                self._pdf_result_window.close()
            except Exception:
                pass
        if self._preview_render_thread:
            try:
                if self._preview_render_thread.isRunning():
                    self._preview_render_thread.quit()
                    self._preview_render_thread.wait(3000)
            except Exception:
                pass
        if self._preview_render_worker:
            try:
                self._preview_render_worker.deleteLater()
            except Exception:
                pass
        self._preview_render_thread = None
        self._preview_render_worker = None
        try:
            _cleanup_runtime_log_session()
        except Exception:
            pass
        try:
            _release_single_instance_lock()
        except Exception:
            pass

    def closeEvent(self, event):
        if self._force_exit:
            # 真实退出
            self._graceful_shutdown()
            event.accept()
            return
        # 普通关闭 = 最小化到托盘
        self.hide()
        if self.tray_icon:
            # 只在第一次最小化时显示提示
            if not getattr(self, '_tray_msg_shown', False):
                self.system_provider.show_notification(self.tray_icon, "LaTeXSnipper", "已最小化到系统托盘")
                self._tray_msg_shown = True
        event.ignore()

    def truly_exit(self):
        self._force_exit = True
        if self.tray_icon:
            self.tray_icon.hide()
        # 先关闭窗口（触发 closeEvent 分支），再延迟真正退出
        try:
            self.close()
        except Exception:
            pass
        QTimer.singleShot(0, lambda: (self._graceful_shutdown(), QCoreApplication.quit()))

class PredictionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, model_wrapper: ModelWrapper, image: Image.Image, model_name: str):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name
        self.elapsed = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import time
        t0 = time.perf_counter()
        try:
            if self._cancelled or QThread.currentThread().isInterruptionRequested():
                self.elapsed = time.perf_counter() - t0
                self.failed.emit("已取消")
                return
            res = self.model_wrapper.predict(self.image, model_name=self.model_name)
            self.elapsed = time.perf_counter() - t0
            if self._cancelled or QThread.currentThread().isInterruptionRequested():
                self.failed.emit("已取消")
                return
            if not res or not res.strip():
                self.failed.emit("识别结果为空")
            else:
                self.finished.emit(res.strip())
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
            if self._cancelled or QThread.currentThread().isInterruptionRequested():
                self.failed.emit("已取消")
                return
            self.failed.emit(str(e))

class PdfPredictWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, model_wrapper: ModelWrapper, pdf_path: str, max_pages: int, model_name: str, output_format: str, dpi: int = 200):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.pdf_path = pdf_path
        self.max_pages = max_pages
        self.model_name = model_name
        self.output_format = output_format
        self.dpi = dpi
        self._cancelled = False
        self.elapsed = None

    def cancel(self):
        self._cancelled = True

    def run(self):
        import queue
        import threading
        import time
        t0 = time.perf_counter()
        def _set_elapsed():
            self.elapsed = time.perf_counter() - t0

        try:
            import fitz  # PyMuPDF
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"缺少 PyMuPDF 依赖: {e}")
            return
        try:
            doc = fitz.open(self.pdf_path)
        except Exception as e:
            _set_elapsed()
            self.failed.emit(f"PDF 打开失败: {e}")
            return

        total = min(max(self.max_pages, 1), doc.page_count or 1)
        try:
            doc.close()
        except Exception:
            pass

        render_queue = queue.Queue(maxsize=1)

        def _cancel_requested():
            return self._cancelled or QThread.currentThread().isInterruptionRequested()

        def _put_render_item(item):
            while not self._cancelled:
                try:
                    render_queue.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def _render_pages():
            render_doc = None
            try:
                render_doc = fitz.open(self.pdf_path)
                for page_index in range(total):
                    if self._cancelled:
                        break
                    page = render_doc.load_page(page_index)
                    pix = page.get_pixmap(dpi=self.dpi, alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    if not _put_render_item((page_index, img, [pix.width, pix.height])):
                        return
                _put_render_item(None)
            except Exception as exc:
                _put_render_item(exc)
            finally:
                try:
                    if render_doc is not None:
                        render_doc.close()
                except Exception:
                    pass

        render_thread = threading.Thread(
            target=_render_pages,
            name="MathCraftPdfRenderPrefetch",
            daemon=True,
        )
        render_thread.start()
        page_results = []
        try:
            while True:
                if _cancel_requested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                try:
                    item = render_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                i, img, image_size = item
                if hasattr(self.model_wrapper, "predict_result"):
                    result = self.model_wrapper.predict_result(img, model_name=self.model_name)
                else:
                    result = {"text": self.model_wrapper.predict(img, model_name=self.model_name)}
                if _cancel_requested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                if isinstance(result, dict):
                    result["page_index"] = i + 1
                    result.setdefault("image_size", image_size)
                    page_results.append(result)
                self.progress.emit(i + 1, total)
        except Exception as e:
            _set_elapsed()
            if self._cancelled or QThread.currentThread().isInterruptionRequested():
                self.failed.emit("已取消")
                return
            self.failed.emit(str(e))
            return
        clean_results = [
            page
            for page in page_results
            if isinstance(page, dict) and (str(page.get("text") or "").strip() or page.get("blocks"))
        ]
        from core.mathcraft_document_engine import compose_mathcraft_markdown_pages

        content = compose_mathcraft_markdown_pages(clean_results)
        if not content.strip():
            _set_elapsed()
            self.failed.emit("识别结果为空")
            return
        _set_elapsed()
        self.finished.emit(content.strip())
# ---------------- 编辑对话框 ----------------

class EditFormulaDialog(QDialog):
    def __init__(self, latex: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑")
        _apply_no_minimize_window_flags(self)
        self.resize(700, 500)
        self._theme_is_dark_cached = None

        lay = QVBoxLayout(self)
        
        # 编辑器
        self.editor = QTextEdit(self)
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setTabChangesFocus(True)
        self.editor.setPlainText(latex or "")
        self.editor.setMaximumHeight(150)
        lay.addWidget(self.editor)
        
        # 实时渲染预览区域
        from PyQt6.QtWidgets import QLabel
        preview_label = QLabel("实时预览:")
        lay.addWidget(preview_label)
        
        self._pending_latex = ""
        self.preview_view = None
        if ensure_webengine_loaded():
            self.preview_view = QWebEngineView()
            self.preview_view.setMinimumHeight(200)
            init_html, init_base_url = self._build_preview_payload(latex or "")
            self.preview_view.setHtml(init_html, init_base_url)
            self._pending_latex = latex or ""
            lay.addWidget(self.preview_view, 1)
            
            # 设置防抖定时器
            self._render_timer = QTimer(self)
            self._render_timer.setSingleShot(True)
            self._render_timer.timeout.connect(self._do_render)
            
            # 连接编辑器文本变化
            self.editor.textChanged.connect(self._on_text_changed)
        else:
            fallback = QLabel("WebEngine 未加载，无法预览")
            fallback.setStyleSheet(f"color: {_dialog_theme_tokens()['muted']}; padding: 20px;")
            lay.addWidget(fallback, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _apply_theme_styles(self, force: bool = False):
        dark = _is_dark_ui()
        if not force and self._theme_is_dark_cached is dark:
            return
        self._theme_is_dark_cached = dark
        if self.preview_view is not None:
            self._pending_latex = ""
            self._do_render()

    def _fallback_local_mathjax_base_url(self):
        from PyQt6.QtCore import QUrl
        # 编辑窗口固定使用本地 MathJax，避免受全局渲染模式（如 CDN）影响。
        candidates = []
        try:
            if APP_DIR and str(APP_DIR).strip():
                candidates.append(Path(APP_DIR) / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass
        try:
            exe_dir = Path(sys.executable).parent
            candidates.append(exe_dir / "_internal" / "assets" / "MathJax-3.2.2" / "es5")
            candidates.append(exe_dir / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass
        try:
            candidates.append(Path(__file__).parent / "assets" / "MathJax-3.2.2" / "es5")
        except Exception:
            pass

        for es5_dir in candidates:
            try:
                if es5_dir.exists():
                    return QUrl.fromLocalFile(str(es5_dir) + os.sep)
            except Exception:
                pass
        return QUrl()

    def _build_preview_payload(self, latex: str):
        text = str(latex or "").strip()
        # 编辑窗口固定使用本地 MathJax，不再异步切换到 LaTeX-SVG。
        return build_math_html(text), self._fallback_local_mathjax_base_url()

    def event(self, e):
        result = super().event(e)
        try:
            if e.type() in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange,
            ):
                self._apply_theme_styles()
        except Exception:
            pass
        return result
    
    def _on_text_changed(self):
        if hasattr(self, '_render_timer') and self._render_timer:
            self._render_timer.stop()
            self._render_timer.start(300)
    
    def _do_render(self):
        if not self.preview_view:
            return
        latex = self.editor.toPlainText().strip()
        if latex == self._pending_latex:
            return
        self._pending_latex = latex
        try:
            html, base_url = self._build_preview_payload(latex)
            self.preview_view.setHtml(html, base_url)
        except Exception as e:
            print(f"[EditDialog Render] 渲染失败: {e}")

    def closeEvent(self, event):
        try:
            if hasattr(self, '_render_timer') and self._render_timer:
                self._render_timer.stop()
        except Exception:
            pass
        return super().closeEvent(event)

    def value(self) -> str:
        return self.editor.toPlainText().strip()

# ==============================
# 🧩 环境隔离保护（非常关键）
# 防止 PyInstaller 或旧虚拟环境污染
# ==============================
for var in ("PYTHONHOME", "PYTHONPATH", "MATHCRAFT_HOME"):
    if var in os.environ:
        print(f"[DEBUG] 清除环境变量 {var}")
        os.environ.pop(var)

# 2) 先初始化日志，再打开 GUI 日志窗口，避免打包版 runtime-console.log 双写
_ensure_startup_splash(_startup_status_message("初始化日志..."))
init_app_logging()
_ensure_startup_splash(_startup_status_message("检查日志窗口设置..."))
open_debug_console(force=False, tee=True)

# 文件: 'src/main.py'（入口关键片段）
if __name__ == "__main__":
    import multiprocessing
    import os, sys
    multiprocessing.freeze_support()
    # 判断是否为 PyInstaller 打包环境
    if getattr(sys, 'frozen', False):
        # 打包环境，直接运行主程序，不再重启到私有解释器
        from PyQt6.QtWidgets import QApplication
        # 确保标准流可用
        _ensure_std_streams()
        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        splash = _take_startup_splash(app, _startup_status_message("初始化界面..."))
        open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"
        # 3) UI 主题（可选）
        try:
            from qfluentwidgets import setThemeColor
            apply_theme_mode(read_theme_mode_from_config())
            setThemeColor("#0078D4")
        except Exception:
            pass
        if open_wizard_on_start:
            _update_startup_splash(splash, _startup_status_message("检查依赖中..."))
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
            if not ok:
                sys.exit(1)
            splash = _take_startup_splash(app, _startup_deps_resume_message())
        if _startup_force_enter_pending():
            splash = _take_startup_splash(app, _startup_deps_resume_message())
        _update_startup_splash(splash, "初始化运行环境...")
        _update_startup_splash(splash, "加载主窗口...")
        win = MainWindow(startup_progress=lambda m: _update_startup_splash(splash, m))
        print("[DEBUG] MainWindow 创建完成，准备显示窗口")
        _update_startup_splash(splash, "主窗口已加载，正在显示...")
        win.show()
        win.start_post_show_tasks()
        QTimer.singleShot(0, lambda: open_debug_console(force=False, tee=True))
        _finish_startup_splash(splash, win)
        print("[DEBUG] win.show() 完成，进入事件循环")
        sys.exit(app.exec())
    else:
        # 开发环境，保留原有依赖检测和私有解释器重启逻辑
        from PyQt6.QtWidgets import QApplication
        _ensure_std_streams()
        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        splash = _take_startup_splash(app, _startup_status_message("初始化界面..."))
        open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"
        deps_check_message = _startup_status_message("检查依赖中...")
        _update_startup_splash(splash, deps_check_message)
        deps_ready_cached = (os.environ.get("LATEXSNIPPER_DEPS_OK") == "1")
        needs_interactive_deps_ui = bool(
            open_wizard_on_start or (not deps_ready_cached)
        )
        if open_wizard_on_start:
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True)
        else:
            ok = ensure_deps(prompt_ui=True, always_show_ui=False, from_settings=False)
        if not ok:
            sys.exit(1)
        resume_message = _startup_deps_resume_message()
        if needs_interactive_deps_ui or resume_message == _FORCE_ENTER_STARTUP_MESSAGE:
            splash = _take_startup_splash(app, resume_message)
        _update_startup_splash(splash, resume_message)
        try:
            from qfluentwidgets import setThemeColor
            apply_theme_mode(read_theme_mode_from_config())
            setThemeColor("#0078D4")
        except Exception:
            pass
        _update_startup_splash(splash, "初始化运行环境...")
        _update_startup_splash(splash, "加载主窗口...")
        win = MainWindow(startup_progress=lambda m: _update_startup_splash(splash, m))
        print("[DEBUG] MainWindow 创建完成，准备显示窗口")
        _update_startup_splash(splash, "主窗口已加载，正在显示...")
        win.show()
        win.start_post_show_tasks()
        QTimer.singleShot(0, lambda: open_debug_console(force=False, tee=True))
        _finish_startup_splash(splash, win)
        print("[DEBUG] win.show() 完成，进入事件循环")
        sys.exit(app.exec())

"""Application and GUI runtime logging helpers."""

from __future__ import annotations

import builtins
import io
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from runtime.app_paths import app_config_path, app_log_dir
from runtime.startup_splash import ensure_startup_splash, startup_status_message

APP_LOG_FILE: Path | None = None

_ORIGINAL_PRINT = None
_PRINT_BRIDGE_INSTALLED = False
_RUNTIME_SESSION_HANDLER = None
_APP_LOGGING_INITIALIZED = False
_LSN_DEBUG_CONSOLE_READY = False
_LSN_RUNTIME_LOG_DIALOG = None
_LSN_RUNTIME_LOG_PATH = None
_LSN_RUNTIME_LOG_FH_OUT = None
_LSN_RUNTIME_LOG_FH_ERR = None
_LSN_RUNTIME_LOG_RESET_DONE = False
_LSN_RUNTIME_LOG_CLEANUP_HOOKED = False


class TeeWriter(io.TextIOBase):
    """Write to two streams while tolerating I/O failures."""

    def __init__(self, a, b):
        self._a = a
        self._b = b
        self._closed = False
        self._b_line_buffer = ""
        self._original_a = a
        self._original_b = b

    @property
    def closed(self) -> bool:
        return self._closed

    def writable(self) -> bool:
        return True

    def _stream_ok(self, stream) -> bool:
        """Return whether the stream is usable."""
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
                    line = self._b_line_buffer[: idx + 1]
                    self._b.write(line)
                    self._b_line_buffer = self._b_line_buffer[idx + 1 :]
                written = len(s)
            except (OSError, ValueError, AttributeError):
                pass
            except Exception:
                pass

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
        self._closed = True

    def fileno(self):
        """Return the primary stream file descriptor when available."""
        for stream in (self._a, self._b):
            if self._stream_ok(stream) and hasattr(stream, "fileno"):
                try:
                    return stream.fileno()
                except Exception:
                    pass
        raise OSError("No valid file descriptor")


def init_app_logging() -> Path:
    """Initialize application logging and route output to the runtime log."""
    global APP_LOG_FILE, _RUNTIME_SESSION_HANDLER, _APP_LOGGING_INITIALIZED
    ensure_startup_splash(startup_status_message("初始化日志..."))
    log_dir = Path(app_log_dir())
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    if _APP_LOGGING_INITIALIZED and APP_LOG_FILE is not None:
        return APP_LOG_FILE

    root = logging.getLogger()
    root.setLevel(logging.INFO)

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
                        sys.__stderr__.write(f"[WARN] app.log 被占用，已切换到 {active_log_path}: {e}\n")
                except Exception:
                    pass
            except Exception as fallback_error:
                fh = None
                try:
                    if sys.__stderr__ and not getattr(sys.__stderr__, "closed", False):
                        sys.__stderr__.write(f"[WARN] 无法初始化文件日志，继续仅使用控制台日志: {fallback_error}\n")
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
        sh = logging.StreamHandler(sys.__stdout__)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    _RUNTIME_SESSION_HANDLER = None

    global _ORIGINAL_PRINT, _PRINT_BRIDGE_INSTALLED
    if (not _PRINT_BRIDGE_INSTALLED) and (file_handler is not None):
        _ORIGINAL_PRINT = builtins.print

        bridge_logger = logging.getLogger("runtime.print")
        bridge_logger.setLevel(logging.INFO)
        bridge_logger.propagate = False
        if not any(h is file_handler for h in bridge_logger.handlers):
            bridge_logger.addHandler(file_handler)

        def _print_bridge(*args, **kwargs):
            _ORIGINAL_PRINT(*args, **kwargs)
            try:
                target = kwargs.get("file", None)
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

    ensure_startup_splash(startup_status_message("初始化 LaTeX 设置..."))
    try:
        from backend.latex_renderer import init_latex_settings

        config_dir = Path.home() / ".latexsnipper"
        config_dir.mkdir(parents=True, exist_ok=True)
        init_latex_settings(config_dir)
        print("[LaTeX] 设置初始化完成")
    except Exception as e:
        print(f"[WARN] LaTeX 设置初始化失败: {e}")

    _APP_LOGGING_INITIALIZED = True
    return active_log_path


def runtime_log_path() -> Path:
    global _LSN_RUNTIME_LOG_PATH
    if _LSN_RUNTIME_LOG_PATH is not None:
        return _LSN_RUNTIME_LOG_PATH
    p = app_log_dir() / "runtime-console.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    _LSN_RUNTIME_LOG_PATH = p
    return p


def cleanup_runtime_log_session():
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
        p = runtime_log_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass
    _LSN_DEBUG_CONSOLE_READY = False


def ensure_runtime_log_cleanup_hook():
    global _LSN_RUNTIME_LOG_CLEANUP_HOOKED
    if _LSN_RUNTIME_LOG_CLEANUP_HOOKED:
        return
    try:
        app = QApplication.instance()
        if app is None:
            return
        app.aboutToQuit.connect(cleanup_runtime_log_session)
        _LSN_RUNTIME_LOG_CLEANUP_HOOKED = True
    except Exception:
        pass


def hook_runtime_log_streams(tee: bool = True):
    global _LSN_RUNTIME_LOG_FH_OUT, _LSN_RUNTIME_LOG_FH_ERR, _LSN_RUNTIME_LOG_RESET_DONE
    if _LSN_RUNTIME_LOG_FH_OUT is not None and _LSN_RUNTIME_LOG_FH_ERR is not None:
        return

    log_path = runtime_log_path()
    if not _LSN_RUNTIME_LOG_RESET_DONE:
        try:
            log_path.write_text("", encoding="utf-8")
        except Exception:
            pass
        _LSN_RUNTIME_LOG_RESET_DONE = True

    _LSN_RUNTIME_LOG_FH_OUT = open(log_path, "a", encoding="utf-8", buffering=1)
    _LSN_RUNTIME_LOG_FH_ERR = open(log_path, "a", encoding="utf-8", buffering=1)
    ensure_runtime_log_cleanup_hook()

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


def show_runtime_log_window(parent=None):
    global _LSN_RUNTIME_LOG_DIALOG
    app = QApplication.instance() or QApplication(sys.argv)
    log_path = runtime_log_path()
    if _LSN_RUNTIME_LOG_DIALOG is None:
        from ui.runtime_log_dialog import RuntimeLogDialog

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


def refresh_runtime_log_dialog_theme(force: bool = True) -> None:
    try:
        if _LSN_RUNTIME_LOG_DIALOG is not None and hasattr(_LSN_RUNTIME_LOG_DIALOG, "_apply_theme_styles"):
            _LSN_RUNTIME_LOG_DIALOG._apply_theme_styles(force=force)
    except Exception:
        pass


def open_debug_console(force: bool = False, tee: bool = True):
    """Open the scrollable and copyable GUI log window."""
    global _LSN_DEBUG_CONSOLE_READY

    if getattr(sys, "frozen", False):
        tee = False

    def _read_startup_console_pref(default: bool = False) -> bool:
        try:
            cfg = app_config_path()
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
            show_runtime_log_window()
            return
        hook_runtime_log_streams(tee=tee)
        show_runtime_log_window()
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

# --- Crash guard & runtime sanity, put this at the VERY TOP of 'src/main.py' ---
import os, sys, pathlib, datetime, faulthandler, json, subprocess
# --- 早期 GUI 依赖检测与自动修复 ---
import sys, os, subprocess, importlib

def _early_ensure_pyqt6_and_pywin32():
    import os, sys, subprocess, importlib
    pyexe = sys.executable
    exe_name = os.path.basename(pyexe).lower()
    # 仅在源码解释器模式启用早期 pip 自修复；打包 exe 不支持 `-m pip` 语义
    can_pip_repair = (not getattr(sys, "frozen", False)) and exe_name.startswith("python")
    if not can_pip_repair:
        print("[INFO] 打包模式或非 python 解释器启动，跳过早期 pip 自修复。")
        return

    # 检查 PyQt6
    try:
        import PyQt6
    except ImportError:
        print("[WARN] 未检测到 PyQt6，尝试自动安装...")
        subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "PyQt6-WebEngine~=6.9.0", "PyQt6-Fluent-Widgets"])
        importlib.invalidate_caches()
        import PyQt6
        print("[OK] PyQt6 安装成功。")
    else:
        # PyQt6 已存在，但可能缺少 WebEngine
        try:
            from PyQt6 import QtWebEngineWidgets  # noqa: F401
        except Exception:
            print("[WARN] 未检测到 PyQt6-WebEngine，尝试自动安装...")
            subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "PyQt6-WebEngine~=6.9.0"])
            importlib.invalidate_caches()

    # 检查 qfluentwidgets（PyQt6-Fluent-Widgets）
    try:
        import qfluentwidgets  # noqa: F401
    except ImportError:
        print("[WARN] 未检测到 PyQt6-Fluent-Widgets，尝试自动安装...")
        subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "PyQt6-Fluent-Widgets"])
        importlib.invalidate_caches()
        import qfluentwidgets  # noqa: F401
        print("[OK] PyQt6-Fluent-Widgets 安装成功。")

    # 检查 win32api
    try:
        import win32api
    except ImportError:
        print("[WARN] 未检测到 win32api，尝试自动安装 pywin32...")
        subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "pywin32"])
        importlib.invalidate_caches()
        # 关键：安装后直接提示用户重启
        print("[OK] pywin32 安装成功。请关闭并重新启动本程序以完成初始化。")
        import time
        time.sleep(2)
        sys.exit(0)

    # 检查 pyperclip
    try:
        import pyperclip  # noqa: F401
    except ImportError:
        print("[WARN] 未检测到 pyperclip，尝试自动安装...")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "pyperclip"])
            importlib.invalidate_caches()
            import pyperclip  # noqa: F401
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
        import requests  # noqa: F401
    except ImportError:
        print("[WARN] 未检测到 requests，尝试自动安装...")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "-U", "requests"])
            importlib.invalidate_caches()
            import requests  # noqa: F401
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

# 全局持有 crash 日志文件句柄，避免被 GC 或提前关闭
_CRASH_FH = None

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

# 5) 确保先创建 QApplication 再调用依赖修复/向导逻辑
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QHBoxLayout, QComboBox
from PyQt6.QtCore import Qt, QCoreApplication, QTimer
from pathlib import Path

# 必须在创建 QApplication 之前设置此属性（满足 QtWebEngine 的上下文共享要求）
try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

app = QApplication.instance() or QApplication(sys.argv)

_single_instance_lock = None

def _ensure_single_instance() -> bool:
    '''Prevent multiple GUI instances on Windows using a file lock.'''
    lock_dir = Path.home() / ".latexsnipper"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "instance.lock"
    restart_flag = os.environ.get("LATEXSNIPPER_RESTART") == "1"

    if os.name == "nt":
        try:
            import msvcrt
            attempts = 30 if restart_flag else 1
            delay = 0.2
            for _ in range(attempts):
                fh = open(lock_file, "a+", encoding="utf-8")
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


# ============ QWebEngine 运行环境预配置 ============
# 仅设置环境变量，不导入 WebEngine 模块
def _apply_webengine_env_overrides():
    """
    预先配置 WebEngine 相关环境变量，避免打包模式下进程/沙箱问题。
    通过环境变量开关，不强行改变默认行为。
    """
    # 用户可通过环境变量显式关闭沙箱
    if os.environ.get("LATEXSNIPPER_WEBENGINE_NO_SANDBOX") == "1":
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--no-sandbox" not in flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --no-sandbox").strip()
        print("[WebEngine] 已根据环境变量禁用沙箱 (QTWEBENGINE_DISABLE_SANDBOX=1)")

    # 尝试设置 QtWebEngineProcess.exe 的路径（如已设置则不覆盖）
    exe_name = "QtWebEngineProcess.exe" if os.name == "nt" else "QtWebEngineProcess"
    candidates = []
    try:
        if hasattr(sys, "_MEIPASS"):
            mp = pathlib.Path(sys._MEIPASS)
            candidates.extend([
                mp / "Qt6" / "bin" / exe_name,
                mp / "PyQt6" / "Qt6" / "bin" / exe_name,
            ])
        exe_dir = pathlib.Path(sys.executable).parent
        candidates.extend([
            exe_dir / "Qt6" / "bin" / exe_name,
            exe_dir / "PyQt6" / "Qt6" / "bin" / exe_name,
        ])
    except Exception:
        candidates = []

    cur = os.environ.get("QTWEBENGINEPROCESS_PATH")
    needs_fix = False
    if cur:
        try:
            p = pathlib.Path(cur)
            if p.is_dir() or not p.exists() or p.name.lower() != exe_name.lower():
                needs_fix = True
        except Exception:
            needs_fix = True

    if not cur or needs_fix:
        for p in candidates:
            if p and p.exists():
                os.environ["QTWEBENGINEPROCESS_PATH"] = str(p)
                print(f"[WebEngine] QTWEBENGINEPROCESS_PATH 已设置: {p}")
                break

_apply_webengine_env_overrides()

# ============ QWebEngine 沙箱配置 ============
# 在使用 QWebEngineView 之前配置，以确保 MathJax 资源可以被正确加载
try:
    from PyQt6.QtWebEngineCore import QWebEngineProfile
    
    profile = QWebEngineProfile.defaultProfile()
    
    # 1. 禁用 HTTP 缓存以避免缓存问题
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
    
    # 2. 获取 profile 的设置对象，并配置允许本地文件访问
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
        self._poll_file(initial=True)

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

    def _poll_file(self, initial: bool = False):
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

import logging
from logging.handlers import RotatingFileHandler
from PyQt6.QtWidgets import QMessageBox

# 移除重复的 CONFIG_FILENAME（已在文件顶部定义）
APP_LOG_FILE: Path | None = None

# 安全占位导入：修复“未解析 rapidocr”
try:
    import rapidocr  # type: ignore
except Exception:
    rapidocr = type("rapidocr", (), {})()  # 空对象，占位

# 注意：init_app_logging、open_realtime_log_window、_read_deps_dir_from_config、
# _ensure_constraints_file、open_deps_terminal 的定义见下方，此处移除了重复版本


def init_app_logging() -> Path:
    """
    初始化应用日志：控制台 + 轮转文件(~/.latexsnipper/logs/app.log)。
    多次调用会复用已存在的处理器。
    """
    global APP_LOG_FILE
    log_dir = Path.home() / ".latexsnipper" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 避免重复添加处理器
    has_file = any(isinstance(h, RotatingFileHandler) for h in root.handlers)
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers)

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    if not has_file:
        fh = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    if not has_stream:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    APP_LOG_FILE = log_path
    logging.info("日志初始化完成，文件: %s", log_path)
    
    # 初始化 LaTeX 设置
    try:
        config_dir = Path.home() / ".latexsnipper"
        config_dir.mkdir(parents=True, exist_ok=True)
        init_latex_settings(config_dir)
        print("[LaTeX] 设置初始化完成")
    except Exception as e:
        print(f"[WARN] LaTeX 设置初始化失败: {e}")
    
    return log_path

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
    从用户家目录`LaTeXSnipper_config.json`读取依赖目录。
    结构: { "install_base_dir": "D:/LaTeXSnipper/deps" }
    """
    cfg = Path.home() / "LaTeXSnipper_config.json"
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

def _ensure_constraints_file(deps_dir: Path) -> Path:
    """
    写入/复用约束文件，默认固定 numpy<2.0.0。
    """
    c = deps_dir / "constraints.txt"
    try:
        if not c.exists():
            c.write_text("numpy<2.0.0\n", encoding="utf-8")
    except Exception:
        pass
    return c

def open_deps_terminal(parent=None):
    """
    在依赖目录打开 cmd.exe，并预置:
    - PATH: <deps>/python311 优先
    - PIP_CONSTRAINT: <deps>/constraints.txt (写入 numpy<2.0.0)
    """
    deps_dir = _read_deps_dir_from_config()
    if not deps_dir or not deps_dir.exists():
        QMessageBox.warning(parent, "未找到依赖目录", "请先通过依赖向导选择或安装依赖目录。")
        return

    py_dir = deps_dir / "python311"
    pyexe = py_dir / "python.exe"
    cfile = _ensure_constraints_file(deps_dir)

    # 组装环境
    env = os.environ.copy()
    # 无论打包模式还是开发模式，都允许注入 python311 路径到 PATH
    if py_dir.exists():
        env["PATH"] = f"{py_dir};{env.get('PATH','')}"
    env["PIP_CONSTRAINT"] = str(cfile)

    # 进入目录并打开 cmd，显示简短提示
    banner = (
        f'echo LaTeXSnipper 依赖终端 ^| PIP_CONSTRAINT=%PIP_CONSTRAINT% && '
        f'where python && python --version && pip --version && '
        f'echo. && echo 建议: pip install -U --no-cache-dir --force-reinstall "numpy<2.0.0" && echo.'
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

def _qfw_set_titlebar_color(win, color: str = "transparent") -> bool:
    """
    兼容设置 FluentWindow 标题栏颜色：
    - 若有原生 setTitleBarColor 则直接调用
    - 否则尝试 titleBar() 对象的若干候选 API
    - 最后兜底用样式表或透明背景
    返回：是否设置成功
    """
    # 1) 直接调用窗口方法
    fn = getattr(win, "setTitleBarColor", None)
    if callable(fn):
        try:
            fn(color)
            return True
        except Exception:
            pass

    # 2) 访问 titleBar 对象
    bar = None
    tb_attr = getattr(win, "titleBar", None)
    if callable(tb_attr):
        try:
            bar = tb_attr()
        except Exception:
            bar = None
    elif tb_attr is not None:
        bar = tb_attr

    if bar is not None:
        # 尝试若干常见命名
        for name in ("setTitleBarColor", "setColor", "setBackgroundColor", "setBgColor", "setMaskColor"):
            m = getattr(bar, name, None)
            if callable(m):
                try:
                    m(color)
                    return True
                except Exception:
                    pass
        # 兜底样式
        try:
            if color in ("transparent", "rgba(0,0,0,0)"):
                bar.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                bar.setStyleSheet("background: transparent;")
            else:
                bar.setStyleSheet(f"background: {color};")
            return True
        except Exception:
            pass
    return False

# 安装类级别猴子补丁：让 win.setTitleBarColor(...) 依旧可用（无需改调用处）
def _install_titlebar_color_shim():
    try:
        from qfluentwidgets import FluentWindow as _FW
    except Exception:
        return
    if hasattr(_FW, "setTitleBarColor"):
        return
    def _shim(self, color: str = "transparent"):
        _qfw_set_titlebar_color(self, color)
    try:
        setattr(_FW, "setTitleBarColor", _shim)
    except Exception:
        pass

_install_titlebar_color_shim()

# AA_ShareOpenGLContexts 已在文件顶部 QApplication 创建前设置

def _qfw_set_border_radius(obj, radius: int = 12) -> bool:
    """
    兼容 qfluentwidgets 新旧版:
    - 新版: 直接调用 setBorderRadius
    - 旧版: 无该方法则忽略（可选为内容容器加圆角样式）
    返回: 是否成功调用到原生 API
    """
    fn = getattr(obj, "setBorderRadius", None)
    if callable(fn):
        try:
            fn(int(radius))
            return True
        except Exception:
            pass
    # 兜底：尽量给中心容器/自身加样式
    try:
        target = None
        cw = getattr(obj, "centralWidget", None)
        if callable(cw):
            target = cw()
        if target is None:
            container = getattr(obj, "container", None)
            target = container() if callable(container) else container
        if target is None:
            target = obj
        # 开启透明背景以便圆角生效（若支持）
        try:
            target.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except Exception:
            pass

        old_qss = ""
        try:
            old_qss = target.styleSheet() or ""
        except Exception:
            pass

        sep = ";" if old_qss and not old_qss.strip().endswith(";") else ""
        target.setStyleSheet(f"{old_qss}{sep}border-radius:{int(radius)}px;")
        return True
    except Exception:
        return False

def _install_border_radius_shim() -> None:
    """
    给 qfluentwidgets.FluentWindow 动态添加 setBorderRadius，避免旧版本缺失导致崩溃。
    """
    try:
        from qfluentwidgets import FluentWindow as _FW
    except Exception:
        return
    if hasattr(_FW, "setBorderRadius"):
        return

    def _shim(self, r: int = 12):
        _qfw_set_border_radius(self, r)

    try:
        setattr(_FW, "setBorderRadius", _shim)
    except Exception:
        pass
_install_border_radius_shim()

import sys, os
base_path = os.path.dirname(os.path.abspath(__file__))
# 确保全局仅一个 QApplication 实例
def ensure_qapp():
    """创建或获取唯一 QApplication 实例。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app

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

import os, sys, io, json
from pathlib import Path
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
print(f"[DEBUG] 模型目录: {MODEL_DIR}")
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
        for stream in (self._a, self._b):
            if not self._stream_ok(stream):
                continue
            try:
                stream.write(s)
                written = len(s)
            except (OSError, ValueError, AttributeError):
                # 流已关闭或损坏，静默忽略
                pass
            except Exception:
                pass

        # 只在写入成功后 flush
        for stream in (self._a, self._b):
            if not self._stream_ok(stream):
                continue
            try:
                stream.flush()
            except Exception:
                pass

        return written if written else len(s)

    def flush(self):
        if self._closed:
            return
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

def open_debug_console(force: bool = False, tee: bool = True):
    """在无控制台或打包态时打开控制台；`LATEXSNIPPER_SHOW_CONSOLE=1` 可强制。"""
    if os.name != "nt":
        return

    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        has_console = bool(k32.GetConsoleWindow())
    except Exception:
        has_console = False

    want = (
        force
        or os.environ.get("LATEXSNIPPER_SHOW_CONSOLE") == "1"
        or _is_packaged_mode()
        or not has_console
    )
    if not want:
        return

    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        attached = bool(k32.AttachConsole(-1))
        if not attached and not k32.AllocConsole():
            return

        try:
            k32.SetConsoleTitleW("LaTeXSnipper 初始化与依赖日志")
        except Exception:
            pass
        try:
            k32.SetConsoleCP(65001)
            k32.SetConsoleOutputCP(65001)
        except Exception:
            pass

        # 保存原始流引用（用于后续恢复）
        _original_stdout = sys.__stdout__
        _original_stderr = sys.__stderr__

        try:
            con_out = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            con_err = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        except Exception:
            # 无法打开控制台输出，跳过
            return

        try:
            con_in = open("CONIN$", "r", encoding="utf-8", buffering=1)
        except Exception:
            con_in = None

        # 记住当前 IDE/原始流
        base_out = sys.stdout if sys.stdout and not getattr(sys.stdout, "closed", False) else _original_stdout
        base_err = sys.stderr if sys.stderr and not getattr(sys.stderr, "closed", False) else _original_stderr

        # 避免嵌套 TeeWriter：如果已经是 TeeWriter，提取其原始流
        if isinstance(base_out, TeeWriter):
            base_out = base_out._original_a or _original_stdout
        if isinstance(base_err, TeeWriter):
            base_err = base_err._original_a or _original_stderr

        if tee and base_out and base_err:
            # 只在 tee 模式下用 TeeWriter 包一层，不关闭底层流
            sys.stdout = TeeWriter(base_out, con_out)
            sys.stderr = TeeWriter(base_err, con_err)
        else:
            # 不动 sys.stdout/sys.stderr，只是确保有控制台可以看输出
            # 如需在这里也输出到控制台，可以在 logging 里加 handler
            pass

        if (sys.stdin is None or getattr(sys.stdin, "closed", False)) and con_in:
            sys.stdin = con_in

        print("[INFO] 调试控制台已打开（UTF-8）。")
    except Exception as e:
        # 避免调试控制台问题反过来影响主程序
        # 尝试恢复标准流
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
    # 用户家目录保存配置
    return Path(os.path.expanduser("~")) / CONFIG_FILENAME

def _read_install_base_dir() -> Path | None:
    cfg = _config_path()
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text("utf-8"))
            p = Path(data.get("install_base_dir", "")).expanduser()
            if p and p.exists():
                return p
        except Exception:
            pass
    return None

def _select_install_base_dir() -> Path:
    """
    弹出目录选择对话框。返回用户选择的目录。
    - 如果用户取消，抛出 RuntimeError("user canceled")
    - 不会自动写入配置文件（由调用者决定）
    """
    from pathlib import Path
    try:
        from PyQt6.QtWidgets import QApplication, QFileDialog
        from qfluentwidgets import setTheme, Theme
        from PyQt6.QtGui import QFont
        app = QApplication.instance() or QApplication([])
        apply_theme("AUTO")
        font = QFont("Microsoft YaHei UI", 9)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
        d = QFileDialog.getExistingDirectory(None, "请选择依赖安装目录", os.path.expanduser("~"))
        if d:
            p = Path(d)
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

def _save_install_base_dir(p: Path) -> None:
    """保存依赖目录到配置文件。"""
    try:
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
    2. 如果为空，弹出目录选择对话框
    3. 检查选定目录是否已有 python311/
       - 有：使用该目录，保存配置，返回
       - 无：弹出确认框"确认要部署到此处吗？"
           - 确认：执行安装器（交互式），成功后保存配置，返回
           - 取消：清空配置文件，直接退出
    """
    import time
    import subprocess
    
    # 第1步：读取或选择依赖目录
    p = _read_install_base_dir()
    if not p:
        print("[INFO] 首次启动，请选择依赖安装目录...")
        try:
            p = _select_install_base_dir()
        except RuntimeError:
            print("[ERROR] 用户取消了目录选择，退出。")
            time.sleep(2)
            sys.exit(7)
    
    py311_dir = p / "python311"
    py_exe = py311_dir / "python.exe"
    
    # 第2步：检查 Python 是否已存在
    if py_exe.exists():
        print(f"[OK] ✓ Python 3.11 已在: {py_exe}")
        _save_install_base_dir(p)
        return p
    
    # 第3步：python311 不存在，需要安装
    print(f"[INFO] 检测到依赖未安装，位置: {py311_dir}")
    
    # 弹出确认框
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtGui import QFont, QIcon
        from qfluentwidgets import setTheme
        
        app = QApplication.instance() or QApplication([])
        apply_theme("AUTO")
        font = QFont("Microsoft YaHei UI", 9)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        app.setFont(font)
        
        msg_box = QMessageBox()
        msg_box.setWindowTitle("LaTeXSnipper - 部署确认")
        msg_box.setText("检测到 Python 3.11 环境未部署")
        msg_box.setInformativeText(
            f"确认要部署到以下位置吗？\n\n{p}\n\n"
            f"部署将需要几分钟时间，请保持网络连接。"
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
        
        # 窗口左上角设置软件图标
        try:
            icon_path = APP_DIR / "assets" / "icon.ico"
            if icon_path.exists():
                msg_box.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        
        result = msg_box.exec()
        
        if result != QMessageBox.StandardButton.Ok:
            print("[INFO] 用户取消了部署，清空配置并退出。")
            # 清空配置文件
            try:
                cfg_path = _config_path()
                if cfg_path.exists():
                    cfg_path.unlink()
                    print(f"[INFO] 已清空配置: {cfg_path}")
            except Exception as e:
                print(f"[WARN] 清空配置失败: {e}")
            time.sleep(2)
            sys.exit(7)
    except Exception as e:
        print(f"[WARN] 无法弹出确认框: {e}，继续部署...")
    
    # 第4步：执行安装器
    # 优先在 _MEIPASS（打包模式）查找，再在选定目录查找，再在项目根目录查找
    installer_exe = None
    
    # 1. 打包模式：从 _internal 目录查找
    if getattr(sys, '_MEIPASS', None):
        meipass_installer = Path(sys._MEIPASS) / "python-3.11.0-amd64.exe"
        if meipass_installer.exists():
            installer_exe = meipass_installer
            print(f"[INFO] 在 _internal 找到安装器: {installer_exe}")
    
    # 2. 如果还没找到，尝试在选定目录查找
    if not installer_exe or not installer_exe.exists():
        fallback_installer = p / "python-3.11.0-amd64.exe"
        if fallback_installer.exists():
            installer_exe = fallback_installer
            print(f"[INFO] 在依赖目录找到安装器: {installer_exe}")
    
    # 3. 开发模式下：尝试在项目根目录查找
    if not installer_exe or not installer_exe.exists():
        if not _is_packaged_mode():
            root_installer = Path(__file__).parent.parent / "python-3.11.0-amd64.exe"
            if root_installer.exists():
                installer_exe = root_installer
                print(f"[INFO] 在项目根目录找到安装器: {installer_exe}")
    
    if not installer_exe or not installer_exe.exists():
        msg = f"安装器未找到"
        print(f"[ERROR] {msg}")
        
        # 开发模式下允许重新选择
        if not _is_packaged_mode():
            print(f"[INFO] 开发模式：允许重新选择依赖目录")
            try:
                from PyQt6.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance() or QApplication([])
                
                msgbox = QMessageBox()
                msgbox.setWindowTitle("重新选择依赖目录")
                msgbox.setText("未在选定目录找到安装器或 Python 3.11 环境")
                msgbox.setInformativeText(
                    "请重新选择依赖目录。\n\n"
                    "提示：如果已在源码目录部署过（如 src/deps），可以选择该目录。"
                )
                msgbox.setStandardButtons(QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel)
                result = msgbox.exec()
                
                if result == QMessageBox.StandardButton.Retry:
                    print(f"[INFO] 用户选择重新选择目录")
                    # 清空配置并重新选择
                    try:
                        cfg_path = _config_path()
                        if cfg_path.exists():
                            cfg_path.unlink()
                    except Exception:
                        pass
                    # 递归调用自身以重新选择
                    return resolve_install_base_dir()
                else:
                    print(f"[INFO] 用户取消，退出")
                    try:
                        cfg_path = _config_path()
                        if cfg_path.exists():
                            cfg_path.unlink()
                    except Exception:
                        pass
                    time.sleep(2)
                    sys.exit(7)
            except Exception as e:
                print(f"[ERROR] 对话框异常: {e}")
                try:
                    cfg_path = _config_path()
                    if cfg_path.exists():
                        cfg_path.unlink()
                except Exception:
                    pass
                time.sleep(2)
                sys.exit(8)
        else:
            # 打包模式下找不到安装器是真的错误
            msg = f"安装器未找到\n\n期望位置：{Path(sys._MEIPASS) if getattr(sys, '_MEIPASS', None) else '?'}/python-3.11.0-amd64.exe\n\n无法继续部署。"
            print(f"[ERROR] {msg}")
            # 清空配置文件
            try:
                cfg_path = _config_path()
                if cfg_path.exists():
                    cfg_path.unlink()
            except Exception:
                pass
            try:
                from PyQt6.QtWidgets import QApplication, QMessageBox
                app = QApplication.instance() or QApplication([])
                QMessageBox.critical(None, "错误", msg)
            except Exception:
                pass
            time.sleep(2)
            sys.exit(8)
    
    print(f"[INFO] 即将启动安装器...")
    print(f"[INFO] 安装器: {installer_exe}")
    print(f"[INFO] 安装目标: {py311_dir}")
    
    try:
        # 交互式运行安装器
        proc = subprocess.Popen([str(installer_exe)])
        ret = proc.wait(timeout=900)  # 等待最多15分钟
        print(f"[INFO] 安装器进程结束（返回码: {ret}）")
        # 给系统时间完成文件操作
        time.sleep(2)
    except subprocess.TimeoutExpired:
        print(f"[ERROR] 安装器超时（15分钟）")
        proc.kill()
        # 清空配置文件
        try:
            cfg_path = _config_path()
            if cfg_path.exists():
                cfg_path.unlink()
        except Exception:
            pass
        time.sleep(2)
        sys.exit(8)
    except Exception as e:
        print(f"[ERROR] 运行安装器失败: {e}")
        # 清空配置文件
        try:
            cfg_path = _config_path()
            if cfg_path.exists():
                cfg_path.unlink()
        except Exception:
            pass
        time.sleep(2)
        sys.exit(8)
    
    # 第5步：检查安装是否成功
    if py_exe.exists():
        print(f"[OK] ✓ Python 3.11 安装成功！")
        _save_install_base_dir(p)
        return p
    else:
        msg = f"Python 3.11 部署失败\n\n期望位置: {py_exe}\n\n请检查安装器是否正确运行。"
        print(f"[ERROR] {msg}")
        # 清空配置文件
        try:
            cfg_path = _config_path()
            if cfg_path.exists():
                cfg_path.unlink()
        except Exception:
            pass
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            QMessageBox.critical(None, "部署失败", msg)
        except Exception:
            pass
        time.sleep(2)
        sys.exit(8)

    (p / "models").mkdir(parents=True, exist_ok=True)
    (p / "deps").mkdir(parents=True, exist_ok=True)
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

# 导入清理：以下导入已在文件顶部完成，这里不再重复
import re
import ctypes
import importlib

def _python_base_from_exe(pyexe: str) -> Path:
    p = Path(pyexe)
    return p.parent.parent if p.parent.name.lower() == "scripts" else p.parent

def _stdlib_zip_paths(base: Path) -> list[str]:
    try:
        return [str(p) for p in base.glob("python*.zip")]
    except Exception:
        return []

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
            import win32api
        except ImportError:
            return False
        # 触发一次 Qt 核心模块加载，尽早暴露 DLL 问题
        from PyQt6.QtCore import QT_VERSION_STR  # noqa: F401
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
    """用私有解释器在“新控制台子进程”重启，避免 os.execve 引发的崩溃。"""
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
    CREATE_NEW_CONSOLE = 0x00000010
    try:
        subprocess.Popen(argv, env=env, creationflags=CREATE_NEW_CONSOLE)
    except Exception as e:
        print(f"[ERROR] 启动子进程失败: {e}")
        sys.exit(6)
    sys.exit(0)

def _native_message_box(title: str, text: str, flags: int = 0x00000040 | 0x00000004) -> int:
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
            subprocess.check_call(cmd, env=env)
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
        print("[OK] GUI 依赖已就绪，不弹窗。")
        return

    # 检查 win32api 缺失，自动补装 pywin32
    try:
        import win32api
    except ImportError:
        print("[INFO] 检测到 win32api 缺失，自动安装 pywin32")
        _run_pip_install(pyexe, ["pywin32"])
        # 安装后重试
        if _try_import_gui():
            print("[OK] pywin32 安装完成，GUI 依赖已就绪。")
            return
    shown_cmd = (f"{pyexe} -m pip install -U PyQt6 PyQt6-Fluent-Widgets"
                 if pyexe else "python -m pip install -U PyQt6 PyQt6-Fluent-Widgets")
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

    ok = _run_pip_install(pyexe, ["PyQt6", "PyQt6-Fluent-Widgets"])
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

def enforce_private_runtime(base_dir: Path):
    if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") == "1":
        return

    # 指定安装根目录，并清理干扰变量
    os.environ.setdefault("LATEXSNIPPER_INSTALL_BASE_DIR", str(base_dir))
    for var in ("PYTHONHOME", "PYTHONPATH"):
        os.environ.pop(var, None)
    os.environ.setdefault("PYTHONNOUSERSITE", "1")

    # 准备私有解释器
    pyexe = None
    try:
        import importlib
        db = importlib.import_module("deps_bootstrap")
        db.ensure_deps(prompt_ui=False, always_show_ui=False, require_layers=("BASIC", "CORE"))
        pyexe = os.environ.get("LATEXSNIPPER_PYEXE")
        if not pyexe:
            for c in (base_dir / "venv" / "Scripts" / "python.exe",
                      base_dir / "python_full" / "python.exe"):
                if c.exists():
                    pyexe = str(c); break
    except Exception as e:
        print(f"[WARN] ensure_deps 失败，将尝试继续: {e}")

    need_switch = bool(pyexe and os.path.exists(pyexe) and not _same_exe(sys.executable, pyexe))
    if not need_switch:
        _sanitize_sys_path(pyexe, base_dir)
        _ensure_gui_deps_or_prompt(pyexe)
        return

    # 在 IDE 中：跳过重启，但先注入路径并确保 GUI 依赖
    if _in_ide() or os.environ.get("LATEXSNIPPER_DEV_NO_RESTART") == "1":
        print(f"[INFO] IDE/开发模式，跳过重启，继续使用当前进程，但改用私有依赖路径。目标解释器: {pyexe}")
        _sanitize_sys_path(pyexe, base_dir)
        _ensure_gui_deps_or_prompt(pyexe)
        return

    # 非 IDE：以新控制台启动私有解释器，然后立即退出当前进程
    try:
        env = os.environ.copy()
        env["LATEXSNIPPER_BOOTSTRAPPED"] = "1"
        env["PYTHONNOUSERSITE"] = "1"
        CREATE_NEW_CONSOLE = 0x00000010
        argv = [pyexe, os.path.abspath(__file__), *sys.argv[1:]]
        print(f"[INFO] 切换到私有解释器（新控制台）: {pyexe}")
        subprocess.Popen(argv, env=env, creationflags=CREATE_NEW_CONSOLE)
    finally:
        os._exit(0)

# --- 放在最前面的辅助 ---
import os, sys
from pathlib import Path

def _norm_path(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().strip('"').strip("'").strip()

def _clean_bad_env():
    """移除/修复坏掉的 LATEXSNIPPER_PYEXE，避免污染后续检测。"""
    val = os.environ.get("LATEXSNIPPER_PYEXE")
    p = _norm_path(val)
    if not p or not os.path.exists(p):
        os.environ.pop("LATEXSNIPPER_PYEXE", None)

# --- _find_full_python：仅认安装目录与 PATH，不再读取环境变量 ---
import shutil

def _has_ensurepip_venv(pyexe: str) -> bool:
    try:
        import subprocess
        r = subprocess.run([pyexe, "-c", "import ensurepip, venv;print('ok')"],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False

def _find_full_python(base_dir: Path) -> str | None:
    """强制优先 base_dir/python311；不使用环境变量候选。"""
    if getattr(sys, "frozen", False):
        # 打包模式下只认 _internal/python311，不查找其它路径
        pyexe = base_dir / "python311" / "python.exe"
        installer = base_dir / "python-3.11.0-amd64.exe"
        if pyexe.exists() and _has_ensurepip_venv(str(pyexe)):
            return str(pyexe)
        # 自动静默安装
        if installer.exists():
            if _run_python_installer(installer, base_dir / "python311"):
                pyexe = base_dir / "python311" / "python.exe"
                if pyexe.exists() and _has_ensurepip_venv(str(pyexe)):
                    return str(pyexe)
        return None
    # 开发模式：保留原有多路径查找
    candidates: list[Path] = [
        base_dir / "python311" / "python.exe",
        base_dir / "python311" / "Scripts" / "python.exe",
        base_dir / "Python311" / "python.exe",
        base_dir / "Python311" / "Scripts" / "python.exe",
        base_dir / "python_full" / "python.exe",
    ]
    for c in candidates:
        try:
            if c and c.exists() and _has_ensurepip_venv(str(c)):
                return str(c)
        except Exception:
            pass
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
        r = subprocess.run(args, timeout=600)
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
            print(f"[INFO] (打包模式) 使用内置 Python: {py}")
            return py
        print("[ERROR] (打包模式) 缺失 _internal/python311，且未找到安装器，无法启动。")
        sys.exit(10)
    # 开发模式：保留原有多路径查找和安装逻辑
    py = _find_full_python(base_dir)
    if py:
        print(f"[INFO] 使用已下载的 Python: {py}")
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

# --- 启动顺序修正：先确定 TARGET_PY，再决定是否重启 ---
# 注意：_same_exe、_in_ide、_relaunch_with、_run_python_installer 已在上方定义，此处移除重复

from deps_bootstrap import custom_warning_dialog, clear_deps_state
from settings_window import SettingsWindow

# 1) 打开调试控制台（尽早）
open_debug_console(force=False, tee=True)

# 2) 解析/选择安装目录
from pathlib import Path
INSTALL_BASE_DIR = resolve_install_base_dir()

# 3) 打包模式下：检查是否需要重定向到私有解释器
if _is_packaged_mode():
    py311_dir = INSTALL_BASE_DIR / "python311"
    py_exe = py311_dir / "python.exe"

    if py_exe.exists():
        if os.environ.get("LATEXSNIPPER_FORCE_PRIVATE_PY") == "1":
            # redirect only when explicitly enabled
            if os.environ.get("LATEXSNIPPER_INNER_PY") != "1":
                print(f"[INFO] packaged: redirect to private python {py_exe}")
                import subprocess
                env = os.environ.copy()
                env["LATEXSNIPPER_INNER_PY"] = "1"
                argv = [str(py_exe), os.path.abspath(__file__), *sys.argv[1:]]
                subprocess.Popen(argv, env=env)
                sys.exit(0)
            else:
                print("[INFO] packaged: already in private python")
        else:
            print("[INFO] packaged: keep bundled runtime, mount deps dir")
    else:
        print(f"[WARN] packaged: private python not found: {py_exe}, keep bundled runtime")

BASE_DIR = Path(INSTALL_BASE_DIR)
_clean_bad_env()

TARGET_PY = ensure_full_python_or_prompt(BASE_DIR)
if not TARGET_PY:
    print("[ERROR] 未找到可用的完整 Python 3.11。")
    sys.exit(2)

# 固定环境，禁止外部干扰
os.environ["LATEXSNIPPER_PYEXE"] = TARGET_PY
os.environ.setdefault("LATEXSNIPPER_INSTALL_BASE_DIR", str(BASE_DIR))
os.environ.setdefault("PYTHONNOUSERSITE", "1")
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)

# 5) IDE 模式下的路径注入（非打包模式）
if not _in_ide() and not _is_packaged_mode():
    if not _same_exe(sys.executable, TARGET_PY):
        _relaunch_with(TARGET_PY)
elif _in_ide():
    print(f"[INFO] IDE 中运行，保持当前解释器，但使用私有依赖路径")

# 只有在非 BOOTSTRAPPED 模式下才修改 sys.path
if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1":
    _sanitize_sys_path(TARGET_PY, BASE_DIR)
    if _is_packaged_mode():
        _append_private_site_packages(TARGET_PY)
        _block_pyqt6_from_private(TARGET_PY)
    else:
        _ensure_gui_deps_or_prompt(TARGET_PY)

    # 5) Run deps wizard once (explicit UI)
    # Pass BASE_DIR to avoid repeated prompts
    import importlib as _imp
    _db = _imp.import_module("deps_bootstrap")
    try:
        _ok = _db.ensure_deps(
            prompt_ui=True,
            always_show_ui=True,
            require_layers=("BASIC", "CORE"),
            deps_dir=str(BASE_DIR),
        )
        if _ok:
            os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
    except Exception as e:
        print(f"[WARN] deps wizard failed: {e}")

def ensure_deps(*args, **kwargs):
    # 已就绪则直接返回 True，避免再次尝试 venv/构建 UI
    # 但从设置页进入（from_settings/force_verify）时必须执行真实校验，不能被短路
    from_settings = bool(kwargs.get("from_settings", False))
    force_verify = bool(kwargs.get("force_verify", False))
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not (from_settings or force_verify):
        return True
    # 真需要时再按需引入并调用（通常用不到）
    import deps_bootstrap as _db
    ok = _db.ensure_deps(*args, **kwargs)
    if ok:
        os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
    return ok
def show_dependency_wizard(always_show_ui=False):
    # 默认不展示；仅在明确需要时才展示（always_show_ui=True）
    if os.environ.get("LATEXSNIPPER_DEPS_OK") == "1" and not always_show_ui:
        return
    try:
        import deps_bootstrap as _db
        # 严格仅在缺失时才让底层决定是否展示
        return _db.show_dependency_wizard(always_show_ui=False)
    except Exception as e:
        print(f"[WARN] 依赖向导不可用: {e}")
        return
from PyQt6.QtWidgets import QApplication, QFileDialog, QSizePolicy
from qfluentwidgets import MessageBox, TitleLabel, BodyLabel
import re
import pyperclip
from pathlib import Path
import traceback
import sys, os
import json
# 修正路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
from backend.model import ModelWrapper
from backend.capture_overlay import ScreenCaptureOverlay
from backend.latex_renderer import init_latex_settings, get_latex_renderer
import importlib
from qfluentwidgets import (
    setTheme, Theme, FluentIcon,
    InfoBar, InfoBarPosition, MessageBox, PrimaryPushButton
)
from pathlib import Path
def get_app_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).parent

APP_DIR = get_app_dir()
print(f"[DEBUG] 主程序目录: {APP_DIR}")

def lazy_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        print(f"[WARN] 模块 {module_name} 未安装。")
        return None

def try_load_torch():
    try:
        import torch
        return torch
    except ModuleNotFoundError:
        print("[WARN] 未安装 torch（HEAVY_GPU 层），跳过 GPU 模块初始化。")
        return None

def parse_requirements(req_path):
    reqs = {}
    if os.path.exists(req_path):
        with open(req_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    name = re.split(r'[<>=!~ ]', line, 1)[0].strip().lower()
                    reqs[name] = line
    return reqs

# 统一把 FluentWindow 弹窗改为 QDialog，移除重复 dlg 赋值

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidgetItem
from qfluentwidgets import BodyLabel, PrimaryPushButton, MessageBox

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

def show_gpu_install_tip(parent=None):
    cmd = r'.\.venv\Scripts\python.exe -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu118'
    pyperclip.copy(cmd)

    dlg = QDialog(parent)
    _apply_close_only_window_flags(dlg)
    dlg.setWindowTitle("安装 GPU 依赖")
    lay = QVBoxLayout(dlg)
    lay.addWidget(BodyLabel("如需 GPU 加速，请在终端运行以下命令安装 CUDA 版本："))
    lay.addWidget(BodyLabel(cmd))
    lay.addWidget(BodyLabel("命令已复制到剪贴板。"))
    btn = PushButton(FluentIcon.CLOSE, "关闭")
    btn.setFixedHeight(32)
    btn.clicked.connect(dlg.accept)
    lay.addWidget(btn)
    dlg.exec()

def show_missing_deps_dialog(missing_pkgs, parent=None):
    dlg = QDialog(parent)
    _apply_close_only_window_flags(dlg)
    dlg.setWindowTitle("缺失依赖")
    dlg.setModal(True)

    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("检测到缺失依赖，请下载安装："))
    for pkg in missing_pkgs:
        lay.addWidget(QLabel(f"- {pkg}"))
    lay.addWidget(QLabel("下载后需重启应用。"))

    btn_row = QHBoxLayout()
    btn_download = PushButton(FluentIcon.DOWNLOAD, "下载")
    btn_cancel = PushButton(FluentIcon.CLOSE, "取消")
    btn_download.setFixedHeight(32)
    btn_cancel.setFixedHeight(32)
    btn_row.addWidget(btn_download)
    btn_row.addWidget(btn_cancel)
    lay.addLayout(btn_row)

    result = {"download": False}
    btn_download.clicked.connect(lambda: (result.update({"download": True}), dlg.accept()))
    btn_cancel.clicked.connect(dlg.reject)

    return dlg.exec() == QDialog.DialogCode.Accepted and result["download"]

# 注意：show_confirm_dialog 方法已移至 MainWindow 类中

def get_install_base_dir():
    config_path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "install_base_dir" in cfg and os.path.isdir(cfg["install_base_dir"]):
                return cfg["install_base_dir"]
        except Exception:
            pass
    # 未设置，弹窗选择
    app = QApplication.instance() or QApplication([])
    from qfluentwidgets import setFont, Theme, setTheme
    apply_theme("AUTO")
    from PyQt6.QtGui import QFont
    font = QFont("Microsoft YaHei UI", 9)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    dir_ = QFileDialog.getExistingDirectory(None, "请选择主安装目录下的_internal", os.path.expanduser("~"))
    if not dir_:
        msg = MessageBox("错误", "未选择安装目录_internal，程序将退出。", None).exec()
        msg.exec()
        sys.exit(1)
    # 保存到配置
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    cfg["install_base_dir"] = dir_
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return dir_
# 在 main.py 最前面调用
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(DEPS_DIR, exist_ok=True)
if os.name == "nt":
    import msvcrt
    def singleton_lock(lockfile):
        try:
            fp = open(lockfile, "w")
            msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
            return fp
        except OSError:
            return None
else:
    import fcntl
    def singleton_lock(lockfile):
        try:
            fp = open(lockfile, "w")
            fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fp
        except OSError:
            return None

_ocr_loaded = False
_rapidocr_engine = None
_rapidocr_module = None
def get_ocr_backend():
    """
    懒加载 OCR 依赖；若未安装则静默禁用 OCR 功能。
    """
    global _ocr_loaded, _rapidocr_module
    if _rapidocr_module is not None:
        return _rapidocr_module

    if not _ocr_loaded:
        try:
            import rapidocr as _rapidocr  # noqa: F401
        except ModuleNotFoundError:
            print("[OCR] rapidocr 未安装，OCR 功能已禁用。")
            return None
        _rapidocr_module = _rapidocr
        _ocr_loaded = True
    return _rapidocr_module
def run_ocr(img_src):
    global _rapidocr_engine
    rapidocr = get_ocr_backend()
    if rapidocr is None:
        return ""

    # 延迟导入依赖
    from pathlib import Path
    from io import BytesIO
    from PIL import Image
    import numpy as np
    def to_ndarray(src):
        # 文件路径
        if isinstance(src, (str, Path)):
            return np.array(Image.open(src).convert("RGB"))
        # PIL.Image
        if isinstance(src, Image.Image):
            return np.array(src.convert("RGB"))
        # Qt 图像
        try:
            from PyQt6.QtGui import QPixmap, QImage
            if isinstance(src, QPixmap):
                qimg = src.toImage()
                return to_ndarray(qimg)
            if isinstance(src, QImage):
                buf = qimg_to_bytes(src)
                return np.array(Image.open(BytesIO(buf)).convert("RGB"))
        except Exception:
            pass
        # bytes
        if isinstance(src, (bytes, bytearray)):
            return np.array(Image.open(BytesIO(src)).convert("RGB"))
        raise TypeError(f"不支持的 img_src 类型: {type(src)}")

    def qimg_to_bytes(qimg):
        from PyQt6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        qimg.save(buf, "PNG")
        data = bytes(buf.data())
        buf.close()
        return data
    img = to_ndarray(img_src)
    # 2. 初始化引擎（一次）
    if _rapidocr_engine is None:
        # 兼容不同 rapidocr 版本的入口
        engine = None
        # v3.x 典型: from rapidocr import RapidOCR
        if hasattr(rapidocr, "RapidOCR"):
            engine = rapidocr.RapidOCR()
        else:
            # 兜底：某些版本 main.RapidOCR
            # 修复未解析 rapidocr：安全占位导入
            try:
                import rapidocr  # type: ignore
            except Exception:
                rapidocr = None  # type: ignore
                pass
        if engine is None:
            raise RuntimeError("未找到 RapidOCR 引擎入口 (RapidOCR 类缺失)")
        _rapidocr_engine = engine
    engine = _rapidocr_engine
    # 3. 推理
    try:
        result = engine(img)  # 常见返回: ([(text, box, score), ...], elapse) 或 (text_lines, elapse)
    except Exception as e:
        print(f"[OCR] 调用失败: {e}")
        return ""
    # 4. 解析结果
    def extract_text(res):
        if not res:
            return ""
        # 结构 (lines, elapse)
        if isinstance(res, (list, tuple)) and len(res) == 2 and isinstance(res[0], (list, tuple)):
            lines = res[0]
        else:
            lines = res
        collected = []
        for item in lines:
            # item 可能是 (text, box, score) 或 dict
            if isinstance(item, (list, tuple)):
                if item:
                    collected.append(str(item[0]))
            elif isinstance(item, dict):
                t = item.get("text") or item.get("label")
                if t:
                    collected.append(str(t))
            elif isinstance(item, str):
                collected.append(item)
        return "\n".join(t.strip() for t in collected if t and t.strip())
    return extract_text(result)
import os, sys, subprocess, importlib, importlib.metadata
FORCE_CPU = False # 若为 True 则强制使用 CPU
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("ORT_DISABLE_AZURE", "1")

def _ensure_typing_ext():
    """确保 typing_extensions 至少为 4.9.0，但不强制降级，避免与 pydantic 等冲突。"""
    import subprocess, logging

    try:
        subprocess.check_call([
            TARGET_PY, "-m", "pip", "install",
            "--upgrade", "typing_extensions>=4.9.0"
        ])
        logging.info("typing_extensions 已升级到兼容版本（>=4.9.0）")
    except Exception as e:
        logging.error("typing_extensions 安装/升级失败: %s", e)

def _ensure_hf_hub():
    try:
        import huggingface_hub
        from packaging.version import Version
        if Version(huggingface_hub.__version__) < Version("0.34.0"):
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "--no-cache-dir", "huggingface-hub>=0.34.0,<1.0"
            ])
    except Exception as e:
        print("[Boot] huggingface-hub check skipped:", e)
def _select_device():
    if FORCE_CPU:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        return "cpu(forced)"
    try:
        import torch
        if torch.cuda.is_available():
            return f"cuda:0 (name={torch.cuda.get_device_name(0)})"
        return "cpu"
    except Exception as e:
        return f"cpu(no_torch:{e})"
_ensure_typing_ext()
_ensure_hf_hub()
print("[INFO] 设备:", _select_device())

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
from PyQt6.QtWidgets import QWidgetAction
from PyQt6.QtGui import QCursor
import weakref
try:
    import sip  # PyQt6>=6.5
except Exception:
    sip = None

import sys
import json
from io import BytesIO
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QVBoxLayout, QListWidget, QMenu, QInputDialog, QProgressDialog
from qfluentwidgets import PrimaryPushButton
# ========== Fluent UI 样式 ==========
from qfluentwidgets import (
    PrimaryPushButton, PushButton,
    setTheme, Theme, InfoBar, InfoBarPosition, MessageBox
)

from PyQt6.QtCore import Qt, QObject, QThread, QCoreApplication, QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut, QDesktopServices
import pyperclip
from PIL import Image

# 绝对导入（依赖 backend/__init__.py 与 backend/qhotkey/__init__.py）
from backend.qhotkey import QHotkey, GlobalHotkey
from updater import check_update_dialog

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QSystemTrayIcon,
                             QDialog, QTextEdit, QHBoxLayout, QScrollArea, QSplitter)
from PyQt6.QtCore import QBuffer, QIODevice, QPropertyAnimation, QEasingCurve, pyqtSignal

from backend.capture_overlay import ScreenCaptureOverlay
from backend.model import ModelWrapper
flags = [
    "--use-angle=d3d11",
    "--ignore-gpu-blocklist",
    "--enable-logging=stderr",
    "--v=1",
]
ACTION_BTN_STYLE = (
    "PrimaryPushButton{background:#3daee9;color:#fff;border-radius:4px;"
    "padding:4px 10px;font-size:12px;}"
    "PrimaryPushButton:hover{background:#5dbff2;}"
)
# ---------------- 获取 PyInstaller 打包路径 ----------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

# 样式常量
HOVER_STYLE_BASE = "QWidget{background:#fefefe;border:1px solid #cfcfcf;border-radius:5px;padding:6px;}"
HOVER_STYLE_ACTIVE = "QWidget{background:#ffffff;border:1px solid #999;border-radius:5px;padding:6px;}"

# 行内（历史记录每行的小按钮）紧凑描边样式
INLINE_BUTTON_STYLE = (
    "PrimaryPushButton{background:#ffffff;border:1px solid #d0d7de;"
    "border-radius:4px;padding:3px 8px;font-size:12px;color:#1976d2;}"
    "PrimaryPushButton:hover{background:#f0f7ff;}"
    "PrimaryPushButton:pressed{background:#e2efff;}"
)

MAX_HISTORY = 200
ENABLE_ROW_ANIMATION = False    # 历史记录行动画开关
SAFE_MINIMAL = True          # 第一步：最小化测试开关
DISABLE_GLOBAL_HOTKEY = False # 若为 True 不注册全局热键
DEFAULT_FAVORITES_NAME = "favorites.json"
DEFAULT_HISTORY_NAME = "history.json"

# ---------------- MathJax 实时渲染模板 ----------------
# MathJax 3.2.2 是稳定版本，v4.0+ 可能有兼容性问题
MATHJAX_CDN_URL = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
# 备用CDN（如主CDN不可用）
MATHJAX_CDN_URL_BACKUP = "https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js"

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
  background: #fafafa;
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
  color: #1976d2;
  background: #e3f2fd;
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
  color: #d32f2f;
  font-size: 12px;
  padding: 8px;
  background: #ffebee;
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
      scale: 1.2
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
    console.warn('[MathJax] 本地加载失败，尝试使用 CDN...');
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

def _get_mathjax_base_url():
    """获取 MathJax 的 base URL (用于 setHtml)
    
    这个函数必须返回一个指向 es5 目录的 file:// URL，
    这样 tex-mml-chtml.js 才能被正确加载。
    
    支持开发模式和 PyInstaller 打包后的两种运行环境。
    """
    from PyQt6.QtCore import QUrl
    from pathlib import Path
    import sys
    import os
    
    try:
        # 首先检查当前选择的渲染模式
        try:
            from backend.latex_renderer import _latex_settings
            if _latex_settings:
                mode = _latex_settings.get_render_mode()
                # 如果选择了 CDN MathJax，返回 CDN URL
                if mode == "mathjax_cdn":
                    print("[MathJax] 使用 CDN MathJax")
                    cdn_url = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/"
                    return QUrl(cdn_url)
                # 如果选择了 LaTeX，不返回 MathJax URL（在渲染逻辑中单独处理）
                elif mode and mode.startswith("latex_"):
                    print(f"[MathJax] 使用 LaTeX 渲染模式: {mode}")
                    return QUrl()  # 返回空 URL
        except Exception as e:
            print(f"[WARN] 获取渲染模式失败: {e}")
        
        # 否则使用本地 MathJax
        # 第1步：确定 APP_DIR
        actual_app_dir = None
        
        # 优先使用全局 APP_DIR（已初始化的情况）
        if APP_DIR and str(APP_DIR).strip():
            actual_app_dir = Path(APP_DIR)
        
        # 如果 APP_DIR 为空或不可用，尝试其他方法
        if not actual_app_dir or not str(actual_app_dir).strip():
            # 打包模式检查：sys.frozen 表示 PyInstaller 打包
            if getattr(sys, 'frozen', False):
                # 打包后：exe 所在目录的 _internal 或同级 src
                exe_dir = Path(sys.executable).parent
                # 尝试 _internal/assets (PyInstaller --onedir)
                if (exe_dir / "_internal" / "assets").exists():
                    actual_app_dir = exe_dir / "_internal"
                    print(f"[MathJax] 检测到打包模式，使用 _internal: {actual_app_dir}")
                # 尝试 assets (PyInstaller --onefile 解包目录)
                elif (exe_dir / "assets").exists():
                    actual_app_dir = exe_dir
                    print(f"[MathJax] 检测到打包模式，使用 exe 同级: {actual_app_dir}")
                else:
                    # 最后尝试：还原到 exe 目录往上查找
                    parent = exe_dir.parent
                    if (parent / "src" / "assets").exists():
                        actual_app_dir = parent / "src"
                        print(f"[MathJax] 检测到打包模式，使用父目录 src: {actual_app_dir}")
            else:
                # 开发模式：使用当前脚本所在目录
                actual_app_dir = Path(__file__).parent
                print(f"[MathJax] 开发模式，使用 __file__: {actual_app_dir}")
        
        if not actual_app_dir:
            actual_app_dir = Path(APP_DIR) if APP_DIR else Path.cwd()
        
        # 第2步：检查 MathJax es5 目录
        es5_dir = actual_app_dir / "assets" / "MathJax-3.2.2" / "es5"
        tex_chtml = es5_dir / "tex-mml-chtml.js"
        
        print(f"[MathJax] APP_DIR={actual_app_dir}")
        print(f"[MathJax] es5_dir={es5_dir}")
        print(f"[MathJax] tex-mml-chtml.js exists={tex_chtml.exists()}")
        
        if not tex_chtml.exists():
            print(f"[WARN] MathJax 文件缺失: {tex_chtml}")
            # 尝试列出 assets 目录内容以帮助诊断
            assets_dir = actual_app_dir / "assets"
            if assets_dir.exists():
                print(f"[WARN] assets 目录内容: {list(assets_dir.iterdir())}")
        
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
        
        print(f"[MathJax] 原始路径: {es5_dir}")
        print(f"[MathJax] 标准化路径: {url_path}")
        print(f"[MathJax] 最终 URL: {url_str}")
        
        # 验证 URL 格式
        if not url_str.startswith("file:///"):
            print(f"[ERROR] URL 格式异常，应以 file:/// 开头: {url_str}")
        
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
        from matplotlib import mathtext
        import matplotlib.pyplot as plt
        from io import BytesIO
        import base64
        
        # 创建图形并渲染公式
        fig, ax = plt.subplots(figsize=(8, 1), dpi=150)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        # 使用 mathtext 渲染公式
        t = ax.text(0.5, 0.5, f'${latex}$', ha='center', va='center', 
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
        
        # 生成每个公式的 MathJax HTML
        formula_html = ""
        for i, latex in enumerate(formulas):
            label = labels[i] if i < len(labels) and labels[i] else ""
            label_html = f'<div class="formula-label">{label}</div>' if label else ""
            
            # 使用 MathJax 渲染（不要 HTML 转义，保留 LaTeX）
            formula_html += f'<div class="math-container">{label_html}<div class="formula-content">$${latex}$$</div></div>\n'
        
        if not formula_html:
            formula_html = '<div class="math-container" style="color:#888;">无公式</div>'
        
        # 使用 MathJax HTML 模板（使用相对路径）
        html = MATHJAX_HTML_TEMPLATE.replace("__FORMULAS__", formula_html)
        
        return html
    except Exception as e:
        print(f"[ERROR] build_math_html 出错: {e}")
        import traceback
        traceback.print_exc()
        # 返回错误提示 HTML
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: red; padding: 20px; font-family: sans-serif;">
<h3>公式渲染出错</h3>
<p><strong>错误信息:</strong> {str(e)}</p>
<p>请检查 MathJax 资源是否正确打包</p>
</body></html>'''

# WebEngine 延迟导入
QWebEngineView = None

def _log_webengine_diagnostics(stage: str, err: Exception | None = None) -> None:
    """输出 WebEngine 诊断信息，定位打包环境加载失败原因。"""
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

    # 关键环境变量
    log_info(f"[WebEngine] QTWEBENGINE_DISABLE_SANDBOX={os.environ.get('QTWEBENGINE_DISABLE_SANDBOX')}")
    log_info(f"[WebEngine] QTWEBENGINE_CHROMIUM_FLAGS={os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS')}")
    log_info(f"[WebEngine] QTWEBENGINEPROCESS_PATH={os.environ.get('QTWEBENGINEPROCESS_PATH')}")

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

from utils import resource_path
from qfluentwidgets import RoundMenu, Action

class CenterMenu(RoundMenu):
    def __init__(self, title: str = "", parent=None):
        super().__init__(title=title, parent=parent)

    def add_center_button(self, text: str, slot):
        from qfluentwidgets import PushButton, FluentIcon
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
        self.path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
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

from PyQt6.QtWidgets import QMainWindow as _QMainWindow
class FavoritesWindow(_QMainWindow):
    """收藏夹窗口 - 简化版，只保留列表功能"""
    def __init__(self, cfg: ConfigManager, parent=None):
        super().__init__(parent)
        self.cfg = cfg
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
        favorites_path = self.cfg.get("favorites_path")
        if not favorites_path:
            favorites_path = os.path.join(os.path.expanduser("~"), DEFAULT_FAVORITES_NAME)
            self.cfg.set("favorites_path", favorites_path)
        self.file_path = favorites_path
        self.load_favorites()

        # --- 新增: ESC 快捷关闭（备用方案，防止某些子控件截获按键） ---
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._esc_shortcut.activated.connect(self.close)

    # --- 新增: 捕获 ESC 按键 ---
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

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
            content_type = self._favorite_types.get(latex, "pix2tex")
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
        
        # 从 UserRole 获取原始公式（如果没有则使用文本）
        latex = item.data(Qt.ItemDataRole.UserRole)
        if not latex:
            # 兼容旧版本：直接使用文本
            latex = item.text()
        
        menu = QMenu(self)
        a_copy = menu.addAction("复制")
        
        # 导出子菜单 - 增加更多导出格式
        export_menu = menu.addMenu("导出为...")
        a_latex = export_menu.addAction("LaTeX (行内 $...$)")
        a_latex_display = export_menu.addAction("LaTeX (display \\[...\\])")
        a_latex_equation = export_menu.addAction("LaTeX (equation 编号)")
        a_html = export_menu.addAction("HTML")
        export_menu.addSeparator()
        a_md_inline = export_menu.addAction("Markdown (行内 $...$)")
        a_md_block = export_menu.addAction("Markdown (块级 $$...$$)")
        export_menu.addSeparator()
        a_mathml = export_menu.addAction("MathML")
        a_mathml_mml = export_menu.addAction("MathML (.mml)")
        a_mathml_m = export_menu.addAction("MathML (<m>)")
        a_mathml_attr = export_menu.addAction("MathML (attr)")
        export_menu.addSeparator()
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
        content_type = self._favorite_types.get(latex, "pix2tex")
        
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
        
        # 继承名称
        name = self._favorite_names.get(latex, "")
        if name and hasattr(p, '_formula_names'):
            p._formula_names[latex] = name
            if hasattr(p, 'save_history'):
                p.save_history()
        
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
                result = _mathml_htmlize(self._latex_to_mathml(clean))
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
        from backend.model import latex_to_svg
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
            import latex2mathml.converter
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
        except Exception as e:
            raise

    def _copy_item(self, latex: str):
        """复制公式到剪贴板"""
        import pyperclip
        if latex:
            pyperclip.copy(latex)
            self._set_status("已复制到剪贴板")

    def _rename_item(self, latex: str):
        """重命名收藏夹中的公式"""
        from qfluentwidgets import MessageBoxBase, SubtitleLabel, LineEdit

        class RenameDialog(MessageBoxBase):
            def __init__(self, current_name: str, parent=None):
                super().__init__(parent)
                self.titleLabel = SubtitleLabel("公式命名")
                self.nameEdit = LineEdit()
                self.nameEdit.setPlaceholderText("输入公式名称（留空则清除）")
                self.nameEdit.setText(current_name)
                self.nameEdit.setClearButtonEnabled(True)

                self.viewLayout.addWidget(self.titleLabel)
                self.viewLayout.addWidget(self.nameEdit)

                self.widget.setMinimumWidth(300)

            def value(self):
                return self.nameEdit.text().strip()

        # 使用收藏夹自己的名称字典
        current_name = self._favorite_names.get(latex, "")
        dlg = RenameDialog(current_name, self)
        if dlg.exec():
            new_name = dlg.value()
            if new_name:
                self._favorite_names[latex] = new_name
                self._set_status(f"已命名为: {new_name}")
            elif latex in self._favorite_names:
                del self._favorite_names[latex]
                self._set_status("已清除名称")

            # 保存收藏夹
            self.save_favorites()

            # 刷新列表显示
            self.refresh_list()

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
            "pix2tex": "公式",
            "pix2text": "公式",
            "pix2text_text": "文字",
            "pix2text_mixed": "混合",
            "pix2text_page": "整页",
            "pix2text_table": "表格",
        }

        for idx, formula in enumerate(self.favorites, start=1):
            # 创建带样式的列表项
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, formula)  # 存储原始公式

            # 获取名称和类型（优先使用收藏夹自己的）
            name = self._favorite_names.get(formula, "")
            content_type = self._favorite_types.get(formula, "pix2tex")
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

        # 设置列表样式
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background: transparent;
            }
            QListWidget::item {
                border-bottom: 1px solid #e0e0e0;
                padding: 8px 6px;
                color: #333;
                background: transparent;
            }
            QListWidget::item:hover {
                background: #e3f2fd;
            }
            QListWidget::item:selected {
                background: #42a5f5;
                color: white;
            }
        """)

    def select_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择收藏夹保存路径",
                                             os.path.dirname(self.file_path),
                                             "JSON Files (*.json)")
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
                        self._favorite_types = {str(k): str(v) for k, v in types.items()}
                elif isinstance(data, list):
                    # 兼容旧格式：纯列表
                    self.favorites = [str(x) for x in data]
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
            _exec_close_only_message_box(self, "提示", "收藏夹已经是空的")
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
            content_type: 内容类型 (pix2tex, pix2text, pix2text_mixed 等)
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
                content_type = "pix2tex"
        self._favorite_types[t] = content_type

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

class MainWindow(_QMainWindow):
    """主窗口 - 使用 QMainWindow 以正确支持 setCentralWidget"""
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LaTeX Snipper")
        self.resize(1000, 700)

        # 在模型初始化前
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        reqs = parse_requirements(req_path)
        self._force_exit = False
        # 状态字段
        self.model_status = "未加载"
        self.action_status = ""
        self._predict_busy = False
        self.overlay = None
        self.predict_thread = None
        self.predict_worker = None
        self.pdf_predict_thread = None
        self.pdf_predict_worker = None
        self.pdf_progress = None
        self._pdf_output_format = None
        self._pdf_doc_style = None
        self._pdf_dpi = None
        self.settings_window = None
        self._pix2tex_warmup_notified = False

        # 配置与模型
        self.cfg = ConfigManager()
        self.current_model = self.cfg.get("default_model", "pix2tex")
        self.desired_model = self.cfg.get("desired_model", self.current_model)
        try:
            if self.desired_model in ("pix2text", "unimernet"):
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

        # 尝试初始化模型
        try:
            self.model = ModelWrapper(self.current_model)
            self.model.status_signal.connect(self.show_status_message)
            print("[DEBUG] ModelWrapper 初始化完成")

            # 根据当前模式和对应模型的实际状态设置状态文本
            if self.model.is_model_ready(self.current_model):
                self.model_status = f"已加载 ({self.current_model})"
            elif self.current_model == "pix2tex" and self.model.get_error():
                self.model_status = f"加载失败"
            elif self.current_model.startswith("pix2text") and self.model._pix2text_import_failed:
                self.model_status = f"加载失败 ({self.current_model})"
            elif self.current_model == "unimernet" and getattr(self.model, "_unimernet_import_failed", False):
                self.model_status = f"加载失败 ({self.current_model})"
            else:
                self.model_status = f"未就绪 ({self.current_model})"

        except Exception as e:
            app = QApplication.instance() or QApplication([])
            from qfluentwidgets import setFont, Theme, setTheme
            from PyQt6.QtWidgets import QMessageBox as QMsgBox
            apply_theme("AUTO")
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
                msg.exec()
                try:
                    ok = ensure_deps(always_show_ui=True, require_layers=("BASIC", "CORE"))
                    if not ok:
                        sys.exit(1)
                except Exception as ee:
                    print(f"[FATAL] ensure_deps 异常: {ee}")
                    show_dependency_wizard(always_show_ui=True)
                    return

        try:
            if self.model:
                QTimer.singleShot(0, self._warmup_desired_model)
        except Exception:
            pass

        # 历史文件
        print("[DEBUG] 开始初始化历史记录")
        self.history_path = os.path.join(os.path.expanduser("~"), DEFAULT_HISTORY_NAME)
        self.history = []

        # 状态栏（注意不要与方法同名）
        print("[DEBUG] 开始初始化状态栏")
        self.status_label = QLabel()

        # 收藏窗口（需在 status_label 之后创建，便于回调写入状态）
        print("[DEBUG] 开始初始化收藏窗口")
        self.favorites_window = FavoritesWindow(self.cfg, self)
        print("[DEBUG] 收藏窗口初始化完成")

        if DISABLE_GLOBAL_HOTKEY:
            self.hotkey = None
            self._fallback_shortcut = QShortcut("Ctrl+F", self)
            self._fallback_shortcut.activated.connect(self.start_capture)
        else:
            self.hotkey = QHotkey(parent=self)
            seq = self.cfg.get("hotkey", "Ctrl+F")
            if not (seq.startswith("Ctrl+") and len(seq) == 6):
                seq = "Ctrl+F"
            self._fallback_shortcut = None
            self.hotkey.activated.connect(self.on_hotkey_triggered)
            QTimer.singleShot(0, lambda: self.register_hotkey(seq))

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

        # 历史记录标题 - 使用更现代的样式
        history_title = QLabel("历史记录")
        history_title.setStyleSheet("font-size: 14px; font-weight: 500; color: #1976d2; padding: 4px 0;")
        left_layout.addWidget(history_title)

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
        editor_title = QLabel("LaTeX 编辑器")
        editor_title.setStyleSheet("font-size: 14px; font-weight: 500; color: #1976d2; padding: 4px 0;")
        editor_header.addWidget(editor_title)
        editor_header.addStretch()
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
        self.add_to_fav_btn = PushButton(FluentIcon.HEART, "收藏")
        self.add_to_fav_btn.clicked.connect(self._add_editor_to_fav)
        editor_header.addWidget(self.upload_image_btn)
        editor_header.addWidget(self.upload_pdf_btn)
        editor_header.addWidget(self.copy_editor_btn)
        editor_header.addWidget(self.export_btn)
        editor_header.addWidget(self.add_to_fav_btn)
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
        preview_title = QLabel("实时渲染预览")
        preview_title.setStyleSheet("font-size: 14px; font-weight: 500; color: #1976d2; padding: 4px 0;")
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        self.clear_preview_btn = PushButton(FluentIcon.BROOM, "清空预览")
        self.clear_preview_btn.clicked.connect(self._clear_preview)
        preview_header.addWidget(self.clear_preview_btn)
        right_layout.addLayout(preview_header)

        # 初始化 WebEngine 渲染视图
        self.preview_view = None
        self._render_timer = None
        self._pending_latex = ""
        self._rendered_formulas = []  # 存储已渲染的公式列表: [(formula, label), ...]
        self._formula_names = {}  # 存储公式名称映射: {formula: name}
        self._formula_types = {}  # 存储公式内容类型: {formula: content_type}
        if ensure_webengine_loaded():
            self.preview_view = QWebEngineView()
            
            # 禁用 WebEngine 沙箱，允许本地文件中的脚本执行
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
                pg.loadStarted.connect(lambda: print("[WebEngine] loadStarted"))
                pg.loadProgress.connect(lambda p: print(f"[WebEngine] loadProgress={p}"))
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
            fallback_label = QLabel("WebEngine 未加载，无法渲染公式预览。\n请确保已安装 PyQtWebEngine。")
            fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback_label.setStyleSheet("color: #888; padding: 20px;")
            right_layout.addWidget(fallback_label, 1)

        # ========== 主布局：左右分栏 ==========
        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 600])  # 初始宽度比例
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # 设置中心 widget
        self.setCentralWidget(container)

        # 托盘
        self.tray_icon = QSystemTrayIcon(self.icon, self)
        tray_menu = QMenu()
        tray_menu.addAction("打开主窗口", self.show_window)
        tray_menu.addAction("截图识别", self.start_capture)
        tray_menu.addAction("退出", self.truly_exit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.update_tray_tooltip()
        # 初始化界面
        self.load_history()
        self.update_history_ui()
        self.refresh_status_label()

        # 刷新收藏夹列表（确保在 _formula_names 加载后刷新，以显示公式名称）
        if hasattr(self, 'favorites_window') and self.favorites_window:
            self.favorites_window.refresh_list()

        self.update_tray_menu()

        self._apply_primary_buttons()
        QApplication.instance().aboutToQuit.connect(self._graceful_shutdown)

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
                b.setStyleSheet(ACTION_BTN_STYLE)
            except Exception:
                pass

    def _show_history_context_menu(self, row: QWidget, global_pos):
        if not self._row_is_alive(row):
            return
        latex = self._safe_row_text(row)
        m = CenterMenu(parent=self)
        m.addAction(Action("编辑", triggered=lambda: self._edit_history_row(row)))
        m.addAction(Action("重命名", triggered=lambda: self._rename_history_row(row)))
        m.addAction(Action("复制", triggered=lambda: self._do_copy_row(row)))

        # 导出子菜单 - 增加更多导出格式
        export_menu = CenterMenu("导出为...", parent=m)
        export_menu.addAction(Action("LaTeX (行内 $...$)", triggered=lambda: self._export_as("latex", latex)))
        export_menu.addAction(Action("LaTeX (display \\[...\\])", triggered=lambda: self._export_as("latex_display", latex)))
        export_menu.addAction(Action("LaTeX (equation 编号)", triggered=lambda: self._export_as("latex_equation", latex)))
        export_menu.addAction(Action("HTML", triggered=lambda: self._export_as("html", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("Markdown (行内 $...$)", triggered=lambda: self._export_as("markdown_inline", latex)))
        export_menu.addAction(Action("Markdown (块级 $$...$$)", triggered=lambda: self._export_as("markdown_block", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("MathML", triggered=lambda: self._export_as("mathml", latex)))
        export_menu.addAction(Action("MathML (.mml)", triggered=lambda: self._export_as("mathml_mml", latex)))
        export_menu.addAction(Action("MathML (<m>)", triggered=lambda: self._export_as("mathml_m", latex)))
        export_menu.addAction(Action("MathML (attr)", triggered=lambda: self._export_as("mathml_attr", latex)))
        export_menu.addSeparator()
        export_menu.addAction(Action("Word OMML", triggered=lambda: self._export_as("omml", latex)))
        export_menu.addAction(Action("SVG Code", triggered=lambda: self._export_as("svgcode", latex)))
        m.addMenu(export_menu)

        m.addAction(Action("收藏", triggered=lambda: self._do_fav_row(row)))
        m.addAction(Action("删除", triggered=lambda: self._do_delete_row(row)))
        m.exec(global_pos)

    def _rename_history_row(self, row: QWidget):
        """重命名公式"""
        from PyQt6.QtWidgets import QInputDialog
        latex = self._safe_row_text(row)
        if not latex:
            return
        current_name = self._formula_names.get(latex, "")
        new_name, ok = QInputDialog.getText(
            self, "重命名公式",
            "输入公式名称（留空则清除名称）:",
            text=current_name
        )
        if not ok:
            return
        new_name = new_name.strip()
        if new_name:
            self._formula_names[latex] = new_name
        elif latex in self._formula_names:
            del self._formula_names[latex]

        # 同步更新渲染列表中的标签
        idx = getattr(row, '_index', 0)
        if new_name:
            new_label = f"#{idx} {new_name}" if idx > 0 else new_name
        elif idx > 0:
            new_label = f"#{idx}"
        else:
            new_label = ""
        # 更新 _rendered_formulas 中的标签
        for i, (formula, label) in enumerate(self._rendered_formulas):
            if formula == latex:
                self._rendered_formulas[i] = (formula, new_label)

        # 刷新 UI
        self.rebuild_history_ui()
        self._refresh_preview()
        self.set_action_status(f"已命名: {new_name}" if new_name else "已清除名称")

    # --- 新增方法：托盘提示更新 ---
    def update_tray_tooltip(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        if getattr(self, "tray_icon", None):
            self.tray_icon.setToolTip(f"LaTeXSnipper - 截图识别快捷键: {hk}")

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
    def refresh_status_label(self):
        base = f"当前模型: {self.current_model} | 状态: {self.model_status}"
        if getattr(self, "current_model", "") == "unimernet":
            try:
                base += f" | 权重: {self._get_unimernet_weight_label()}"
            except Exception:
                pass
        if self.action_status:
            base += f" | {self.action_status}"
        self.status_label.setText(base)

    def _history_row_index(self, row: QWidget):
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
        lbl = row.findChild(QLabel)
        if lbl:
            lbl.setText(new_latex)
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

    def set_action_status(self, msg: str, auto_clear_ms: int = 2500):
        InfoBar.success(
            title="提示",
            content=msg,
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=auto_clear_ms
        )

    def show_status_message(self, msg: str):
        # 模型后台线程回调
        self.set_model_status(msg)

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
            content_type = getattr(self, "current_model", "pix2tex")
        self.favorites_window.add_favorite(text, content_type=content_type)

    def _show_export_menu(self):
        """显示导出格式菜单"""
        text = self.latex_editor.toPlainText().strip()
        if not text:
            self.set_action_status("编辑器为空")
            return

        menu = CenterMenu(parent=self)
        menu.addAction(Action("LaTeX (行内 $...$)", triggered=lambda: self._export_as("latex", text)))
        menu.addAction(Action("LaTeX (display \\[...\\])", triggered=lambda: self._export_as("latex_display", text)))
        menu.addAction(Action("LaTeX (equation 编号)", triggered=lambda: self._export_as("latex_equation", text)))
        menu.addAction(Action("HTML", triggered=lambda: self._export_as("html", text)))
        menu.addSeparator()
        menu.addAction(Action("Markdown (行内 $...$)", triggered=lambda: self._export_as("markdown_inline", text)))
        menu.addAction(Action("Markdown (块级 $$...$$)", triggered=lambda: self._export_as("markdown_block", text)))
        menu.addSeparator()
        menu.addAction(Action("MathML", triggered=lambda: self._export_as("mathml", text)))
        menu.addAction(Action("MathML (.mml)", triggered=lambda: self._export_as("mathml_mml", text)))
        menu.addAction(Action("MathML (<m>)", triggered=lambda: self._export_as("mathml_m", text)))
        menu.addAction(Action("MathML (attr)", triggered=lambda: self._export_as("mathml_attr", text)))
        menu.addSeparator()
        menu.addAction(Action("Word OMML", triggered=lambda: self._export_as("omml", text)))
        menu.addAction(Action("SVG Code", triggered=lambda: self._export_as("svgcode", text)))

        # 在导出按钮位置显示菜单
        btn_pos = self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft())
        menu.exec(btn_pos)

    def _export_as(self, format_type: str, latex: str):
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
                result = _mathml_htmlize(self._latex_to_mathml(clean))
            except Exception as e:
                self.set_action_status(f"HTML 导出失败: {e}")
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
                self.set_action_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML"

        elif format_type == "mathml_mml":
            # MathML 带 .mml 扩展名格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "mml")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (.mml)"

        elif format_type == "mathml_m":
            # MathML 数学元素格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "m")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (<m>)"

        elif format_type == "mathml_attr":
            # MathML 属性格式
            try:
                result = _mathml_with_prefix(self._latex_to_mathml(clean), "attr")
            except Exception as e:
                self.set_action_status(f"MathML 导出失败: {e}")
                return
            format_name = "MathML (attr)"

        elif format_type == "omml":
            try:
                result = self._latex_to_omml(clean)
            except Exception as e:
                self.set_action_status(f"OMML 导出失败: {e}")
                return
            format_name = "Word OMML"

        elif format_type == "svgcode":
            # SVG 代码格式
            try:
                result = self._latex_to_svg_code(clean)
            except Exception as e:
                self.set_action_status(f"SVG 导出失败: {e}")
                return
            format_name = "SVG Code"

        if result:
            try:
                QApplication.clipboard().setText(result)
                self.set_action_status(f"已复制 {format_name} 格式")
            except Exception:
                try:
                    import pyperclip
                    pyperclip.copy(result)
                    self.set_action_status(f"已复制 {format_name} 格式")
                except Exception:
                    self.set_action_status("复制失败")

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
        except Exception as e:
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
            self._formula_types[latex] = getattr(self, "current_model", "pix2tex")
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
            current_mode = getattr(self, "current_model", "pix2tex")
            all_items.append((editor_text, "编辑中", current_mode))
        
        # 已渲染的公式列表 - 使用各自存储的类型
        for formula, label in self._rendered_formulas:
            content_type = self._formula_types.get(formula, "pix2tex")  # 默认公式模式
            all_items.append((formula, label, content_type))
        
        try:
            # 构建智能渲染的 HTML
            html = self._build_smart_preview_html(all_items)
            base_url = _get_mathjax_base_url()
            self.preview_view.setHtml(html, base_url)
        except Exception as e:
            # 在 WebEngine 中显示错误信息
            try:
                error_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: #d32f2f; padding: 20px; font-family: sans-serif;">
<h3>⚠️ 公式渲染失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: #fff3e0; padding: 10px; border-radius: 4px; overflow-x: auto;">{str(e)}</pre>
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
            import html as html_module
            
            if not items:
                return build_math_html("")
            
            # 构建各个内容块
            content_blocks = []
            has_math = False  # 是否需要加载 MathJax
            
            for content, label, content_type in items:
                block_html = self._render_content_block(content, label, content_type)
                content_blocks.append(block_html)
                # 检查是否需要 MathJax
                if content_type in ("pix2tex", "pix2text", "pix2text_mixed"):
                    has_math = True
            
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
}}
.content-block {{
    margin-bottom: 16px;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 8px;
    border-left: 4px solid #1976d2;
}}
.content-block.text-type {{
    border-left-color: #43a047;
}}
.content-block.table-type {{
    border-left-color: #f57c00;
}}
.content-block.mixed-type {{
    border-left-color: #7b1fa2;
}}
.block-label {{
    font-size: 12px;
    color: #666;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.type-badge {{
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    background: #e3f2fd;
    color: #1976d2;
}}
.type-badge.text {{ background: #e8f5e9; color: #43a047; }}
.type-badge.table {{ background: #fff3e0; color: #f57c00; }}
.type-badge.mixed {{ background: #f3e5f5; color: #7b1fa2; }}
.block-content {{
    font-size: 14px;
    text-align: center;
}}
.formula-content {{
    text-align: center;
    padding: 0.5em 0.5em 0.2em 0.5em;
    margin: 0.2em 0 0.2em 0;
    display: inline-block;
    max-width: 100%;
    box-sizing: border-box;
}}
.formula-content img,
.formula-content svg {{
    max-width: 100%;
    height: auto;
    vertical-align: middle;
    font-size: 20em;
    /* 让SVG公式更大更清晰 */
    margin: 0.1em 0;
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
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}}
th {{
    background-color: #f2f2f2;
}}
.MathJax {{ font-size: 1.2em; }}
</style>
</head>
<body>{body_content}</body>
</html>'''
        except Exception as e:
            # 返回错误提示 HTML
            return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="color: #d32f2f; padding: 20px; font-family: sans-serif;">
<h3>⚠️ HTML 构建失败</h3>
<p><strong>错误:</strong></p>
<pre style="background: #fff3e0; padding: 10px; border-radius: 4px; overflow-x: auto;">{str(e)}</pre>
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
                content_type = "pix2tex"
            else:
                content_type = str(content_type)
            
            print(f"[RenderBlock] 处理内容块: type={content_type}, label_len={len(label)}, content_len={len(content)}")
            
            # 类型显示名称和样式
            type_info = {
                "pix2tex": ("公式", ""),
                "pix2text": ("公式", ""),
                "unimernet": ("公式", ""),
                "pix2text_text": ("文字", "text"),
                "pix2text_mixed": ("混合", "mixed"),
                "pix2text_page": ("整页", "text"),
                "pix2text_table": ("表格", "table"),
            }
            
            type_name, type_class = type_info.get(content_type, ("内容", ""))
            block_class = f"content-block {type_class}-type" if type_class else "content-block"
            badge_class = f"type-badge {type_class}" if type_class else "type-badge"
            
            # 根据类型渲染内容
            if content_type in ("pix2tex", "pix2text", "unimernet"):
                # 公式模式：根据当前选择的渲染引擎来渲染
                try:
                    from backend.latex_renderer import _latex_settings
                    if _latex_settings:
                        mode = _latex_settings.get_render_mode()
                        # 如果选择了 LaTeX 渲染，使用 LaTeX 渲染
                        if mode and mode.startswith("latex_"):
                            from backend.latex_renderer import get_latex_renderer
                            renderer = get_latex_renderer()
                            if renderer and renderer.is_available():
                                try:
                                    svg = renderer.render_to_svg(content)
                                    if svg:
                                        rendered_content = f'<div class="formula-content">{svg}</div>'
                                    else:
                                        # LaTeX 渲染失败，fallback 到 MathJax
                                        rendered_content = f'<div class="formula-content">$${content}$$</div>'
                                except Exception:
                                    # LaTeX 渲染异常，fallback 到 MathJax
                                    rendered_content = f'<div class="formula-content">$${content}$$</div>'
                            else:
                                # LaTeX 不可用，使用 MathJax
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
            elif content_type == "pix2text_mixed":
                # 混合模式：文字和公式混合，由 MathJax 处理
                rendered_content = self._render_mixed_content(content)
            elif content_type == "pix2text_table":
                # 表格模式
                rendered_content = self._render_table_content(content)
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
            print(f"[RenderBlock] 渲染成功，输出长度: {len(result)}")
            return result
        except Exception as e:
            print(f"[RenderBlock] 处理内容块失败: {e}")
            import traceback
            traceback.print_exc()
            # 返回错误提示
            error_msg = f"内容块渲染失败: {str(e)}"
            return f'<div style="color: red; padding: 10px; background: #ffebee; border-radius: 4px;">{html_module.escape(error_msg)}</div>'
    
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
                # 继承或补充类型（避免默认成 pix2tex）
                if hasattr(self, "_formula_types"):
                    if formula not in self._formula_types:
                        self._formula_types[formula] = getattr(self, "current_model", "pix2tex")
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

    def rebuild_history_ui(self):
        for i in reversed(range(self.history_layout.count() - 1)):
            item = self.history_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                self.history_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
        for idx, t in enumerate(self.history):
            self.history_layout.insertWidget(self.history_layout.count() - 1, self.create_history_row(t, idx + 1))
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
            content_type = getattr(self, "current_model", "pix2tex")
        self.favorites_window.add_favorite(txt, content_type=content_type)

    def _do_delete_row(self, row):
        txt = self._safe_row_text(row)
        if not txt:
            self.set_action_status("已删除（空）")
            return
        # 不标记 _deleted，直接调用
        self.delete_history_item(row, txt)

    def create_history_row(self, t: str, index: int = 0):
        row = QWidget(self.history_container)
        row._latex_text = t
        row._index = index
        row._deleted = False
        hl = QHBoxLayout(row)
        hl.setContentsMargins(6, 4, 6, 4)
        
        # 编号标签
        if index > 0:
            num_lbl = QLabel(f"#{index}")
            num_lbl.setFixedWidth(35)
            num_lbl.setStyleSheet("color: #1976d2; font-weight: bold; font-size: 11px;")
            hl.addWidget(num_lbl)
        
        # 公式名称（如果有）
        formula_name = self._formula_names.get(t, "")
        if formula_name:
            name_lbl = QLabel(f"[{formula_name}]")
            name_lbl.setStyleSheet("color: #f57c00; font-size: 10px; margin-right: 4px;")
            hl.addWidget(name_lbl)
            row._name_label = name_lbl
        else:
            row._name_label = None
        
        lbl = QLabel(t)
        lbl.setWordWrap(True)
        lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        lbl.setToolTip("点击加载到编辑器并渲染")
        # 优化字体显示
        from PyQt6.QtGui import QFont
        label_font = QFont("Consolas", 9)
        label_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        lbl.setFont(label_font)
        lbl.setStyleSheet("color: #333; padding: 2px;")
        hl.addWidget(lbl, 1)

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
            row_ref2 = weakref.ref(row)

            def _wrapped():
                r = row_ref2()
                if not self._row_is_alive(r):
                    return
                handler(r)

            b.clicked.connect(_wrapped)
            hl.addWidget(b)
            return b

        add_btn("复制", "复制到剪贴板", self._do_copy_row, FluentIcon.COPY)
        add_btn("收藏", "加入收藏夹", self._do_fav_row, FluentIcon.HEART)
        add_btn("删除", "删除该条记录", self._do_delete_row, FluentIcon.DELETE)
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
            content_type = getattr(self, "current_model", "pix2tex")
        self._formula_types[t] = content_type
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
                # 新格式：包含历史记录和公式名称
                history_list = data.get("history", [])
                self.history = [str(x) for x in history_list if isinstance(x, (str, int, float))]
                # 加载公式名称
                formula_names = data.get("formula_names", {})
                if isinstance(formula_names, dict):
                    self._formula_names = {str(k): str(v) for k, v in formula_names.items()}
                # 加载公式类型
                formula_types = data.get("formula_types", {})
                if isinstance(formula_types, dict):
                    self._formula_types = {str(k): str(v) for k, v in formula_types.items()}
            elif isinstance(data, list):
                # 兼容旧格式：纯列表
                self.history = [str(x) for x in data if isinstance(x, (str, int, float))]
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
        if self.history:
            # 有历史
            self.clear_history_button.setText("清空历史记录")
            self.clear_history_button.setToolTip("清空所有历史记录")
        else:
            # 无历史但仍可点，点击会弹出提示（逻辑已在 clear_history 内）
            self.clear_history_button.setText("清空历史记录（无记录）")
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

    def _get_preferred_model_for_predict(self) -> str:
        desired = (self.cfg.get("desired_model", "") or "").lower()
        if desired == "pix2text":
            mode = (self.cfg.get("pix2text_mode", "formula") or "formula").lower()
            mode_map = {
                "formula": "pix2text",
                "mixed": "pix2text_mixed",
                "text": "pix2text_text",
                "page": "pix2text_page",
                "table": "pix2text_table",
            }
            return mode_map.get(mode, "pix2text")
        if desired == "unimernet":
            return "unimernet"
        return "pix2tex"

    def _warmup_desired_model(self):
        if not self.model:
            return
        preferred = self._get_preferred_model_for_predict()
        if not preferred:
            return
        # If already ready, just sync status/UI.
        try:
            if self.model.is_model_ready(preferred):
                self.current_model = preferred
                self.cfg.set("default_model", preferred)
                if preferred.startswith("pix2text"):
                    self.desired_model = "pix2text"
                elif preferred == "unimernet":
                    self.desired_model = "unimernet"
                else:
                    self.desired_model = "pix2tex"
                self.cfg.set("desired_model", self.desired_model)
                self.set_model_status(f"已加载 ({preferred})")
                if self.settings_window:
                    self.settings_window.update_model_selection()
                return
        except Exception:
            pass

        def worker():
            ok = False
            try:
                if preferred.startswith("pix2text"):
                    self._apply_pix2text_env()
                    ok = self.model._lazy_load_pix2text()
                elif preferred == "unimernet":
                    self._apply_unimernet_env()
                    ok = self.model._lazy_load_unimernet()
                    try:
                        self.model._ensure_unimernet_worker()
                    except Exception:
                        pass
                else:
                    if self.model._is_frozen:
                        ok = self.model._ensure_pix2tex_worker()
                    else:
                        self.model._ensure_pix2tex()
                        ok = True
            except Exception:
                ok = False

            if ok:
                def apply():
                    from qfluentwidgets import InfoBar, InfoBarPosition
                    self.current_model = preferred
                    self.cfg.set("default_model", preferred)
                    if preferred.startswith("pix2text"):
                        self.desired_model = "pix2text"
                    elif preferred == "unimernet":
                        self.desired_model = "unimernet"
                    else:
                        self.desired_model = "pix2tex"
                    self.cfg.set("desired_model", self.desired_model)
                    self.set_model_status(f"已加载 ({preferred})")
                    if self.settings_window:
                        self.settings_window.update_model_selection()
                    if preferred == "pix2tex" and not self._pix2tex_warmup_notified:
                        self._pix2tex_warmup_notified = True
                        InfoBar.success(
                            title="模型预热完成",
                            content="pix2tex 预热完成，可直接识别",
                            parent=self._get_infobar_parent(),
                            duration=3000,
                            position=InfoBarPosition.TOP
                        )
                QTimer.singleShot(0, apply)

        import threading
        threading.Thread(target=worker, daemon=True).start()
    def on_model_changed(self, model_name: str):
        from qfluentwidgets import InfoBar, InfoBarPosition
        info_parent = self._get_infobar_parent()
        m = model_name.lower()
        requested = m
        if requested.startswith("pix2text"):
            desired_model = "pix2text"
        elif requested == "unimernet":
            desired_model = "unimernet"
        else:
            desired_model = "pix2tex"
        
        # 支持的模式列表
        valid_modes = ("pix2tex", "pix2text", "pix2text_text", "pix2text_mixed",
                       "pix2text_page", "pix2text_table", "unimernet")
        
        if m not in valid_modes:
            self.set_action_status("未知模型，使用 pix2tex")
            m = "pix2tex"
        
        # 首先检查模型是否有加载错误
        model_has_error = self.model and self.model.get_error()
        
        # UniMERNet 模式
        if m == "unimernet":
            unimernet_unavailable = False
            unimernet_error_msg = ""
            if not self._is_unimernet_model_available():
                unimernet_unavailable = True
                unimernet_error_msg = "UniMERNet 权重未下载或目录不完整。"
            self._apply_unimernet_env()
            try:
                if self.model:
                    self.model._unimernet_import_failed = False
                if not unimernet_unavailable:
                    result = self.model._lazy_load_unimernet() if self.model else None
                    if not result:
                        unimernet_unavailable = True
                        unimernet_error_msg = "UniMERNet 未安装或无法加载。"
            except Exception as e:
                unimernet_unavailable = True
                unimernet_error_msg = f"UniMERNet 加载出错: {e}"

            if unimernet_unavailable:
                InfoBar.warning(
                    title="模型未就绪",
                    content=f"{unimernet_error_msg} 可在设置中点击“下载模型”安装。",
                    parent=info_parent,
                    duration=6000,
                    position=InfoBarPosition.TOP
                )
                m = "pix2tex"
            else:
                InfoBar.success(
                    title="模式切换成功",
                    content="已切换到 UniMERNet 公式识别",
                    parent=info_parent,
                    duration=3000,
                    position=InfoBarPosition.TOP
                )

        # pix2text 系列模式
        elif m.startswith("pix2text"):
            # 用户选择 pix2text 系列，检查是否可用
            pix2text_unavailable = False
            pix2text_error_msg = ""
            self._apply_pix2text_env()
            
            # 重置失败标志并重新尝试
            if self.model:
                self.model._pix2text_import_failed = False
            
            try:
                result = self.model._lazy_load_pix2text() if self.model else None
                if not result:
                    pix2text_unavailable = True
                    pix2text_error_msg = "pix2text 模型未部署或加载失败。"
            except Exception as e:
                pix2text_unavailable = True
                pix2text_error_msg = f"pix2text 加载出错: {e}"
            
            if pix2text_unavailable:
                InfoBar.warning(
                    title="模型切换失败",
                    content=f"{pix2text_error_msg} 已回退到 pix2tex",
                    parent=info_parent,
                    duration=5000,
                    position=InfoBarPosition.TOP
                )
                m = "pix2tex"
            else:
                # 模式名称映射
                mode_names = {
                    "pix2text": "pix2text 公式识别",
                    "pix2text_text": "pix2text 纯文字识别",
                    "pix2text_mixed": "pix2text 混合识别",
                    "pix2text_page": "pix2text 整页识别",
                    "pix2text_table": "pix2text 表格识别",
                }
                mode_display = mode_names.get(m, m)
                InfoBar.success(
                    title="模式切换成功",
                    content=f"已切换到 {mode_display}",
                    parent=info_parent,
                    duration=3000,
                    position=InfoBarPosition.TOP
                )
        else:
            # 切换到 pix2tex
            if model_has_error:
                error_msg = self.model.get_error() if self.model else "未知错误"
                short_error = error_msg[:50] + "..." if len(error_msg) > 50 else error_msg
                InfoBar.error(
                    title="模型加载失败",
                    content=f"pix2tex 不可用: {short_error}\n请在【设置】→【依赖管理向导】中修复",
                    parent=info_parent,
                    duration=8000,
                    position=InfoBarPosition.TOP
                )
            elif self.model and self.model.is_ready():
                InfoBar.success(
                    title="模式切换成功",
                    content="已切换到 pix2tex 公式识别",
                    parent=info_parent,
                    duration=3000,
                    position=InfoBarPosition.TOP
                )
            else:
                InfoBar.warning(
                    title="模型未就绪",
                    content="pix2tex 模型尚未加载完成",
                    parent=info_parent,
                    duration=5000,
                    position=InfoBarPosition.TOP
                )
        
        self.current_model = m
        self.cfg.set("default_model", m)
        self.desired_model = desired_model
        self.cfg.set("desired_model", desired_model)
        if m.startswith("pix2text"):
            mode_map = {
                "pix2text": "formula",
                "pix2text_mixed": "mixed",
                "pix2text_text": "text",
                "pix2text_page": "page",
                "pix2text_table": "table",
            }
            self.cfg.set("pix2text_mode", mode_map.get(m, "formula"))
        
        # 根据模型实际状态设置状态文本
        if self.model:
            # 使用 is_model_ready 方法检查对应模型的状态
            if self.model.is_model_ready(m):
                self.set_model_status(f"已加载 ({m})")
            elif m == "pix2tex" and self.model.get_error():
                self.set_model_status(f"加载失败")
            elif m.startswith("pix2text") and self.model._pix2text_import_failed:
                self.set_model_status(f"加载失败 ({m})")
            elif m == "unimernet" and getattr(self.model, "_unimernet_import_failed", False):
                self.set_model_status(f"加载失败 ({m})")
            else:
                self.set_model_status(f"未就绪 ({m})")
        else:
            self.set_model_status(f"未就绪 ({m})")
            
        # 更新设置窗口选择状态
        if self.settings_window:
            self.settings_window.update_model_selection()

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

    def _start_predict_with_pil(self, img: Image.Image):
        if self._predict_busy:
            from qfluentwidgets import MessageBox
            msg = MessageBox("提示", "正在识别，请稍候", self)
            msg.cancelButton.hide()
            msg.exec()
            return
        if not self.model:
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        if self.predict_thread and self.predict_thread.isRunning():
            custom_warning_dialog("错误", "前一识别线程尚未结束", self)
            return
        preferred = self._get_preferred_model_for_predict()
        try:
            if preferred != self.current_model or (self.model and not self.model.is_model_ready(preferred)):
                self.on_model_changed(preferred)
        except Exception:
            if preferred != self.current_model:
                self.on_model_changed(preferred)
        active_model = self.current_model
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

    def _open_terminal_from_settings(self, env_key: str | None = None):
        try:
            if not self.settings_window:
                self.settings_window = SettingsWindow(self)
            self.settings_window._open_terminal(env_key=env_key)
        except Exception as e:
            custom_warning_dialog("错误", f"打开终端失败: {e}", self)

    def _get_unimernet_variant(self) -> str:
        v = (self.cfg.get("unimernet_variant", "base") or "base").lower()
        return v if v in ("base", "small", "tiny") else "base"

    def _get_unimernet_model_dir(self) -> Path:
        p = MODEL_DIR / f"unimernet_{self._get_unimernet_variant()}"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    def _is_unimernet_model_available(self, variant: str | None = None) -> bool:
        try:
            v = (variant or self._get_unimernet_variant()).lower()
            p = MODEL_DIR / f"unimernet_{v}"
            if not p.exists() or not p.is_dir():
                return False
            weight_candidates = [
                p / "pytorch_model.pth",
                p / f"unimernet_{v}.pth",
                p / "pytorch_model.bin",
                p / "model.safetensors",
            ]
            if any(x.exists() for x in weight_candidates):
                return True
            # fallback: any .pth in dir
            return any(p.glob("*.pth"))
        except Exception:
            return False

    def _get_unimernet_weight_label(self) -> str:
        variant = self._get_unimernet_variant()
        label_map = {"base": "Base", "small": "Small", "tiny": "Tiny"}
        display_variant = label_map.get(variant, variant)
        model_dir = MODEL_DIR / f"unimernet_{variant}"
        candidates = [
            model_dir / f"unimernet_{variant}.pth",
            model_dir / "pytorch_model.pth",
            model_dir / "model.safetensors",
            model_dir / "pytorch_model.bin",
        ]
        found = next((p for p in candidates if p.exists()), None)
        if not found and model_dir.exists():
            for pattern in ("*.pth", "*.safetensors", "*.bin"):
                for p in model_dir.glob(pattern):
                    found = p
                    break
                if found:
                    break
        if found:
            return f"{display_variant} ({found.name})"
        return f"{display_variant} (未检测到权重)"

    def _apply_pix2text_env(self):
        try:
            pyexe = self.cfg.get("pix2text_pyexe", "")
            if pyexe and os.path.exists(pyexe):
                os.environ["PIX2TEXT_PYEXE"] = pyexe
            else:
                os.environ.pop("PIX2TEXT_PYEXE", None)
        except Exception:
            pass

    def _apply_unimernet_env(self):
        try:
            os.environ["UNIMERNET_MODEL_PATH"] = str(self._get_unimernet_model_dir())
        except Exception:
            pass
        try:
            pyexe = self.cfg.get("unimernet_pyexe", "")
            if pyexe and os.path.exists(pyexe):
                os.environ["UNIMERNET_PYEXE"] = pyexe
            else:
                os.environ.pop("UNIMERNET_PYEXE", None)
        except Exception:
            pass

    def _open_pix2text_download_page(self):
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(cache_dir)))
        except Exception:
            pass
        try:
            pyperclip.copy(str(cache_dir))
        except Exception:
            pass
        try:
            InfoBar.info(
                title="已打开",
                content=f"已打开缓存目录并复制路径: {cache_dir}",
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP
            )
        except Exception:
            pass

    def _open_unimernet_download_page(self):
        variant = self._get_unimernet_variant()
        model_dir = self._get_unimernet_model_dir()
        url = f"https://huggingface.co/wanderkid/unimernet_{variant}"
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(model_dir)))
        except Exception:
            pass
        try:
            pyperclip.copy(str(model_dir))
        except Exception:
            pass
        try:
            InfoBar.info(
                title="已打开下载页",
                content=f"已打开模型目录并复制路径: {model_dir}",
                parent=self,
                duration=3000,
                position=InfoBarPosition.TOP
            )
        except Exception:
            pass


    def _show_pix2text_setup_tip(self):
        from qfluentwidgets import MessageBox
        pyexe = self.cfg.get("pix2text_pyexe", "")
        pip_prefix = f"\"{pyexe}\" -m pip" if (pyexe and os.path.exists(pyexe)) else "python -m pip"
        install_cmd = "\n".join([
            f"{pip_prefix} install -U pix2text==1.1.4",
            f"{pip_prefix} -c \"from pix2text import Pix2Text; Pix2Text()\"",
        ])
        env_note = ""
        if not (pyexe and os.path.exists(pyexe)):
            env_note = "\u26a0️ \u672a\u914d\u7f6e pix2text \u9694\u79bb\u73af\u5883，\u5c06\u4f7f\u7528\u5f53\u524d Python\u3002\n\n"
        msg = (
            f"{env_note}pix2text \u5efa\u8bae\u5b89\u88c5\u5728\u72ec\u7acb\u73af\u5883，\u9996\u6b21\u521d\u59cb\u5316\u4f1a\u81ea\u52a8\u4e0b\u8f7d\u6a21\u578b\u6743\u91cd。\n\n"
            f"1) \u5b89\u88c5：\n   {pip_prefix} install -U pix2text==1.1.4\n\n"
            f"2) \u89e6\u53d1\u4e0b\u8f7d：\n   {pip_prefix} -c \"from pix2text import Pix2Text; Pix2Text()\"\n\n"
            "\u70b9\u51fb“\u590d\u5236\u547d\u4ee4”\u53ef\u76f4\u63a5\u7c98\u8d34\u6267\u884c。"
        )
        parent = self.settings_window if getattr(self, "settings_window", None) else self
        dlg = MessageBox("pix2text \u4f9d\u8d56\u63d0\u793a", msg, parent)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dlg.yesButton.setText("\u590d\u5236\u547d\u4ee4\u5e76\u6253\u5f00\u7ec8\u7aef")
        dlg.cancelButton.setText("\u4ec5\u590d\u5236\u547d\u4ee4")
        self._pix2text_tip_dlg = dlg

        def _do_copy(open_terminal: bool):
            try:
                pyperclip.copy(install_cmd)
            except Exception:
                pass
            if open_terminal:
                self._open_terminal_from_settings(env_key="pix2text")
            try:
                dlg.close()
            except Exception:
                pass

        dlg.yesButton.clicked.connect(lambda: _do_copy(True))
        dlg.cancelButton.clicked.connect(lambda: _do_copy(False))
        try:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            dlg.exec()

    def _show_unimernet_setup_tip(self):
        """Show UniMERNet setup instructions and copy commands."""
        from qfluentwidgets import MessageBox
        variant = self._get_unimernet_variant()
        model_dir = self._get_unimernet_model_dir()
        pyexe = self.cfg.get("unimernet_pyexe", "")
        pip_prefix = f"\"{pyexe}\" -m pip" if (pyexe and os.path.exists(pyexe)) else "python -m pip"
        install_cmd = "\n".join([
            f"{pip_prefix} install -U \"unimernet[full]\"",
            "git lfs install",
            f"git clone https://huggingface.co/wanderkid/unimernet_{variant} \"{model_dir}\"",
        ])
        env_note = ""
        if not (pyexe and os.path.exists(pyexe)):
            env_note = "\u26a0\ufe0f \u672a\u914d\u7f6e UniMERNet \u9694\u79bb\u73af\u5883\uff0c\u5c06\u4f7f\u7528\u5f53\u524d Python\u3002\n\n"
        msg = (
            f"{env_note}UniMERNet \u4e3a\u5b9e\u9a8c\u529f\u80fd\uff0c\u5efa\u8bae\u5728\u9694\u79bb\u73af\u5883\u4e2d\u5b89\u88c5\uff1a\n\n"
            "1) \u5b89\u88c5\u5305\uff1a\n"
            f"   {pip_prefix} install -U \"unimernet[full]\"\n"
            "   \u6216\u5728\u6e90\u7801\u76ee\u5f55\u6267\u884c\uff1apip install -e \".[full]\"\n\n"
            "2) \u4e0b\u8f7d\u6a21\u578b\u6743\u91cd\uff08git-lfs\uff09\uff1a\n"
            "   git lfs install\n"
            f"   git clone https://huggingface.co/wanderkid/unimernet_{variant} \"{model_dir}\"\n\n"
            "\u70b9\u51fb\u201c\u590d\u5236\u547d\u4ee4\u201d\u5373\u53ef\u7c98\u8d34\u6267\u884c\u3002"
        )
        parent = self.settings_window if getattr(self, "settings_window", None) else self
        dlg = MessageBox("UniMERNet \u4f9d\u8d56\u63d0\u793a", msg, parent)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dlg.yesButton.setText("\u590d\u5236\u547d\u4ee4\u5e76\u6253\u5f00\u7ec8\u7aef")
        dlg.cancelButton.setText("\u4ec5\u590d\u5236\u547d\u4ee4")
        self._unimernet_tip_dlg = dlg

        def _do_copy(open_terminal: bool):
            try:
                pyperclip.copy(install_cmd)
            except Exception:
                pass
            if open_terminal:
                self._open_terminal_from_settings(env_key="unimernet")
            try:
                dlg.close()
            except Exception:
                pass

        dlg.yesButton.clicked.connect(lambda: _do_copy(True))
        dlg.cancelButton.clicked.connect(lambda: _do_copy(False))
        try:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            dlg.exec()

    def _upload_image_recognition(self):
        """上传图片并识别公式/文本。"""
        if not self.model:
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        patterns = self._get_supported_image_patterns()
        filter_ = f"图片文件 ({' '.join(patterns)})"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            f"{filter_};;所有文件 (*.*)"
        )
        if not file_path:
            return
        try:
            img = Image.open(file_path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
        except Exception as e:
            custom_warning_dialog("错误", f"图片加载失败: {e}", self)
            return
        self._start_predict_with_pil(img)

    def _model_supports_pdf(self, model_name: str) -> bool:
        m = (model_name or "").lower()
        return m.startswith("pix2text") or m == "unimernet"

    def _prompt_pdf_output_options(self):
        """选择 PDF 识别的导出格式与模板。"""
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
            if dlg.exec() != int(QDialog.DialogCode.Accepted):
                return None
            return dlg.textValue()

        fmt_items = ["Markdown", "LaTeX"]
        fmt = _pick_item("导出格式", "请选择导出格式：", fmt_items, 0)
        if not fmt:
            return None
        style_items = ["论文 (article)", "期刊 (IEEEtran)"]
        style = _pick_item("文档模板", "请选择文档模板：", style_items, 0)
        if not style:
            return None
        fmt_key = "markdown" if fmt.lower().startswith("markdown") else "latex"
        style_key = "paper" if style.startswith("论文") else "journal"
        # 速度/精度选择
        speed_items = ["快 (150 DPI)", "平衡 (200 DPI)", "清晰 (300 DPI)"]
        speed = _pick_item("速度/精度", "请选择识别速度/精度：", speed_items, 1)
        if not speed:
            return None
        dpi_map = {"快 (150 DPI)": 150, "平衡 (200 DPI)": 200, "清晰 (300 DPI)": 300}
        dpi = dpi_map.get(speed, 200)
        return fmt_key, style_key, dpi

    def _upload_pdf_recognition(self):
        """上传 PDF 并识别（输出 Markdown/LaTeX 文档）。"""
        if not self.model:
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        preferred = self._get_preferred_model_for_predict()
        try:
            if preferred != self.current_model or (self.model and not self.model.is_model_ready(preferred)):
                self.on_model_changed(preferred)
        except Exception:
            if preferred != self.current_model:
                self.on_model_changed(preferred)
        if not self._model_supports_pdf(self.current_model):
            custom_warning_dialog("提示", "当前模型不支持 PDF 识别，请切换到 pix2text/UniMERNet。", self)
            return
        if self.current_model.startswith("pix2text") and self.current_model != "pix2text_mixed":
            from qfluentwidgets import MessageBox
            tip = MessageBox(
                "推荐模式",
                "PDF 识别建议使用 pix2text_mixed（混合识别）。\n是否切换并继续？",
                self
            )
            tip.yesButton.setText("切换并继续")
            tip.cancelButton.setText("取消")
            if tip.exec():
                self.on_model_changed("pix2text_mixed")
                if not self._model_supports_pdf(self.current_model):
                    custom_warning_dialog("提示", "当前模型仍不支持 PDF 识别。", self)
                    return
            else:
                return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 PDF 文件",
            "",
            "PDF 文件 (*.pdf);;所有文件 (*.*)"
        )
        if not file_path:
            return
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            custom_warning_dialog("错误", f"缺少 PyMuPDF 依赖: {e}\n请在依赖环境中安装 pymupdf。", self)
            return
        try:
            doc = fitz.open(file_path)
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
        if page_dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        pages = page_dlg.intValue()

        opts = self._prompt_pdf_output_options()
        if not opts:
            return
        fmt_key, style_key, dpi = opts
        self._pdf_output_format = fmt_key
        self._pdf_doc_style = style_key
        self._pdf_dpi = dpi

        if self._predict_busy:
            from qfluentwidgets import MessageBox
            msg = MessageBox("提示", "正在识别，请稍候", self)
            msg.cancelButton.hide()
            msg.exec()
            return

        self._predict_busy = True
        self.set_model_status("识别中...")

        self.pdf_predict_thread = QThread()
        self.pdf_predict_worker = PdfPredictWorker(self.model, file_path, pages, self.current_model, fmt_key, dpi)
        self.pdf_predict_worker.moveToThread(self.pdf_predict_thread)

        self.pdf_progress = QProgressDialog("正在识别 PDF（取消将在当前页结束后生效）...", "取消", 0, pages, self)
        self.pdf_progress.setWindowModality(Qt.WindowModality.WindowModal)
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
            if self.pdf_progress:
                try:
                    self.pdf_progress.close()
                except Exception:
                    pass
                self.pdf_progress = None
            if self.pdf_predict_worker:
                self.pdf_predict_worker.deleteLater()
                self.pdf_predict_worker = None
            if self.pdf_predict_thread:
                self.pdf_predict_thread.deleteLater()
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

    def _on_pdf_progress(self, current: int, total: int):
        if self.pdf_progress:
            try:
                self.pdf_progress.setMaximum(total)
                self.pdf_progress.setValue(current)
            except Exception:
                pass

    def _on_pdf_cancel_requested(self):
        if self.pdf_predict_worker:
            try:
                self.pdf_predict_worker.cancel()
            except Exception:
                pass
        if self.pdf_progress:
            try:
                self.pdf_progress.setLabelText("正在取消（等待当前页结束）...")
            except Exception:
                pass
        if self.pdf_predict_thread:
            try:
                self.pdf_predict_thread.requestInterruption()
            except Exception:
                pass
        self.set_model_status("已取消")

    def _wrap_document_output(self, content: str, fmt_key: str, style_key: str) -> str:
        text = (content or "").strip()
        if not text:
            return ""
        if fmt_key == "markdown":
            if style_key == "paper":
                return "# Title\n\n## Abstract\n\n" + text + "\n\n## References\n"
            return "# Title\n\n" + text
        # LaTeX
        if "\\documentclass" in text and "\\begin{document}" in text:
            return text
        if style_key == "journal":
            docclass = "\\documentclass[journal]{IEEEtran}"
        else:
            docclass = "\\documentclass[11pt]{article}"
        preamble = (
            f"{docclass}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{geometry}\n"
            "\\geometry{a4paper, margin=1in}\n"
            "\\begin{document}\n"
        )
        return preamble + text + "\n\\end{document}\n"

    def _show_document_dialog(self, text: str, fmt_key: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("PDF 识别结果")
        # 显式使用可移动的标准窗口样式，避免在部分路径下出现不可拖动。
        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        dlg.setSizeGripEnabled(True)
        dlg.resize(780, 520)
        lay = QVBoxLayout(dlg)
        info = BodyLabel("识别结果（可编辑/复制/保存）：")
        lay.addWidget(info)
        te = QTextEdit()
        te.setPlainText(text)
        lay.addWidget(te, 1)

        btn_row = QHBoxLayout()
        btn_copy = PushButton(FluentIcon.COPY, "复制")
        btn_save = PushButton(FluentIcon.SAVE, "保存")
        btn_close = PushButton(FluentIcon.CLOSE, "关闭")
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        def _do_copy():
            try:
                pyperclip.copy(te.toPlainText())
                self.set_action_status("已复制文档")
            except Exception as e:
                custom_warning_dialog("错误", f"复制失败: {e}", self)

        def _do_save():
            suffix = "md" if fmt_key == "markdown" else "tex"
            filter_ = "Markdown (*.md)" if fmt_key == "markdown" else "LaTeX (*.tex)"
            path, _ = QFileDialog.getSaveFileName(
                self,
                "保存识别结果",
                f"识别结果.{suffix}",
                filter_
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(te.toPlainText())
                self.set_action_status("已保存文档")
            except Exception as e:
                custom_warning_dialog("错误", f"保存失败: {e}", self)

        btn_copy.clicked.connect(_do_copy)
        btn_save.clicked.connect(_do_save)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()

    def _on_pdf_predict_ok(self, content: str):
        self.set_model_status("完成")
        try:
            if self.pdf_progress:
                self.pdf_progress.setWindowModality(Qt.WindowModality.NonModal)
                self.pdf_progress.close()
        except Exception:
            pass
        try:
            used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "pix2tex")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            weight = None
            if used == "unimernet":
                weight = self._get_unimernet_weight_label()
            if elapsed is not None:
                if weight:
                    print(f"[INFO] PDF 识别完成 model={used} weight={weight} time={elapsed:.2f}s")
                else:
                    print(f"[INFO] PDF 识别完成 model={used} time={elapsed:.2f}s")
            else:
                if weight:
                    print(f"[INFO] PDF 识别完成 model={used} weight={weight}")
                else:
                    print(f"[INFO] PDF 识别完成 model={used}")
        except Exception:
            pass
        fmt_key = self._pdf_output_format or "markdown"
        style_key = self._pdf_doc_style or "paper"
        doc = self._wrap_document_output(content, fmt_key, style_key)
        if not doc:
            custom_warning_dialog("提示", "识别结果为空", self)
            return
        self._show_document_dialog(doc, fmt_key)

    def _on_pdf_predict_fail(self, msg: str):
        if msg == "已取消":
            self.set_model_status("已取消")
            return
        self.set_model_status("失败")
        try:
            used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "pix2tex")
            elapsed = getattr(getattr(self, "pdf_predict_worker", None), "elapsed", None)
            weight = None
            if used == "unimernet":
                weight = self._get_unimernet_weight_label()
            if elapsed is not None:
                if weight:
                    print(f"[INFO] PDF 识别失败 model={used} weight={weight} time={elapsed:.2f}s err={msg}")
                else:
                    print(f"[INFO] PDF 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                if weight:
                    print(f"[INFO] PDF 识别失败 model={used} weight={weight} err={msg}")
                else:
                    print(f"[INFO] PDF 识别失败 model={used} err={msg}")
        except Exception:
            pass

        custom_warning_dialog("错误", msg, self)

    def start_capture(self):
        if not self.isVisible():
            self.showMinimized()  # 只最小化显示，不抢前台
        if not self.model:
            custom_warning_dialog("错误", "模型未初始化", self)
            return
        self.overlay = ScreenCaptureOverlay()
        self.overlay.installEventFilter(self)
        self.overlay.selection_done.connect(self.on_capture_done)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "overlay", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                try:
                    obj.close()
                except Exception:
                    pass
                self.overlay = None
                self.set_action_status("已取消截图")
                return True
        return super().eventFilter(obj, event)

    def on_capture_done(self, pixmap):
        if self.overlay:
            self.overlay.close()
            self.overlay = None
        if pixmap is None:
            return
        if self._predict_busy:
            from qfluentwidgets import MessageBox
            msg = MessageBox("提示", "正在识别，请稍候", self)
            msg.cancelButton.hide()
            msg.exec()
            return
        try:
            img = self._qpixmap_to_pil(pixmap)
        except Exception as e:
            custom_warning_dialog("错误", f"图片处理失败: {e}", self)
            return
        self._start_predict_with_pil(img)

    # 2. 托盘菜单项显示快捷键
    def update_tray_menu(self):
        hk = self.cfg.get("hotkey", "Ctrl+F")
        tray_menu = QMenu()
        tray_menu.addAction("打开主窗口", self.show_window)
        tray_menu.addAction(f"截图识别（{hk}）", self.start_capture)
        tray_menu.addAction("退出", self.truly_exit)
        self.tray_icon.setContextMenu(tray_menu)

    def on_predict_ok(self, latex: str):
        self.set_model_status("完成")
        try:
            used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "pix2tex")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            weight = None
            if used == "unimernet":
                weight = self._get_unimernet_weight_label()
            if elapsed is not None:
                if weight:
                    print(f"[INFO] 识别完成 model={used} weight={weight} time={elapsed:.2f}s")
                else:
                    print(f"[INFO] 识别完成 model={used} time={elapsed:.2f}s")
            else:
                if weight:
                    print(f"[INFO] 识别完成 model={used} weight={weight}")
                else:
                    print(f"[INFO] 识别完成 model={used}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            hk = self.cfg.get("hotkey", "Ctrl+F")
            # 识别完成托盘提示（不打扰主窗口使用）
            try:
                self.tray_icon.showMessage(
                    "识别完成",
                    f"公式已识别。使用快捷键 {hk} 可再次截图。",
                    QSystemTrayIcon.MessageIcon.Information,
                    3500
                )
            except Exception:
                pass
        self.show_confirm_dialog(latex)

    def show_confirm_dialog(self, latex_code: str):
        """显示识别结果确认对话框"""
        code = (latex_code or "").strip()
        if not code:
            _exec_close_only_message_box(self, "提示", "结果为空")
            return

        # 获取当前识别模式（优先使用实际使用的模型，便于正确标注类型）
        current_mode = None
        try:
            current_mode = getattr(getattr(self, "model", None), "last_used_model", None)
        except Exception:
            current_mode = None
        if not current_mode:
            current_mode = getattr(self, "current_model", "pix2tex")
        
        dlg = QDialog(self)
        _apply_close_only_window_flags(dlg)
        dlg.setWindowTitle("识别结果")
        dlg.resize(700, 500)

        lay = QVBoxLayout(dlg)
        
        # 根据模式显示不同的标题
        mode_titles = {
            "pix2tex": "确认或修改 LaTeX：",
            "pix2text": "确认或修改 LaTeX：",
            "pix2text_text": "识别的文字内容：",
            "pix2text_mixed": "识别结果（文字+公式）：",
            "pix2text_page": "整页识别结果：",
            "pix2text_table": "表格识别结果：",
            "unimernet": "确认或修改 LaTeX：",
        }
        info = BodyLabel(mode_titles.get(current_mode, "确认或修改内容："))
        lay.addWidget(info)

        te = QTextEdit()
        te.setText(code)
        lay.addWidget(te)
        
        # 根据模式选择不同的预览策略
        preview_label = None
        preview_view = None
        
        # 公式模式：使用 MathJax 渲染
        if current_mode in ("pix2tex", "pix2text", "unimernet"):
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
                fallback.setStyleSheet("color: #888; padding: 10px;")
                lay.addWidget(fallback)

        # 混合模式：渲染文字和公式
        elif current_mode == "pix2text_mixed":
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
        
        # 表格模式：渲染 HTML 表格
        elif current_mode == "pix2text_table":
            preview_label = BodyLabel("表格预览：")
            lay.addWidget(preview_label)
            
            if ensure_webengine_loaded():
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                preview_view = QWebEngineView()
                preview_view.setMinimumHeight(150)
                preview_view.setHtml(self._build_table_html(code), _get_mathjax_base_url())
                lay.addWidget(preview_view, 1)
                
                render_timer = QTimer(dlg)
                render_timer.setSingleShot(True)
                
                def do_render_table():
                    content = te.toPlainText().strip()
                    if content and preview_view:
                        preview_view.setHtml(self._build_table_html(content), _get_mathjax_base_url())
                
                render_timer.timeout.connect(do_render_table)
                te.textChanged.connect(lambda: render_timer.start(300))
        
        # 纯文字/整页模式：简单文本预览
        elif current_mode in ("pix2text_text", "pix2text_page"):
            preview_label = BodyLabel("文本预览：")
            lay.addWidget(preview_label)
            
            preview_text = QTextEdit()
            preview_text.setReadOnly(True)
            preview_text.setPlainText(code)
            preview_text.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ddd;")
            preview_text.setMinimumHeight(100)
            lay.addWidget(preview_text, 1)
            
            # 同步更新预览
            def update_preview():
                preview_text.setPlainText(te.toPlainText())
            te.textChanged.connect(update_preview)

        btn = PushButton(FluentIcon.ACCEPT, "确定")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda: self.accept_latex(dlg, te))
        lay.addWidget(btn)

        dlg.exec()

    def _build_mixed_html(self, content: str) -> str:
        """构建混合内容（文字+公式）的 HTML"""
        import html
        import re
        
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
      scale: 1
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
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
       padding: 16px; line-height: 1.8; font-size: 14px; }}
.MathJax {{ font-size: 1.1em; }}
</style>
</head>
<body>{body_content}</body>
</html>'''

    def _build_mixed_preview_html(self, formulas: list, labels: list) -> str:
        """构建混合模式的预览 HTML（支持多个公式）"""
        import html
        import re
        
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
<script src="es5/tex-mml-chtml.js" async></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; }}
.item {{ margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 8px; }}
.label {{ display: inline-block; background: #1976d2; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.8; font-size: 14px; }}
</style>
</head>
<body>{"".join(items_html) if items_html else "<p style='color:#888;'>暂无内容</p>"}</body>
</html>'''

    def _build_text_preview_html(self, formulas: list, labels: list) -> str:
        """构建纯文本模式的预览 HTML"""
        import html
        
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
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; }}
.item {{ margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 8px; }}
.label {{ display: inline-block; background: #4caf50; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ line-height: 1.6; font-size: 14px; white-space: pre-wrap; }}
</style>
</head>
<body>{"".join(items_html) if items_html else "<p style='color:#888;'>暂无内容</p>"}</body>
</html>'''

    def _build_table_preview_html(self, formulas: list, labels: list) -> str:
        """构建表格模式的预览 HTML"""
        import html
        
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
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 16px; }}
.item {{ margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 8px; }}
.label {{ display: inline-block; background: #ff9800; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-bottom: 8px; }}
.content {{ font-size: 14px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f2f2f2; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0; }}
</style>
</head>
<body>{"".join(items_html) if items_html else "<p style='color:#888;'>暂无内容</p>"}</body>
</html>'''

    def _build_table_html(self, content: str) -> str:
        """构建表格的 HTML 预览"""
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
       padding: 16px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f2f2f2; }}
tr:nth-child(even) {{ background-color: #f9f9f9; }}
pre {{ white-space: pre-wrap; word-wrap: break-word; }}
</style>
</head>
<body>{table_content}</body>
</html>'''

    def on_predict_fail(self, msg: str):
        self.set_model_status("失败")
        try:
            used = getattr(getattr(self, "model", None), "last_used_model", None)
            if not used:
                used = getattr(getattr(self, "model_wrapper", None), "last_used_model", None)
            if not used:
                used = getattr(self, "current_model", "pix2tex")
            elapsed = getattr(getattr(self, "predict_worker", None), "elapsed", None)
            weight = None
            if used == "unimernet":
                weight = self._get_unimernet_weight_label()
            if elapsed is not None:
                if weight:
                    print(f"[INFO] 识别失败 model={used} weight={weight} time={elapsed:.2f}s err={msg}")
                else:
                    print(f"[INFO] 识别失败 model={used} time={elapsed:.2f}s err={msg}")
            else:
                if weight:
                    print(f"[INFO] 识别失败 model={used} weight={weight} err={msg}")
                else:
                    print(f"[INFO] 识别失败 model={used} err={msg}")
        except Exception:
            pass
        if getattr(self, "tray_icon", None):
            hk = self.cfg.get("hotkey", "Ctrl+F")
            try:
                self.tray_icon.showMessage(
                    "识别失败",
                    f"{msg}\n可使用快捷键 {hk} 重试。",
                    QSystemTrayIcon.MessageIcon.Critical,
                    4000
                )
            except Exception:
                pass
        custom_warning_dialog("错误", msg, self)

    def accept_latex(self, dialog, te: QTextEdit):
        t = te.toPlainText().strip()
        if not t:
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
                content_type = getattr(self, "current_model", "pix2tex")
            self.add_history_record(t, content_type=content_type)
        except Exception as e:
            custom_warning_dialog("错误", f"写入历史失败: {e}", self)
        dialog.accept()

    def clear_history(self):
        # 若无记录给提示
        if not self.history:
            _exec_close_only_message_box(self, "提示", "当前没有历史记录可清空。")
            return
        ret = _exec_close_only_message_box(
            self,
            "确认",
            "确认清空所有历史记录？",
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
        if not self.hotkey:
            # 全局热键已禁用，忽略
            return
        print(f"[Hotkey] try register {seq}")
        try:
            self.hotkey.setShortcut(QKeySequence(seq))
            self.hotkey.register()
            print(f"[Hotkey] global registered={self.hotkey.is_registered()}")
            if self._fallback_shortcut:
                try:
                    self._fallback_shortcut.activated.disconnect()
                except Exception:
                    pass
                self._fallback_shortcut.setParent(None)
                self._fallback_shortcut = None
        except Exception as e:
            print(f"[Hotkey] global failed: {e}")
            if not self._fallback_shortcut:
                self._fallback_shortcut = QShortcut(QKeySequence(seq), self)
                self._fallback_shortcut.activated.connect(self.start_capture)
                print("[Hotkey] fallback QShortcut enabled")

    def on_hotkey_triggered(self):
        print("[Hotkey] Triggered")
        self.start_capture()

    # 设置快捷键窗口支持 ESC 关闭
    def set_shortcut(self):

        dlg = QDialog(self)
        _apply_close_only_window_flags(dlg)
        dlg.setWindowTitle("设置快捷键")
        dlg.setFixedSize(320, 120)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"当前: {self.cfg.get('hotkey', 'Ctrl+F')} 按下新的 Ctrl+字母以创建，或按 Esc 取消"))
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setFixedHeight(34)

        def keyPressEvent(ev):
            if ev.key() == Qt.Key.Key_Escape:
                dlg.reject()
                return
            k = ev.key()
            if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= k <= Qt.Key.Key_Z:
                edit.setText(f"Ctrl+{chr(k)}")
            else:
                edit.setText("")

        edit.keyPressEvent = keyPressEvent
        lay.addWidget(edit)
        btn = PushButton(FluentIcon.ACCEPT, "确定")
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda: self.update_hotkey(edit.toPlainText().strip(), dlg))
        lay.addWidget(btn)
        dlg.exec()

    def update_hotkey(self, text: str, dialog: QDialog):
        if not (text.startswith("Ctrl+") and len(text) == 6 and text[-1].isalpha()):
            custom_warning_dialog("错误", "格式必须 Ctrl+字母", self)
            return
        self.register_hotkey(text)
        # 兼容禁用全局热键的场景
        if self.hotkey and (not self.hotkey.is_registered()) and not self._fallback_shortcut:
            custom_warning_dialog("错误", "快捷键注册失败", self)
            return
        self.cfg.set("hotkey", text)
        dialog.accept()
        _exec_close_only_message_box(self, "提示", f"已更新: {text}")
        self.update_tray_tooltip()
        self.update_tray_menu()
    # ---------- 其它 UI ----------
    def open_settings(self):
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if not self.settings_window:
            self.settings_window = SettingsWindow(self)
            self.settings_window.model_changed.connect(self.on_model_changed)
            self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def open_favorites(self):
        self.favorites_window.show()
        self.favorites_window.raise_()
        self.favorites_window.activateWindow()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()
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

    # ------ 5) 修改 closeEvent（替换原实现） ------
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
                self.tray_icon.showMessage("LaTeXSnipper", "已最小化到托盘")
                self._tray_msg_shown = True
        event.ignore()

    # ------ 6) 修改 truly_exit（替换原实现） ------
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

    def run(self):
        import time
        t0 = time.perf_counter()
        try:
            res = self.model_wrapper.predict(self.image, model_name=self.model_name)
            self.elapsed = time.perf_counter() - t0
            if not res or not res.strip():
                self.failed.emit("识别结果为空")
            else:
                self.finished.emit(res.strip())
        except Exception as e:
            self.elapsed = time.perf_counter() - t0
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
        results = []
        try:
            for i in range(total):
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=self.dpi, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                res = self.model_wrapper.predict(img, model_name=self.model_name)
                if self._cancelled or QThread.currentThread().isInterruptionRequested():
                    _set_elapsed()
                    self.failed.emit("已取消")
                    return
                results.append((res or "").strip())
                self.progress.emit(i + 1, total)
        finally:
            try:
                doc.close()
            except Exception:
                pass

        sep = "\n\n---\n\n" if self.output_format == "markdown" else "\n\n% --- Page ---\n\n"
        content = sep.join([r for r in results if r])
        if not content.strip():
            _set_elapsed()
            self.failed.emit("识别结果为空")
            return
        _set_elapsed()
        self.finished.emit(content.strip())
# ---------------- 编辑对话框 ----------------
from PyQt6.QtCore import Qt
# 替换原 EditFormulaDialog：使用 QDialog，支持 exec/accept/reject
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

class EditFormulaDialog(QDialog):
    def __init__(self, latex: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑")
        self.resize(700, 500)

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
            self.preview_view.setHtml(build_math_html(latex or ""), _get_mathjax_base_url())
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
            fallback.setStyleSheet("color: #888; padding: 20px;")
            lay.addWidget(fallback, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
    
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
            html = build_math_html(latex)
            self.preview_view.setHtml(html, _get_mathjax_base_url())
        except Exception as e:
            print(f"[EditDialog Render] 渲染失败: {e}")

    def value(self) -> str:
        return self.editor.toPlainText().strip()

state_path = Path(INSTALL_BASE_DIR) / ".deps_state.json"

# 防止重复进入依赖修复流程
_repair_in_progress = False

def show_dependency_wizard(always_show_ui=True):
    """
    当环境损坏或依赖缺失时，强制打开依赖修复窗口（仅尝试一次）。
    需在主程序已创建 QApplication 后调用。
    """
    global _repair_in_progress
    if _repair_in_progress:
        print("[WARN] 已在修复流程中，跳过重复调用。")
        return False
    _repair_in_progress = True

    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance()
    if app is None:
        print("[WARN] 依赖修复需要 GUI，但当前未创建 QApplication。请在主程序创建 QApplication 后再调用。")
        _repair_in_progress = False
        return False

    QMessageBox.warning(
        None, "依赖修复",
        "检测到依赖环境损坏或缺失，请在接下来的窗口中重新选择安装目录或修复依赖。"
    )
    try:
        ok = ensure_deps(always_show_ui=always_show_ui)
        if not ok:
            QMessageBox.critical(None, "修复失败", "依赖修复未成功。程序将退出。")
        else:
            QMessageBox.information(None, "修复完成", "依赖环境修复成功，请重新启动程序。")
        return ok
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[FATAL] show_dependency_wizard 失败: {e}\n{tb}")
        QMessageBox.critical(None, "严重错误", f"依赖修复失败：{e}")
        return False
    finally:
        _repair_in_progress = False
# ==============================
# 🧩 环境隔离保护（非常关键）
# 防止 PyInstaller 或旧虚拟环境污染
# ==============================
for var in ("PYTHONHOME", "PYTHONPATH"):
    if var in os.environ:
        print(f"[DEBUG] 清除环境变量 {var}")
        os.environ.pop(var)

init_app_logging()

# 文件: 'src/main.py'（入口关键片段）
if __name__ == "__main__":
    import os, sys
    force_deps_check = '--force-deps-check' in sys.argv
    force_verify_env = os.environ.pop("LATEXSNIPPER_FORCE_VERIFY", None) == "1"
    # 判断是否为 PyInstaller 打包环境
    if getattr(sys, 'frozen', False):
        # 打包环境，直接运行主程序，不再重启到私有解释器
        from PyQt6.QtWidgets import QApplication
        # 确保标准流可用
        _ensure_std_streams()
        app = QApplication.instance() or QApplication(sys.argv)
        # 3) UI 主题（可选）
        try:
            from qfluentwidgets import Theme, setTheme, setThemeColor
            setTheme(Theme.AUTO)
            setThemeColor("#0078D4")
        except Exception:
            pass
        # 检查是否需要强制依赖检验
        if force_deps_check or force_verify_env:
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True, force_verify=True)
            if not ok:
                sys.exit(1)
        # 4) 可选：延迟检测 torch，避免 VC++ 运行库缺失导致崩溃
        try:
            import torch
            print("[INFO] torch ok, cuda:", torch.cuda.is_available())
        except Exception as e:
            print("[WARN] torch 初始化失败：", e)
            print("[HINT] 请安装 Microsoft Visual C++ 2015–2022(x64) 运行库后重试。")
        win = MainWindow()
        print("[DEBUG] MainWindow 创建完成，准备显示窗口")
        win.show()
        print("[DEBUG] win.show() 完成，进入事件循环")
        sys.exit(app.exec())
    else:
        # 开发环境，保留原有依赖检测和私有解释器重启逻辑
        from PyQt6.QtWidgets import QApplication
        _ensure_std_streams()
        app = QApplication.instance() or QApplication(sys.argv)
        force_deps_check = '--force-deps-check' in sys.argv
        open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"
        force_verify_env = os.environ.pop("LATEXSNIPPER_FORCE_VERIFY", None) == "1"
        # 检查是否需要强制依赖检验
        if force_deps_check or force_verify_env:
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True, force_verify=True)
        elif open_wizard_on_start:
            ok = ensure_deps(prompt_ui=True, always_show_ui=True, from_settings=True, force_verify=True)
        else:
            ok = ensure_deps(prompt_ui=True, always_show_ui=False, from_settings=False)
        if not ok:
            sys.exit(1)
        try:
            from qfluentwidgets import Theme, setTheme, setThemeColor
            setTheme(Theme.AUTO)
            setThemeColor("#0078D4")
        except Exception:
            pass
        try:
            import torch
            print("[INFO] torch ok, cuda:", torch.cuda.is_available())
        except Exception as e:
            print("[WARN] torch 初始化失败：", e)
            print("[HINT] 请安装 Microsoft Visual C++ 2015–2022(x64) 运行库后重试。")
        win = MainWindow()
        print("[DEBUG] MainWindow 创建完成，准备显示窗口")
        win.show()
        print("[DEBUG] win.show() 完成，进入事件循环")
        sys.exit(app.exec())





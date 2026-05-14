# --- Crash guard & runtime sanity, put this at the VERY TOP of 'src/main.py' ---
import atexit
import datetime
import faulthandler
import json
import os
import pathlib
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from runtime.linux_graphics_runtime import apply_linux_graphics_fallbacks
from runtime.startup_gui_deps import early_ensure_pyqt6_and_pywin32

# Force UTF-8 encoding for all subprocess pipes on Windows (avoids gbk decode crashes)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

apply_linux_graphics_fallbacks()
early_ensure_pyqt6_and_pywin32()

_CRASH_FH = None

def _pre_bootstrap_runtime():
    global _CRASH_FH


    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")


    os.environ.setdefault("ORT_NO_AZURE_EP", "1")


    log_dir = pathlib.Path.home() / ".latexsnipper" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    crash_log = log_dir / "crash-native.log"

    try:

        _CRASH_FH = open(crash_log, "a", encoding="utf-8", buffering=1)
        _CRASH_FH.write(f"\n=== LaTeXSnipper start {datetime.datetime.now().isoformat()} ===\n")
        faulthandler.enable(all_threads=True, file=_CRASH_FH)
    except Exception:

        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

_pre_bootstrap_runtime()


def _load_qt_symbols():
    from PyQt6.QtCore import (
        QBuffer,
        QCoreApplication,
        QIODevice,
        Qt,
        QTimer,
        pyqtSignal,
    )
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
    return (
        QApplication,
        QBuffer,
        QCoreApplication,
        QHBoxLayout,
        QIcon,
        QIODevice,
        QLabel,
        QMainWindow,
        QMessageBox,
        QScrollArea,
        QTimer,
        QVBoxLayout,
        QWidget,
        Qt,
        pyqtSignal,
    )


(
    QApplication,
    QBuffer,
    QCoreApplication,
    QHBoxLayout,
    QIcon,
    QIODevice,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
) = _load_qt_symbols()


try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

app = QApplication.instance() or QApplication(sys.argv)

from runtime.app_paths import resource_path  # noqa: E402
from runtime.python_runtime_resolver import (  # noqa: E402
    APP_DIR,
    _append_private_site_packages,
    _clean_bad_env,
    _config_path,
    _default_python_exe_name,
    _find_install_base_python,
    _in_ide,
    _initial_deps_dir,
    _is_packaged_mode,
    _relaunch_with,
    _same_exe,
    _sanitize_sys_path,
    _win_subprocess_kwargs,
    ensure_full_python_or_prompt,
    resolve_install_base_dir,
)

from runtime.single_instance import (  # noqa: E402
    ensure_single_instance as _ensure_single_instance,
    release_single_instance_lock as _release_single_instance_lock,
)


def _show_already_running_message() -> None:
    try:
        icon_path = resource_path("assets/icon.ico")
        if icon_path and os.path.exists(icon_path):
            icon = QIcon(icon_path)
            app.setWindowIcon(icon)
        else:
            icon = None
        msg = QMessageBox()
        msg.setWindowTitle("LaTeXSnipper")
        msg.setText("Another instance is already running.")
        msg.setIcon(QMessageBox.Icon.Information)
        if icon is not None:
            msg.setWindowIcon(icon)
        msg.exec()
    except Exception:
        print("[WARN] already running; exiting")


if not _ensure_single_instance():
    _show_already_running_message()
    sys.exit(0)

atexit.register(_release_single_instance_lock)


from runtime.startup_splash import (  # noqa: E402
    FORCE_ENTER_STARTUP_MESSAGE,
    deps_force_entered as _deps_force_entered,
    ensure_startup_splash as _ensure_startup_splash,
    finish_startup_splash as _finish_startup_splash,
    hide_startup_splash_for_modal as _hide_startup_splash_for_modal,
    mark_startup_force_entered as _mark_startup_force_entered,
    startup_deps_resume_message as _startup_deps_resume_message,
    startup_force_enter_pending as _startup_force_enter_pending,
    startup_status_message as _startup_status_message,
    take_startup_splash as _take_startup_splash,
    update_startup_splash as _update_startup_splash,
)
from runtime.runtime_logging import (  # noqa: E402
    TeeWriter,
    init_app_logging,
    open_debug_console,
)
from ui.theme_controller import (  # noqa: E402
    ThemeControllerMixin,
    apply_theme_mode,
    read_theme_mode_from_config,
)
from runtime.dependency_bootstrap_controller import (  # noqa: E402
    ensure_deps,
    load_startup_modules,
)


_ensure_startup_splash("配置 MathJax 与 WebEngine...")

# Ensure src/ is on sys.path so that sibling packages (runtime, backend, etc.) are importable
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# ============ QWebEngine profile configuration ============
from runtime.webengine_runtime import configure_default_webengine_profile  # noqa: E402

configure_default_webengine_profile()

print(f"[DEBUG] Application root: {APP_DIR}")
print(f"[DEBUG] Packaged mode: {_is_packaged_mode()}")


DEPS_DIR = _initial_deps_dir()
DEPS_DIR.mkdir(parents=True, exist_ok=True)

print(f"[DEBUG] Dependency directory: {DEPS_DIR}")


_ensure_startup_splash("加载依赖向导模块...")
_ensure_startup_splash("加载设置模块...")


custom_warning_dialog, clear_deps_state, SettingsWindow = load_startup_modules()


_ensure_startup_splash("定位依赖目录...")
INSTALL_BASE_DIR = resolve_install_base_dir()


if _is_packaged_mode():
    py_exe_path = _find_install_base_python(INSTALL_BASE_DIR)
    py_exe = py_exe_path if py_exe_path is not None else (INSTALL_BASE_DIR / "python311" / _default_python_exe_name())

    if py_exe.exists():
        if os.environ.get("LATEXSNIPPER_FORCE_PRIVATE_PY") == "1":
            # redirect only when explicitly enabled
            if os.environ.get("LATEXSNIPPER_INNER_PY") != "1":
                print(f"[INFO] packaged: redirect to private python {py_exe}")
                import subprocess
                env = os.environ.copy()
                env["LATEXSNIPPER_INNER_PY"] = "1"

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


                run_py = py_exe
                pyw = py_exe.parent / "pythonw.exe"
                if pyw.exists():
                    run_py = pyw
                argv = [str(run_py), os.path.abspath(__file__), *sys.argv[1:]]
                subprocess.Popen(argv, env=env, **_win_subprocess_kwargs())
                sys.exit(0)
            else:
                print("[INFO] packaged: already in private python")
        else:
            print("[INFO] packaged: keep bundled runtime, mount deps dir")
    else:
        print(f"[WARN] packaged: private python not found: {py_exe}, keep bundled runtime")

BASE_DIR = Path(INSTALL_BASE_DIR)
DEPS_DIR = BASE_DIR
_clean_bad_env()

_ensure_startup_splash("检查 Python 运行时...")
TARGET_PY = ensure_full_python_or_prompt(BASE_DIR)
if not TARGET_PY:
    print("[ERROR] 未找到可用的完整 Python 3.11。")
    sys.exit(2)


os.environ["LATEXSNIPPER_PYEXE"] = TARGET_PY
os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = str(BASE_DIR)
os.environ["LATEXSNIPPER_DEPS_DIR"] = str(BASE_DIR)
os.environ.setdefault("PYTHONNOUSERSITE", "1" if os.name == "nt" else "0")
os.environ.pop("PYTHONHOME", None)
os.environ.pop("PYTHONPATH", None)
os.environ.pop("MATHCRAFT_HOME", None)


if not _in_ide() and not _is_packaged_mode():
    if not _same_exe(sys.executable, TARGET_PY):
        _relaunch_with(TARGET_PY)
elif _in_ide():
    print("[INFO] IDE 中运行，保持当前解释器，但使用私有依赖路径")


if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") != "1":
    _ensure_startup_splash("挂载私有依赖环境...")
    _sanitize_sys_path(TARGET_PY, BASE_DIR)
    if _is_packaged_mode():
        _append_private_site_packages(TARGET_PY)


    _open_wizard_env = (os.environ.get("LATEXSNIPPER_OPEN_WIZARD", "") == "1")
    if _open_wizard_env:
        print("[INFO] 依赖向导模式：跳过启动预检查，由向导统一验证。")
    else:
        import importlib as _imp
        _ensure_startup_splash("检查已安装功能层...")
        _db = _imp.import_module("bootstrap.deps_bootstrap")
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


current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


def _load_runtime_modules():
    from PIL import Image as _Image
    from qfluentwidgets import (
        PrimaryPushButton,
    )

    return (
        _Image,
        PrimaryPushButton,
    )


(
    Image,
    PrimaryPushButton,
) = _load_runtime_modules()

from preview.math_preview import (  # noqa: E402
    configure_math_preview_runtime,
)
from ui.menu_helpers import action_btn_style as _action_btn_style  # noqa: E402
from preview.preview_controller import PreviewControllerMixin  # noqa: E402
from ui.model_runtime_controller import ModelRuntimeControllerMixin  # noqa: E402
from ui.file_drop import FileDropMixin  # noqa: E402
from ui.tray_controller import TrayControllerMixin  # noqa: E402
from ui.history_controller import HistoryControllerMixin  # noqa: E402
from recognition.recognition_controller import RecognitionControllerMixin  # noqa: E402
from recognition.pdf_controller import PdfRecognitionControllerMixin  # noqa: E402
from ui.predict_result_controller import PredictResultControllerMixin  # noqa: E402
from capture.capture_controller import CaptureControllerMixin  # noqa: E402
from ui.hotkey_controller import HotkeyControllerMixin  # noqa: E402
from ui.window_openers import WindowOpenersMixin  # noqa: E402
from ui.app_lifecycle_controller import AppLifecycleMixin  # noqa: E402
from ui.main_window_setup import MainWindowSetupMixin  # noqa: E402
from ui.status_controller import StatusControllerMixin  # noqa: E402
from ui.editor_actions_controller import EditorActionsControllerMixin  # noqa: E402

configure_math_preview_runtime(APP_DIR)

os.makedirs(DEPS_DIR, exist_ok=True)
os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("ORT_DISABLE_AZURE", "1")

def _ensure_std_streams():
    """Restore stdout and stderr only when they are missing, closed, or unusable."""

    def _is_bad(f):
        if f is None:
            return True
        if not hasattr(f, "write"):
            return True
        if getattr(f, "closed", False):
            return True

        if isinstance(f, TeeWriter):
            return f._closed
        return False

    def _try_restore():
        """Try to restore a stream."""

        if _is_bad(getattr(sys, "stdout", None)):
            if hasattr(sys, "__stdout__") and sys.__stdout__ is not None and not getattr(sys.__stdout__, "closed", False):
                sys.stdout = sys.__stdout__

        if _is_bad(getattr(sys, "stderr", None)):
            if hasattr(sys, "__stderr__") and sys.__stderr__ is not None and not getattr(sys.__stderr__, "closed", False):
                sys.stderr = sys.__stderr__


        if _is_bad(getattr(sys, "stdout", None)):
            try:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
            except Exception:
                pass

        if _is_bad(getattr(sys, "stderr", None)):

            if not _is_bad(getattr(sys, "stdout", None)):
                sys.stderr = sys.stdout
            else:
                try:
                    sys.stderr = open(os.devnull, "w", encoding="utf-8")
                except Exception:
                    pass

    _try_restore()


_ensure_std_streams()
try:
    from PyQt6 import sip  # PyQt6 bundled sip, preferred for type resolution
except Exception:
    try:
        import sip  # pyright: ignore[reportMissingImports]  # fallback for top-level sip package
    except Exception:
        sip = None


class MainWindow(
    MainWindowSetupMixin,
    ThemeControllerMixin,
    PreviewControllerMixin,
    FileDropMixin,
    TrayControllerMixin,
    ModelRuntimeControllerMixin,
    StatusControllerMixin,
    EditorActionsControllerMixin,
    HistoryControllerMixin,
    RecognitionControllerMixin,
    PdfRecognitionControllerMixin,
    PredictResultControllerMixin,
    CaptureControllerMixin,
    HotkeyControllerMixin,
    WindowOpenersMixin,
    AppLifecycleMixin,
    QMainWindow,
):
    """Main application window based on QMainWindow."""
    _model_warmup_result_signal = pyqtSignal()
    _preview_latex_render_request = pyqtSignal(str, str)


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


    def _apply_primary_buttons(self) -> None:
        """Apply primary button styling."""
        try:
            btns = self.findChildren(PrimaryPushButton)
        except Exception:
            return
        for b in btns or []:
            try:
                b.setStyleSheet(_action_btn_style())
            except Exception:
                pass


    def _safe_call(self, name, fn):
        print(f"[SlotEnter] {name}")
        try:
            fn()
            print(f"[SlotExit] {name}")
        except Exception as e:
            print(f"[SlotError] {name}: {e}")
    def _defer(self, fn):
        QTimer.singleShot(0, fn)


    def _qpixmap_to_pil(self, pixmap):
        buf = QBuffer()
        if not buf.open(QIODevice.OpenModeFlag.ReadWrite):
            raise RuntimeError("QBuffer 打开失败")
        if not pixmap.save(buf, "PNG"):
            raise RuntimeError("QPixmap 保存失败")
        data = bytes(buf.data())
        buf.close()
        return Image.open(BytesIO(data)).convert("RGB")


for var in ("PYTHONHOME", "PYTHONPATH", "MATHCRAFT_HOME"):
    if var in os.environ:
        print(f"[DEBUG] 清除环境变量 {var}")
        os.environ.pop(var)

_ensure_startup_splash(_startup_status_message("初始化日志..."))
init_app_logging()
_ensure_startup_splash(_startup_status_message("检查日志窗口设置..."))
open_debug_console(force=False, tee=True)


if __name__ == "__main__":
    import multiprocessing
    import os
    import sys
    multiprocessing.freeze_support()

    if getattr(sys, 'frozen', False):
        # Packaged builds run directly from the frozen interpreter.
        from PyQt6.QtWidgets import QApplication

        _ensure_std_streams()
        app = QApplication.instance() or QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        splash = _take_startup_splash(app, _startup_status_message("初始化界面..."))
        open_wizard_on_start = os.environ.pop("LATEXSNIPPER_OPEN_WIZARD", None) == "1"

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
        # Development runs keep dependency checks and private-interpreter relaunch.
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
        if needs_interactive_deps_ui or resume_message == FORCE_ENTER_STARTUP_MESSAGE:
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

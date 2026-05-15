from __future__ import annotations

import atexit
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from preview.math_preview import configure_math_preview_runtime
from runtime.app_paths import resource_path
from runtime.dependency_bootstrap_controller import load_startup_modules
from runtime.python_runtime_resolver import (
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
from runtime.single_instance import (
    ensure_single_instance,
    release_single_instance_lock,
)
from runtime.startup_splash import (
    deps_force_entered,
    ensure_startup_splash,
    hide_startup_splash_for_modal,
    mark_startup_force_entered,
)
from runtime.webengine_runtime import configure_default_webengine_profile


@dataclass(frozen=True)
class BootstrapContext:
    app: QApplication
    app_dir: Path
    base_dir: Path
    deps_dir: Path
    target_python: str


_BOOTSTRAP_CONTEXT: BootstrapContext | None = None


def _ensure_qt_application() -> QApplication:
    try:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass
    return QApplication.instance() or QApplication(sys.argv)


def _show_already_running_message(app: QApplication) -> None:
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


def _ensure_single_instance(app: QApplication) -> None:
    if ensure_single_instance():
        atexit.register(release_single_instance_lock)
        return
    _show_already_running_message(app)
    raise SystemExit(0)


def _ensure_src_path() -> None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(current_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)


def _maybe_redirect_to_private_python(install_base_dir: Path) -> None:
    if not _is_packaged_mode():
        return

    py_exe_path = _find_install_base_python(install_base_dir)
    py_exe = py_exe_path if py_exe_path is not None else (install_base_dir / "python311" / _default_python_exe_name())

    if not py_exe.exists():
        print(f"[WARN] packaged: private python not found: {py_exe}, keep bundled runtime")
        return

    if os.environ.get("LATEXSNIPPER_FORCE_PRIVATE_PY") != "1":
        print("[INFO] packaged: keep bundled runtime, mount deps dir")
        return

    if os.environ.get("LATEXSNIPPER_INNER_PY") == "1":
        print("[INFO] packaged: already in private python")
        return

    print(f"[INFO] packaged: redirect to private python {py_exe}")
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
    argv = [str(run_py), os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"), *sys.argv[1:]]
    subprocess.Popen(argv, env=env, **_win_subprocess_kwargs())
    raise SystemExit(0)


def _prepare_python_runtime(install_base_dir: Path) -> tuple[Path, str]:
    base_dir = Path(install_base_dir)
    _clean_bad_env()

    ensure_startup_splash("检查 Python 运行时...")
    target_py = ensure_full_python_or_prompt(base_dir)
    if not target_py:
        print("[ERROR] 未找到可用的完整 Python 3.11。")
        raise SystemExit(2)

    os.environ["LATEXSNIPPER_PYEXE"] = target_py
    os.environ["LATEXSNIPPER_INSTALL_BASE_DIR"] = str(base_dir)
    os.environ["LATEXSNIPPER_DEPS_DIR"] = str(base_dir)
    os.environ.setdefault("PYTHONNOUSERSITE", "1" if os.name == "nt" else "0")
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("PYTHONPATH", None)
    os.environ.pop("MATHCRAFT_HOME", None)

    if not _in_ide() and not _is_packaged_mode():
        if not _same_exe(sys.executable, target_py):
            _relaunch_with(target_py)
    elif _in_ide():
        print("[INFO] IDE 中运行，保持当前解释器，但使用私有依赖路径")

    return base_dir, target_py


def _bootstrap_dependencies(base_dir: Path, target_py: str) -> None:
    if os.environ.get("LATEXSNIPPER_BOOTSTRAPPED") == "1":
        return

    ensure_startup_splash("挂载私有依赖环境...")
    _sanitize_sys_path(target_py, base_dir)
    if _is_packaged_mode():
        _append_private_site_packages(target_py)

    open_wizard_env = os.environ.get("LATEXSNIPPER_OPEN_WIZARD", "") == "1"
    if open_wizard_env:
        print("[INFO] 依赖向导模式：跳过启动预检查，由向导统一验证。")
        return

    ensure_startup_splash("检查已安装功能层...")
    deps_bootstrap = importlib.import_module("bootstrap.deps_bootstrap")
    try:
        ok = deps_bootstrap.ensure_deps(
            prompt_ui=True,
            always_show_ui=False,
            require_layers=("BASIC", "CORE"),
            deps_dir=str(base_dir),
            before_show_ui=hide_startup_splash_for_modal,
            after_force_enter=mark_startup_force_entered,
        )
        if ok:
            os.environ["LATEXSNIPPER_DEPS_OK"] = "1"
            if deps_force_entered(deps_bootstrap):
                mark_startup_force_entered()
    except Exception as e:
        print(f"[WARN] deps wizard failed: {e}")


def bootstrap_application() -> BootstrapContext:
    global _BOOTSTRAP_CONTEXT
    if _BOOTSTRAP_CONTEXT is not None:
        return _BOOTSTRAP_CONTEXT

    app = _ensure_qt_application()
    _ensure_single_instance(app)

    ensure_startup_splash("配置 MathJax 与 WebEngine...")
    _ensure_src_path()
    configure_default_webengine_profile()

    print(f"[DEBUG] 应用根目录: {APP_DIR}")
    print(f"[DEBUG] 打包模式: {_is_packaged_mode()}")

    deps_dir = _initial_deps_dir()
    deps_dir.mkdir(parents=True, exist_ok=True)
    print(f"[DEBUG] 依赖目录: {deps_dir}")

    ensure_startup_splash("加载依赖向导模块...")
    ensure_startup_splash("加载设置模块...")
    load_startup_modules()

    ensure_startup_splash("定位依赖目录...")
    install_base_dir = resolve_install_base_dir()
    _maybe_redirect_to_private_python(install_base_dir)
    base_dir, target_py = _prepare_python_runtime(install_base_dir)
    _bootstrap_dependencies(base_dir, target_py)

    configure_math_preview_runtime(APP_DIR)
    os.makedirs(base_dir, exist_ok=True)
    os.environ.setdefault("ORT_DISABLE_OPENCL", "1")
    os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
    os.environ.setdefault("ORT_DISABLE_AZURE", "1")

    for var in ("PYTHONHOME", "PYTHONPATH", "MATHCRAFT_HOME"):
        if var in os.environ:
            print(f"[DEBUG] 清除环境变量 {var}")
            os.environ.pop(var)

    _BOOTSTRAP_CONTEXT = BootstrapContext(
        app=app,
        app_dir=Path(APP_DIR),
        base_dir=base_dir,
        deps_dir=base_dir,
        target_python=target_py,
    )
    return _BOOTSTRAP_CONTEXT

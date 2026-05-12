"""Early GUI dependency checks used before Qt symbols are imported."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys

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


def _gui_dep_version_mismatches() -> list[str]:
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


def _install_stable_gui_deps(pyexe: str, reason: str) -> None:
    print(f"[WARN] GUI 依赖需要修复：{reason}")
    subprocess.check_call([pyexe, "-m", "pip", "install", "--force-reinstall", *STABLE_GUI_PIP_SPECS])
    importlib.invalidate_caches()


def early_ensure_pyqt6_and_pywin32() -> None:
    pyexe = sys.executable
    exe_name = os.path.basename(pyexe).lower()
    # Enable early pip self-repair only in source-interpreter mode; packaged executables do not support `-m pip` semantics.
    can_pip_repair = (not getattr(sys, "frozen", False)) and exe_name.startswith("python")
    if not can_pip_repair:
        print("[INFO] 打包模式或非 python 解释器启动，跳过早期 pip 自修复。")
        return

    mismatches = _gui_dep_version_mismatches()
    if mismatches:
        _install_stable_gui_deps(pyexe, "; ".join(mismatches))

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
        try:
            from PyQt6 import QtWebEngineWidgets as _QtWebEngineWidgets
            _ = _QtWebEngineWidgets
        except Exception:
            print("[WARN] 未检测到 PyQt6-WebEngine，尝试自动安装...")
            _install_stable_gui_deps(pyexe, "PyQt6-WebEngine 未安装")
            importlib.invalidate_caches()

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

    if os.name == "nt":
        try:
            import win32api as _win32api
            _ = _win32api
        except ImportError:
            print("[WARN] 未检测到 win32api，尝试自动安装 pywin32...")
            subprocess.check_call([pyexe, "-m", "pip", "install", "pywin32"])
            importlib.invalidate_caches()
            print("[OK] pywin32 安装成功。请关闭并重新启动本程序以完成初始化。")
            import time
            time.sleep(2)
            sys.exit(0)

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
            import types

            def _copy_stub(_text):
                print("[WARN] pyperclip 不可用，无法复制到剪贴板。")

            sys.modules.setdefault("pyperclip", types.SimpleNamespace(copy=_copy_stub))

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

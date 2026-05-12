"""Early GUI dependency checks used before Qt symbols are imported."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time
import types

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

    mismatches: list[str] = []
    for dist_name, expected in STABLE_GUI_VERSION_PINS.items():
        try:
            actual = metadata.version(dist_name)
        except metadata.PackageNotFoundError:
            actual = None
        except Exception:
            actual = None
        if actual != expected:
            shown = actual if actual is not None else "not installed"
            mismatches.append(f"{dist_name}={shown}, expected {expected}")
    return mismatches


def _install_stable_gui_deps(pyexe: str, reason: str) -> None:
    print(f"[WARN] GUI dependencies require repair: {reason}")
    subprocess.check_call([pyexe, "-m", "pip", "install", "--force-reinstall", *STABLE_GUI_PIP_SPECS])
    importlib.invalidate_caches()


def early_ensure_pyqt6_and_pywin32() -> None:
    pyexe = sys.executable
    exe_name = os.path.basename(pyexe).lower()
    can_pip_repair = (not getattr(sys, "frozen", False)) and exe_name.startswith("python")
    if not can_pip_repair:
        print("[INFO] Packaged mode or non-python launcher detected; skipping early pip self-repair.")
        return

    mismatches = _gui_dep_version_mismatches()
    if mismatches:
        _install_stable_gui_deps(pyexe, "; ".join(mismatches))

    try:
        import PyQt6 as _PyQt6
        _ = _PyQt6
    except ImportError:
        print("[WARN] PyQt6 is missing; attempting automatic installation.")
        _install_stable_gui_deps(pyexe, "PyQt6 is missing")
        importlib.invalidate_caches()
        import PyQt6 as _PyQt6
        _ = _PyQt6
        print("[OK] PyQt6 installed.")
    else:
        try:
            from PyQt6 import QtWebEngineWidgets as _QtWebEngineWidgets
            _ = _QtWebEngineWidgets
        except Exception:
            print("[WARN] PyQt6-WebEngine is missing; attempting automatic installation.")
            _install_stable_gui_deps(pyexe, "PyQt6-WebEngine is missing")
            importlib.invalidate_caches()

    try:
        import qfluentwidgets as _qfluentwidgets
        _ = _qfluentwidgets
    except ImportError:
        print("[WARN] PyQt6-Fluent-Widgets is missing; attempting automatic installation.")
        _install_stable_gui_deps(pyexe, "PyQt6-Fluent-Widgets is missing")
        importlib.invalidate_caches()
        import qfluentwidgets as _qfluentwidgets
        _ = _qfluentwidgets
        print("[OK] PyQt6-Fluent-Widgets installed.")

    if os.name == "nt":
        try:
            import win32api as _win32api
            _ = _win32api
        except ImportError:
            print("[WARN] win32api is missing; attempting pywin32 installation.")
            subprocess.check_call([pyexe, "-m", "pip", "install", "pywin32"])
            importlib.invalidate_caches()
            print("[OK] pywin32 installed. Restart the app to complete initialization.")
            time.sleep(2)
            sys.exit(0)

    try:
        import pyperclip as _pyperclip
        _ = _pyperclip
    except ImportError:
        print("[WARN] pyperclip is missing; attempting automatic installation.")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "pyperclip"])
            importlib.invalidate_caches()
            import pyperclip as _pyperclip
            _ = _pyperclip
            print("[OK] pyperclip installed.")
        except Exception as exc:
            print(f"[WARN] pyperclip automatic installation failed: {exc}")

            def _copy_stub(_text):
                print("[WARN] pyperclip is unavailable; clipboard copy is disabled.")

            sys.modules.setdefault("pyperclip", types.SimpleNamespace(copy=_copy_stub))

    try:
        import requests as _requests
        _ = _requests
    except ImportError:
        print("[WARN] requests is missing; attempting automatic installation.")
        try:
            subprocess.check_call([pyexe, "-m", "pip", "install", "requests"])
            importlib.invalidate_caches()
            import requests as _requests
            _ = _requests
            print("[OK] requests installed.")
        except Exception as exc:
            print(f"[WARN] requests automatic installation failed: {exc}")

            def _requests_stub(*_args, **_kwargs):
                raise RuntimeError("requests is unavailable; update checks are disabled.")

            sys.modules.setdefault("requests", types.SimpleNamespace(get=_requests_stub, post=_requests_stub))

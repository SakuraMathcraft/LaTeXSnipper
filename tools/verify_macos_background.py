"""Verify from source that LaTeXSnipper stays in the menu bar during capture.

Run with an isolated home directory so a running installed copy does not own
the single-instance lock:

    HOME=/tmp/lsn-verify .venv/bin/python -X utf8 tools/verify_macos_background.py

The script starts the real main window, puts the application in the background,
hides the window the way the close button does, then starts a capture and
reports whether the capture surface appeared without the application or the
main window coming back to the front.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QCloseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from application.bootstrap import bootstrap_application  # noqa: E402
from platform_services.protocols import PermissionResult, PermissionState  # noqa: E402
from ui.controllers.runtime_log import (  # noqa: E402
    apply_runtime_log_window_preference,
)
from ui.main_window import MainWindow  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(
        f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}",
        flush=True,
    )


def deactivate_application() -> bool:
    """Send the application to the background by handing focus to another app."""
    import subprocess

    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Finder" to activate'],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        pass
    try:
        import AppKit

        AppKit.NSApp.deactivate()
        return True
    except Exception:
        return False


def state_name() -> str:
    return QApplication.applicationState().name


def onscreen_window_count() -> int:
    """Count this process's windows the window server actually draws.

    Qt's isVisible and NSWindow.isVisible both stay true for a panel macOS has
    hidden because its application is inactive, so ask the window server.
    ctypes keeps this free of PyObjC, which the project does not declare.
    """
    import ctypes
    import ctypes.util
    import os

    cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    def key(name: str) -> int:
        return ctypes.c_void_p.in_dll(cg, name).value

    def number(item: int, name: str, fmt: int, ctype):
        ref = cf.CFDictionaryGetValue(item, key(name))
        out = ctype()
        if not ref or not cf.CFNumberGetValue(ref, fmt, ctypes.byref(out)):
            return None
        return out.value

    on_screen_only, null_window, sint32, float64 = 1, 0, 3, 6
    windows = cg.CGWindowListCopyWindowInfo(on_screen_only, null_window)
    if not windows:
        return 0
    try:
        count = 0
        for index in range(cf.CFArrayGetCount(windows)):
            item = cf.CFArrayGetValueAtIndex(windows, index)
            pid = number(item, "kCGWindowOwnerPID", sint32, ctypes.c_int32)
            alpha = number(item, "kCGWindowAlpha", float64, ctypes.c_double)
            if pid == os.getpid() and (alpha or 0) > 0:
                count += 1
        return count
    finally:
        cf.CFRelease(windows)


def main() -> int:
    # The splash pixmap blocks on a first run of an isolated home; it has no
    # bearing on window ordering, so skip it.
    from ui import startup_splash

    startup_splash.create_startup_splash = lambda app: None
    bootstrap_application()
    app = QApplication.instance()
    if app is None:
        raise SystemExit("Qt 应用初始化失败")
    app.setQuitOnLastWindowClosed(False)
    apply_runtime_log_window_preference(force=False)

    window = MainWindow()
    window.show()
    window.start_post_show_tasks()

    tray = window.tray.tray_icon
    record(
        "菜单栏图标已创建",
        tray is not None and QSystemTrayIcon.isSystemTrayAvailable(),
        f"visible={bool(tray and tray.isVisible())}",
    )

    def after_ready() -> None:
        record("启动时主窗口可见", window.isVisible())
        actions = [a.text() for a in (tray.contextMenu().actions() if tray else [])]
        record("状态栏菜单包含退出项", any("退出" in text for text in actions))

        window.lifecycle.closeEvent(QCloseEvent())
        app.processEvents()
        record("关闭窗口后主窗口隐藏", not window.isVisible())
        record("关闭窗口后应用未退出", not window.lifecycle._force_exit)

        record("已置为后台状态", deactivate_application(), state_name())
        QTimer.singleShot(400, start_capture)

    def start_capture() -> None:
        record(
            "截图前应用处于后台",
            app.applicationState() != Qt.ApplicationState.ApplicationActive,
            state_name(),
        )

        capture = window.capture
        print(
            f"  [诊断] busy={capture.tasks.is_busy()} "
            f"can_capture={capture.can_capture()} "
            f"model={bool(getattr(capture.models, 'model', None))}",
            flush=True,
        )
        # The model gate is unrelated to window ordering; satisfy it so the
        # capture surface shows on a machine without installed models.
        if not getattr(capture.models, "model", None):
            capture.models = SimpleNamespace(model=object())
        # The first-run onboarding wizard is unrelated to window ordering; a
        # fresh isolated home always opens it.
        capture.can_capture = lambda: True
        capture.screenshot_provider.request_permission = lambda: PermissionResult(
            PermissionState.ALLOWED
        )

        capture.start_capture(preserve_pinned_result=True)
        probe = getattr(capture, "suppresses_activation", None)
        if callable(probe):
            record("后台状态抑制前台弹出", bool(probe()))
        QTimer.singleShot(700, after_capture_started)

    def after_capture_started() -> None:
        overlay = window.capture.overlay
        record("快捷键触发后出现截图界面", overlay is not None)
        drawn = onscreen_window_count()
        record("截图界面实际绘制在屏幕上", drawn > 0, f"onscreen={drawn}")
        record("截图期间主窗口保持隐藏", not window.isVisible())
        active = app.applicationState() == Qt.ApplicationState.ApplicationActive
        record("截图期间应用未抢占前台", not active, state_name())
        if overlay is not None:
            overlay.close()
        window.capture.overlay = None
        QTimer.singleShot(300, deliver_result)

    def deliver_result() -> None:
        # Feed a finished recognition through the real result path, exactly as
        # the recognition worker does after a capture.
        try:
            window.results.show_result("E = mc^2", "mathcraft", "mathcraft", 0.1)
        except Exception:
            import traceback

            traceback.print_exc()
            record("识别结果路径无异常", False)
        QTimer.singleShot(800, after_result)

    def after_result() -> None:
        dialog = getattr(window.results, "_predict_result_dialog", None)
        record(
            "识别后弹出结果窗口",
            bool(dialog is not None and dialog.isVisible()),
        )
        record("识别后主窗口保持隐藏", not window.isVisible())
        # Opening the main window on purpose must still work while the result
        # window is up: the menu bar item calls show_window directly.
        window.windows.show_window()
        app.processEvents()
        record("结果窗口打开时仍可主动打开主窗口", window.isVisible())
        window.lifecycle.closeEvent(QCloseEvent())
        app.processEvents()
        if dialog is not None:
            dialog.close()
        app.processEvents()
        record("关闭结果窗口后主窗口仍隐藏", not window.isVisible())
        # With no window left, an activation (Dock click) reopens the main window.
        window.lifecycle._reactivate_from_dock()
        app.processEvents()
        record("无其他窗口时点击 Dock 可恢复主窗口", window.isVisible())
        QTimer.singleShot(300, finish)

    def finish() -> None:
        actions = tray.contextMenu().actions() if tray else []
        quit_actions = [action for action in actions if "退出" in action.text()]
        if quit_actions:
            quit_actions[0].trigger()
            app.processEvents()
        record("状态栏退出可结束后台", bool(window.lifecycle._force_exit))

        failed = [name for name, ok, _ in results if not ok]
        print(f"\n{len(results) - len(failed)}/{len(results)} 项通过")
        if failed:
            print("未通过: " + ", ".join(failed))
        window.lifecycle._force_exit = True
        app.exit(1 if failed else 0)

    QTimer.singleShot(1200, after_ready)
    QTimer.singleShot(20000, lambda: app.exit(2))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

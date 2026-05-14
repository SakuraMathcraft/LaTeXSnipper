from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QIcon, QKeySequence
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from backend.capture_overlay import ScreenCaptureOverlay
from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig, TrayMenuHandlers
from backend.qhotkey import QHotkey


def _hidden_subprocess_kwargs() -> dict:
    import os as _os
    if _os.name != "nt":
        return {}
    kwargs: dict = {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def probe_local_device_names() -> tuple[str, str]:
    """Probe GPU and CPU names using PowerShell/WMI/nvidia-smi (Windows only).

    Returns (gpu_name, cpu_name).  Both may be empty strings.
    """
    gpu_name = ""
    cpu_name = ""

    def _run_ps(cmd: str) -> str:
        try:
            res = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5,
                **_hidden_subprocess_kwargs(),
            )
            lines = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
            return lines[0] if lines else ""
        except Exception:
            return ""

    gpu_name = _run_ps(
        "(Get-WmiObject Win32_VideoController | "
        "Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | "
        "Select-Object -First 1 -ExpandProperty Name)"
    )
    if not gpu_name:
        gpu_name = _run_ps(
            "(Get-CimInstance Win32_VideoController | "
            "Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | "
            "Select-Object -First 1 -ExpandProperty Name)"
        )
    if not gpu_name:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=3,
                **_hidden_subprocess_kwargs(),
            )
            names = [line.strip() for line in (res.stdout or "").splitlines() if line.strip()]
            gpu_name = names[0] if names else ""
        except Exception:
            gpu_name = ""

    cpu_name = _run_ps(
        "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"
    )
    if not cpu_name:
        cpu_name = _run_ps(
            "(Get-WmiObject Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"
        )

    return gpu_name, cpu_name


class WindowsHotkeyProvider(QObject):
    """Windows hotkey provider (strict global hotkey path)."""

    def __init__(self, parent=None, global_enabled: bool = True):
        super().__init__(parent)
        self._global_enabled = bool(global_enabled)
        self._hotkey = QHotkey(parent=self) if self._global_enabled else None

    @property
    def activated(self):
        return self._hotkey.activated if self._hotkey else None

    def register(self, seq: str) -> None:
        if not self._hotkey:
            raise RuntimeError("global hotkey disabled")
        self._hotkey.setShortcut(QKeySequence(seq))
        self._hotkey.register()

    def is_registered(self) -> bool:
        if not self._hotkey:
            return False
        try:
            return bool(self._hotkey.is_registered())
        except Exception:
            return False

    def cleanup(self) -> None:
        try:
            if self._hotkey:
                self._hotkey.cleanup()
        except Exception:
            pass


class WindowsScreenshotProvider:
    """Windows screenshot provider with overlay adapter."""

    def request_permission(self) -> PermissionResult:
        # Windows does not require explicit runtime prompt for this capture path.
        return PermissionResult(PermissionState.ALLOWED, "windows-default-allowed")

    def create_overlay(self, cfg: ScreenshotConfig) -> ScreenCaptureOverlay:
        return ScreenCaptureOverlay(
            capture_display_mode=cfg.capture_display_mode,
            preferred_screen_index=cfg.preferred_screen_index,
        )


class WindowsSystemProvider:
    """Windows system integration provider."""

    def create_tray(self, icon: QIcon, parent=None) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icon, parent)
        tray.setContextMenu(QMenu())
        tray.show()
        return tray

    def set_tray_tooltip(self, tray: QSystemTrayIcon, text: str) -> None:
        if tray:
            tray.setToolTip(text)

    def update_tray_menu(self, tray: QSystemTrayIcon, hotkey: str, handlers: TrayMenuHandlers) -> None:
        if not tray:
            return
        tray_menu = QMenu()
        tray_menu.setObjectName("latexsnipperTrayMenu")
        tray_menu.setStyleSheet(
            "QMenu#latexsnipperTrayMenu{padding:4px;}"
            "QMenu#latexsnipperTrayMenu::item{padding:4px 18px 4px 8px;}"
            "QMenu#latexsnipperTrayMenu::item:selected{background-color:rgba(127,127,127,48);border-radius:4px;}"
            "QMenu#latexsnipperTrayMenu::item:pressed{background-color:rgba(127,127,127,64);border-radius:4px;}"
            "QMenu#latexsnipperTrayMenu::icon{width:0px;height:0px;margin:0px;padding:0px;}"
            "QMenu#latexsnipperTrayMenu::indicator{width:0px;height:0px;margin:0px;padding:0px;}"
        )
        tray_menu.addAction("打开主窗口", handlers.on_open)
        tray_menu.addAction(f"截图识别（{hotkey}）", handlers.on_capture)
        if callable(handlers.build_capture_submenu):
            handlers.build_capture_submenu(tray_menu)
        tray_menu.addAction("退出", handlers.on_exit)
        tray.setContextMenu(tray_menu)

    def show_notification(self, tray: QSystemTrayIcon, title: str, text: str, critical: bool = False, timeout_ms: int = 2500) -> None:
        if not tray:
            return
        icon = QSystemTrayIcon.MessageIcon.Critical if critical else QSystemTrayIcon.MessageIcon.Information
        tray.showMessage(title, text, icon, timeout_ms)

    def activate_window(self, window) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


class PermissionState(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNKNOWN = "unknown"


@dataclass
class PermissionResult:
    state: PermissionState
    message: str = ""


@dataclass
class ScreenshotConfig:
    capture_display_mode: str = "auto"
    preferred_screen_index: int | None = 0
    screenshot_tool: str | None = None


@dataclass
class TrayMenuHandlers:
    on_open: Callable[[], None]
    on_capture: Callable[[], None]
    on_exit: Callable[[], None]
    build_capture_submenu: Callable[[QMenu], None] | None = None


class IHotkeyProvider(Protocol):
    @property
    def activated(self):
        ...

    def register(self, seq: str) -> None:
        ...

    def is_registered(self) -> bool:
        ...

    def cleanup(self) -> None:
        ...


class IScreenshotProvider(Protocol):
    def request_permission(self) -> PermissionResult:
        ...

    def create_overlay(self, cfg: ScreenshotConfig):
        ...


class ISystemProvider(Protocol):
    def create_tray(self, icon: QIcon, parent=None) -> QSystemTrayIcon:
        ...

    def set_tray_tooltip(self, tray: QSystemTrayIcon, text: str) -> None:
        ...

    def update_tray_menu(
        self,
        tray: QSystemTrayIcon,
        hotkey: str,
        handlers: TrayMenuHandlers,
    ) -> None:
        ...

    def show_notification(
        self,
        tray: QSystemTrayIcon,
        title: str,
        text: str,
        critical: bool = False,
        timeout_ms: int = 2500,
    ) -> None:
        ...

    def activate_window(self, window) -> None:
        ...

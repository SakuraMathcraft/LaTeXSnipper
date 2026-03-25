from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


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
    remember_last_screen: bool = True
    on_screen_selected: Callable[[int], None] | None = None


class IHotkeyProvider(Protocol):
    def register(self, seq: str) -> None:
        ...

    def is_registered(self) -> bool:
        ...

    def cleanup(self) -> None:
        ...


class IScreenshotProvider(Protocol):
    def request_permission(self) -> PermissionResult:
        ...


class ISystemProvider(Protocol):
    def activate_window(self, window) -> None:
        ...

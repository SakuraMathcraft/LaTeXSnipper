from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig
from backend.platform.registry import PlatformCapabilityRegistry, PlatformProviders, TrayMenuHandlers
from backend.platform.linux_provider import (
    LinuxHotkeyProvider,
    LinuxScreenshotProvider,
    LinuxSystemProvider,
)

__all__ = [
    "PermissionResult",
    "PermissionState",
    "ScreenshotConfig",
    "PlatformCapabilityRegistry",
    "PlatformProviders",
    "TrayMenuHandlers",
    "LinuxHotkeyProvider",
    "LinuxScreenshotProvider",
    "LinuxSystemProvider",
]

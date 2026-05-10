from backend.platform.protocols import PermissionResult, PermissionState, ScreenshotConfig
from backend.platform.registry import PlatformCapabilityRegistry, PlatformProviders, TrayMenuHandlers
from backend.platform.linux_provider import (
    LinuxHotkeyProvider,
    LinuxScreenshotProvider,
    LinuxSystemProvider,
)
from backend.platform.macos_provider import (
    MacOSHotkeyProvider,
    MacOSScreenshotProvider,
    MacOSSystemProvider,
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
    "MacOSHotkeyProvider",
    "MacOSScreenshotProvider",
    "MacOSSystemProvider",
]

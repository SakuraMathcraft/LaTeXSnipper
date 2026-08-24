from platform_services.protocols import PermissionResult, PermissionState, ScreenshotConfig
from platform_services.registry import ApplicationMenuHandlers, PlatformCapabilityRegistry, PlatformProviders, TrayMenuHandlers
from platform_services.linux_provider import (
    LinuxHotkeyProvider,
    LinuxScreenshotProvider,
    LinuxSystemProvider,
)
from platform_services.macos_provider import (
    MacOSHotkeyProvider,
    MacOSScreenshotProvider,
    MacOSSystemProvider,
)

__all__ = [
    "PermissionResult",
    "PermissionState",
    "ScreenshotConfig",
    "ApplicationMenuHandlers",
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

from __future__ import annotations

import sys
from dataclasses import dataclass

from backend.platform.protocols import (
    IHotkeyProvider,
    IScreenshotProvider,
    ISystemProvider,
    TrayMenuHandlers,
)
from backend.platform.windows_provider import (
    WindowsHotkeyProvider,
    WindowsScreenshotProvider,
    WindowsSystemProvider,
)
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


@dataclass
class PlatformProviders:
    hotkey: IHotkeyProvider
    screenshot: IScreenshotProvider
    system: ISystemProvider


class PlatformCapabilityRegistry:
    def __init__(self, parent=None, disable_global_hotkey: bool = False):
        self.parent = parent
        self.disable_global_hotkey = bool(disable_global_hotkey)

    def create(self) -> PlatformProviders:
        if sys.platform == "win32":
            hotkey = WindowsHotkeyProvider(
                parent=self.parent,
                global_enabled=(not self.disable_global_hotkey),
            )
            screenshot = WindowsScreenshotProvider()
            system = WindowsSystemProvider()
        elif sys.platform == "linux":
            hotkey = LinuxHotkeyProvider(
                parent=self.parent,
                global_enabled=(not self.disable_global_hotkey),
            )
            screenshot = LinuxScreenshotProvider()
            system = LinuxSystemProvider()
        elif sys.platform == "darwin":
            hotkey = MacOSHotkeyProvider(
                parent=self.parent,
                global_enabled=(not self.disable_global_hotkey),
            )
            screenshot = MacOSScreenshotProvider()
            system = MacOSSystemProvider()
        else:
            raise RuntimeError(f"Unsupported platform for providers: {sys.platform}")
        return PlatformProviders(hotkey=hotkey, screenshot=screenshot, system=system)


__all__ = ["PlatformCapabilityRegistry", "PlatformProviders", "TrayMenuHandlers"]

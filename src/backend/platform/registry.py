from __future__ import annotations

import sys
from dataclasses import dataclass, field

from backend.platform.windows_provider import (
    TrayMenuHandlers,
    WindowsHotkeyProvider,
    WindowsScreenshotProvider,
    WindowsSystemProvider,
)
from backend.platform.linux_provider import (
    LinuxHotkeyProvider,
    LinuxScreenshotProvider,
    LinuxSystemProvider,
)


@dataclass
class PlatformProviders:
    hotkey: object = field(default=None)
    screenshot: object = field(default=None)
    system: object = field(default=None)


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
        else:
            raise RuntimeError(f"Unsupported platform for providers: {sys.platform}")
        return PlatformProviders(hotkey=hotkey, screenshot=screenshot, system=system)


__all__ = ["PlatformCapabilityRegistry", "PlatformProviders", "TrayMenuHandlers"]

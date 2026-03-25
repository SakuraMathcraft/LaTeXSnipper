from __future__ import annotations

import sys
from dataclasses import dataclass

from backend.platform.windows_provider import (
    TrayMenuHandlers,
    WindowsHotkeyProvider,
    WindowsScreenshotProvider,
    WindowsSystemProvider,
)


@dataclass
class PlatformProviders:
    hotkey: WindowsHotkeyProvider
    screenshot: WindowsScreenshotProvider
    system: WindowsSystemProvider


class PlatformCapabilityRegistry:
    def __init__(self, parent=None, disable_global_hotkey: bool = False):
        self.parent = parent
        self.disable_global_hotkey = bool(disable_global_hotkey)

    def create(self) -> PlatformProviders:
        # V1 only provides a Windows implementation.
        if sys.platform != "win32":
            raise RuntimeError(f"Unsupported platform for V1 providers: {sys.platform}")
        hotkey = WindowsHotkeyProvider(
            parent=self.parent,
            global_enabled=(not self.disable_global_hotkey),
        )
        screenshot = WindowsScreenshotProvider()
        system = WindowsSystemProvider()
        return PlatformProviders(hotkey=hotkey, screenshot=screenshot, system=system)


__all__ = ["PlatformCapabilityRegistry", "PlatformProviders", "TrayMenuHandlers"]

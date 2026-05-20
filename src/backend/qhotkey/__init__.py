import sys

from typing import Any


def _select_provider(platform: str) -> tuple[type[Any], type[Any] | None]:
    if platform == "win32":
        from .qhotkey import GlobalHotkey, QHotkey

        return QHotkey, GlobalHotkey
    if platform == "darwin":
        from .qhotkey_macos import MacHotkey

        return MacHotkey, None

    from .qhotkey_linux import LinuxHotkey

    return LinuxHotkey, None


QHotkey, GlobalHotkey = _select_provider(sys.platform)

__all__ = ["QHotkey", "GlobalHotkey"]

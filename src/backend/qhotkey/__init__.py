import sys

if sys.platform == "win32":
    from .qhotkey import QHotkey, GlobalHotkey
elif sys.platform in ("linux", "darwin"):
    from .qhotkey_linux import LinuxHotkey as QHotkey
    GlobalHotkey = None  # type: ignore[assignment]
else:
    from .qhotkey_linux import LinuxHotkey as QHotkey
    GlobalHotkey = None  # type: ignore[assignment]

__all__ = ["QHotkey", "GlobalHotkey"]


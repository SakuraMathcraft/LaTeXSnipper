from __future__ import annotations

from collections.abc import Callable
import os


REQUIRED_LINUX_HOTKEY_MODULES = (
    "pynput",
    "pynput._util",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
    "pynput.keyboard",
    "pynput.keyboard._base",
    "pynput.keyboard._xorg",
    "pynput.mouse",
    "pynput.mouse._base",
    "pynput.mouse._xorg",
    "Xlib",
    "Xlib.X",
    "Xlib.XK",
    "Xlib.display",
    "Xlib.ext",
    "Xlib.ext.composite",
    "Xlib.ext.damage",
    "Xlib.ext.dpms",
    "Xlib.ext.ge",
    "Xlib.ext.nvcontrol",
    "Xlib.ext.randr",
    "Xlib.ext.record",
    "Xlib.ext.res",
    "Xlib.ext.screensaver",
    "Xlib.ext.security",
    "Xlib.ext.shape",
    "Xlib.ext.xfixes",
    "Xlib.ext.xinerama",
    "Xlib.ext.xinput",
    "Xlib.ext.xtest",
    "Xlib.keysymdef",
    "Xlib.keysymdef.apl",
    "Xlib.keysymdef.arabic",
    "Xlib.keysymdef.cyrillic",
    "Xlib.keysymdef.greek",
    "Xlib.keysymdef.hebrew",
    "Xlib.keysymdef.katakana",
    "Xlib.keysymdef.korean",
    "Xlib.keysymdef.latin1",
    "Xlib.keysymdef.latin2",
    "Xlib.keysymdef.latin3",
    "Xlib.keysymdef.latin4",
    "Xlib.keysymdef.miscellany",
    "Xlib.keysymdef.publishing",
    "Xlib.keysymdef.special",
    "Xlib.keysymdef.technical",
    "Xlib.keysymdef.thai",
    "Xlib.keysymdef.xf86",
    "Xlib.keysymdef.xk3270",
    "Xlib.keysymdef.xkb",
    "Xlib.protocol",
    "Xlib.protocol.rq",
    "Xlib.support",
    "Xlib.support.connect",
    "Xlib.support.lock",
    "Xlib.support.unix_connect",
    "Xlib.threaded",
)

PYNPUT_BACKEND_ENV_VARS = (
    "PYNPUT_BACKEND",
    "PYNPUT_BACKEND_KEYBOARD",
    "PYNPUT_BACKEND_MOUSE",
)


def collect_linux_hotkey_modules(
    collect_submodules: Callable[..., list[str]],
) -> list[str]:
    previous_backends = {
        name: os.environ.get(name) for name in PYNPUT_BACKEND_ENV_VARS
    }
    os.environ.update({name: "dummy" for name in PYNPUT_BACKEND_ENV_VARS})
    try:
        modules = collect_submodules("pynput", on_error="raise")
        modules += collect_submodules("Xlib", on_error="raise")
    finally:
        for name, previous_value in previous_backends.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value

    modules = sorted(set(modules))
    missing = sorted(set(REQUIRED_LINUX_HOTKEY_MODULES).difference(modules))
    if missing:
        raise RuntimeError(
            "Failed to collect required Linux hotkey modules: "
            + ", ".join(missing)
        )
    return modules

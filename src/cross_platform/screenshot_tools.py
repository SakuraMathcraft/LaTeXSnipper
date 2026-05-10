"""Platform screenshot fallbacks used by the capture overlay.

Qt's root-window capture is still the primary path.  This module contains the
Linux and macOS command-line fallbacks plus Wayland portal capture, with Qt
imports delayed until a screenshot is actually needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

LINUX_SCREENSHOT_TOOLS: dict[str, dict] = {
    "maim": {
        "cmds": [["maim", "-x", "{x}", "-y", "{y}", "-w", "{w}", "-h", "{h}", "{output}"]],
        "desc": "maim (X11, 不包含光标)",
        "env": "x11",
    },
    "import": {
        "cmds": [["import", "-window", "root", "-crop", "{w}x{h}+{x}+{y}", "{output}"]],
        "desc": "ImageMagick import (X11)",
        "env": "x11",
    },
    "scrot": {
        "cmds": [["scrot", "-a", "{x},{y},{w},{h}", "-o", "{output}"]],
        "desc": "scrot (X11)",
        "env": "x11",
    },
    "gnome-screenshot": {
        "cmds": [
            ["gnome-screenshot", "-a", "-f", "{output}"],
            ["gnome-screenshot", "-f", "{output}"],
        ],
        "desc": "gnome-screenshot (GNOME 桌面)",
        "env": "any",
    },
    "flameshot": {
        "cmds": [["flameshot", "full", "-r", "{output}"]],
        "desc": "flameshot (全屏截图)",
        "env": "any",
    },
    "spectacle": {
        "cmds": [["spectacle", "-b", "-r", "-o", "{output}"]],
        "desc": "spectacle (KDE 桌面)",
        "env": "any",
    },
    "xdotool": {
        "cmds": [["import", "-window", "root", "-crop", "{w}x{h}+{x}+{y}", "{output}"]],
        "desc": "xdotool + ImageMagick (X11)",
        "env": "x11",
        "requires": ["import"],
    },
    "grim": {
        "cmds": [["grim", "-g", "{x},{y} {w}x{h}", "{output}"]],
        "desc": "grim (wlroots/Sway Wayland)",
        "env": "wayland",
    },
    "screencapture": {
        "cmds": [["screencapture", "-R", "{x},{y},{w},{h}", "-t", "png", "{output}"]],
        "desc": "screencapture (macOS 内置)",
        "env": "macos",
    },
}


def detect_display_env() -> str:
    """Return the active display environment."""
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def is_wayland() -> bool:
    """Return True for Wayland sessions."""
    return bool(
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


def is_image_effectively_black(image) -> bool:
    """Return True when an image is empty or close to all-black.

    Wayland root-window captures can produce a non-null black image.  Overlay
    code uses this to reject that capture and continue to CLI/portal fallback.
    """
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        return True
    width, height = image.width(), image.height()
    sample_points = [
        (2, 2),
        (width - 3, 2),
        (2, height - 3),
        (width - 3, height - 3),
        (width // 2, height // 2),
    ]
    dark_threshold = 8
    for sx, sy in sample_points:
        x = max(0, min(sx, width - 1))
        y = max(0, min(sy, height - 1))
        color = image.pixelColor(x, y)
        if (
            color.red() > dark_threshold
            or color.green() > dark_threshold
            or color.blue() > dark_threshold
        ):
            return False
    return True


def list_available_tools() -> list[str]:
    """Return installed screenshot tools usable in the current display environment."""
    env = detect_display_env()
    available = []
    for name, info in LINUX_SCREENSHOT_TOOLS.items():
        tool_env = info.get("env", "any")
        if tool_env not in (env, "any"):
            continue
        main_tool = info["cmds"][0][0] if info["cmds"] else name
        if not shutil.which(main_tool):
            continue
        requires = info.get("requires", [])
        if requires and not all(shutil.which(r) for r in requires):
            continue
        available.append(name)
    return available


def find_screenshot_tool(preferred: str | None = None) -> str | None:
    """Return the best available screenshot tool for the current environment."""
    available = list_available_tools()

    if preferred and preferred in available:
        return preferred

    if not available:
        return None

    env = detect_display_env()
    if env == "macos":
        priority = ["screencapture"]
    elif env == "wayland":
        priority = ["gnome-screenshot", "flameshot", "spectacle", "grim", "maim", "import", "scrot"]
    else:
        priority = ["maim", "import", "scrot", "gnome-screenshot", "flameshot", "spectacle", "grim"]

    for tool in priority:
        if tool in available:
            return tool
    return available[0]


def _try_screenshot_cmd(
    cmd_template: list[str],
    x: int, y: int, width: int, height: int,
):
    """Run one screenshot command template and return a QImage or None."""
    from PyQt6.QtGui import QImage

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="latexsnipper_cap_")
        os.close(fd)

        cmd = [
            str(arg).format(x=x, y=y, w=width, h=height, output=tmp_path)
            for arg in cmd_template
        ]

        subprocess.run(
            cmd, timeout=15, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        image = QImage(tmp_path)
        if image.isNull():
            return None

        tool_name = cmd_template[0] if cmd_template else ""
        if tool_name in ("flameshot", "gnome-screenshot", "spectacle"):
            if image.width() > width or image.height() > height:
                cropped = image.copy(
                    x % max(1, image.width()),
                    y % max(1, image.height()),
                    min(width, image.width()),
                    min(height, image.height()),
                )
                return cropped

        return image.copy()
    except Exception:
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _capture_region_with_cli_tools(
    x: int, y: int, width: int, height: int,
    preferred_tool: str | None = None,
):
    """Capture a region with command-line tools and return ``(image, tool_name)``."""
    tool = find_screenshot_tool(preferred=preferred_tool)

    tools_to_try: list[str] = []
    if tool:
        tools_to_try.append(tool)
    for t in list_available_tools():
        if t not in tools_to_try:
            tools_to_try.append(t)

    for tool_name in tools_to_try:
        info = LINUX_SCREENSHOT_TOOLS.get(tool_name)
        if info is None:
            continue

        for cmd_template in info["cmds"]:
            result = _try_screenshot_cmd(cmd_template, x, y, width, height)
            if result is not None:
                return result, tool_name

    return None, ""


def wayland_overlay_background():
    """Capture a full-screen Wayland background image for the overlay."""
    from PyQt6.QtGui import QImage

    portal_img = wayland_screenshot_via_portal()
    if portal_img is not None and not portal_img.isNull():
        return portal_img

    for tool_name in ("gnome-screenshot", "grim"):
        tool_path = shutil.which(tool_name)
        if not tool_path:
            continue
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="latexsnipper_bg_")
            os.close(fd)
            cmd = [tool_path, "-f", tmp_path] if tool_name == "gnome-screenshot" else [tool_path, tmp_path]
            subprocess.run(
                cmd,
                timeout=10,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            image = QImage(tmp_path)
            if not image.isNull():
                return image.copy()
        except Exception:
            continue
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
    return None


def capture_region_with_tools(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    preferred_tool: str | None = None,
    screen_geometry: tuple[int, int, int, int] | None = None,
):
    """Capture a region using platform CLI/portal fallback paths.

    Returns ``(image, source_label)``.  ``image`` is a QImage or None.
    """
    cli_img, source = _capture_region_with_cli_tools(
        x,
        y,
        width,
        height,
        preferred_tool=preferred_tool,
    )
    if cli_img is not None and not cli_img.isNull():
        return cli_img, source or "cli"

    if not is_wayland():
        return None, ""

    wayland_img = wayland_screenshot_via_portal()
    if wayland_img is None or wayland_img.isNull():
        return None, ""

    if screen_geometry is None:
        cropped = wayland_img.copy(x, y, min(width, wayland_img.width() - x), min(height, wayland_img.height() - y))
        return cropped, "xdg-desktop-portal"

    sx, sy, sw, sh = screen_geometry
    scale_x = wayland_img.width() / max(1, sw)
    scale_y = wayland_img.height() / max(1, sh)
    crop_x = max(0, int((x - sx) * scale_x))
    crop_y = max(0, int((y - sy) * scale_y))
    crop_w = max(1, int(width * scale_x))
    crop_h = max(1, int(height * scale_y))
    crop_w = min(crop_w, max(0, wayland_img.width() - crop_x))
    crop_h = min(crop_h, max(0, wayland_img.height() - crop_y))
    if crop_w <= 0 or crop_h <= 0:
        return None, ""
    return wayland_img.copy(crop_x, crop_y, crop_w, crop_h), "xdg-desktop-portal"

def wayland_screenshot_via_portal():
    """Capture through org.freedesktop.portal.Screenshot on Wayland."""
    from PyQt6.QtGui import QImage

    try:
        import dbus  # type: ignore[reportMissingImports]
        from dbus.mainloop.glib import DBusGMainLoop  # type: ignore[reportMissingImports]
    except ImportError:
        return None

    try:
        from gi.repository import GLib  # type: ignore
    except ImportError:
        return None

    loop = GLib.MainLoop()
    result: dict = {}

    def _on_response(response: int, results: dict) -> None:
        result["response"] = response
        result["results"] = results
        loop.quit()

    try:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        )
        screenshot = dbus.Interface(
            portal,
            "org.freedesktop.portal.Screenshot",
        )
        screenshot.connect_to_signal("Response", _on_response)

        screenshot.Screenshot(
            "",
            {"interactive": False, "modal": False},
        )

        GLib.timeout_add(10000, loop.quit)
        loop.run()
    except Exception:
        return None

    if result.get("response") != 0:
        return None

    uri = result.get("results", {}).get("uri", "")
    if not uri:
        return None

    path = uri.replace("file://", "")
    image = QImage(path)
    if image.isNull():
        return None

    try:
        os.unlink(path)
    except OSError:
        pass

    return image

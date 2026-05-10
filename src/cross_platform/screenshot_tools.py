# cross_platform/screenshot_tools.py
"""跨平台截图工具检测与截图函数。

将原先散布在 backend/capture_overlay.py 的截图相关逻辑统一到这里。

模块分为两层：
- 工具层（零外部依赖）：注册表、可用性检测、显示环境探测。
- Qt 层（QImage）：CLI 截图函数和 Wayland portal，延迟导入 Qt。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

# ============================================================================
# 工具注册表
# ============================================================================

# 已知的截图工具及其命令行参数模板。
# 参数模板中 {x} {y} {w} {h} {output} 会被替换为实际值。
LINUX_SCREENSHOT_TOOLS: dict[str, dict] = {
    # ---- X11 工具 ----
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
    # ---- Wayland 工具 ----
    "grim": {
        "cmds": [["grim", "-g", "{x},{y} {w}x{h}", "{output}"]],
        "desc": "grim (wlroots/Sway Wayland)",
        "env": "wayland",
    },
    # ---- macOS 工具 ----
    "screencapture": {
        "cmds": [["screencapture", "-R", "{x},{y},{w},{h}", "-t", "png", "{output}"]],
        "desc": "screencapture (macOS 内置)",
        "env": "macos",
    },
}

# ============================================================================
# 环境探测
# ============================================================================


def detect_display_env() -> str:
    """检测当前桌面环境类型: 'wayland' | 'x11' | 'macos' | 'unknown'."""
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def is_wayland() -> bool:
    """检查当前是否为 Wayland 会话。"""
    return bool(
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


# ============================================================================
# 工具可用性检测
# ============================================================================


def list_available_tools() -> list[str]:
    """列出当前系统中已安装的所有截图工具。"""
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
    """查找可用的截图工具。

    Args:
        preferred: 用户偏好的工具名。如果指定且已安装则优先使用。

    Returns:
        工具名，未找到返回 None。
    """
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


# ============================================================================
# Qt 截图函数（延迟导入 QImage）
# ============================================================================


def _try_screenshot_cmd(
    cmd_template: list[str],
    x: int, y: int, width: int, height: int,
):
    """尝试执行单个截图命令模板。返回 QImage 或 None。"""
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


def linux_cli_screenshot_region(
    x: int, y: int, width: int, height: int,
    preferred_tool: str | None = None,
):
    """使用命令行工具截取屏幕区域。返回 QImage 或 None。"""
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
                return result

    return None


def test_screenshot_tool(tool_name: str) -> dict:
    """测试指定截图工具是否可用。

    Returns:
        {"ok": bool, "message": str, "image_path": str|None}
    """
    from PyQt6.QtGui import QImage

    info = LINUX_SCREENSHOT_TOOLS.get(tool_name)
    if info is None:
        return {"ok": False, "message": f"未知工具: {tool_name}", "image_path": None}

    main_tool = info["cmds"][0][0] if info["cmds"] else tool_name
    if not shutil.which(main_tool):
        requires = info.get("requires", [])
        missing = [r for r in requires if not shutil.which(r)]
        if missing:
            return {"ok": False, "message": f"缺少依赖: {', '.join(missing)}", "image_path": None}
        return {"ok": False, "message": f"未安装: {main_tool}", "image_path": None}

    tmp_path = None
    for cmd_template in info["cmds"]:
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="latexsnipper_test_")
            os.close(fd)
            cmd = [
                str(arg).format(x=0, y=0, w=100, h=100, output=tmp_path)
                for arg in cmd_template
            ]
            subprocess.run(
                cmd, timeout=10, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            img = QImage(tmp_path)
            if not img.isNull():
                return {
                    "ok": True,
                    "message": f"{tool_name} 测试成功 ({img.width()}x{img.height()})",
                    "image_path": None,
                }
        except Exception:
            continue
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                tmp_path = None

    return {"ok": False, "message": f"{tool_name} 执行失败", "image_path": None}


def wayland_screenshot_via_portal():
    """通过 org.freedesktop.portal.Screenshot 在 Wayland 上截图。返回 QImage 或 None。"""
    from PyQt6.QtGui import QImage

    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
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


def wayland_overlay_background() -> object | None:
    """Wayland: 获取全屏截图作为 overlay 背景。

    按优先级尝试：D-Bus portal → gnome-screenshot → grim。
    返回 QImage 或 None。为避免 capture_overlay 的静态依赖，
    此处返回类型标注为 object | None。
    """
    from PyQt6.QtGui import QImage

    # 1) D-Bus Screenshot portal（跨合成器通用，GNOME/KDE 均支持）
    portal_img = wayland_screenshot_via_portal()
    if portal_img is not None and not portal_img.isNull():
        print("[ScreenshotTools] Wayland: 使用 D-Bus Screenshot portal 作为 overlay 背景")
        return portal_img

    # 2) gnome-screenshot（GNOME 桌面）
    gnome_sc = shutil.which("gnome-screenshot")
    if gnome_sc:
        try:
            fd, tmp = tempfile.mkstemp(suffix=".png", prefix="latexsnipper_bg_")
            os.close(fd)
            subprocess.run(
                [gnome_sc, "-f", tmp], timeout=10, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            img = QImage(tmp)
            if not img.isNull():
                result = img.copy()
                os.unlink(tmp)
                print("[ScreenshotTools] Wayland: 使用 gnome-screenshot 作为 overlay 背景")
                return result
            os.unlink(tmp)
        except Exception:
            pass

    # 3) grim（wlroots 合成器：Sway/Hyprland）
    grim_bin = shutil.which("grim")
    if grim_bin:
        try:
            fd, tmp = tempfile.mkstemp(suffix=".png", prefix="latexsnipper_bg_")
            os.close(fd)
            subprocess.run(
                [grim_bin, tmp], timeout=10, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            img = QImage(tmp)
            if not img.isNull():
                result = img.copy()
                os.unlink(tmp)
                print("[ScreenshotTools] Wayland: 使用 grim 作为 overlay 背景")
                return result
            os.unlink(tmp)
        except Exception:
            pass

    return None


def wayland_capture_region(
    x: int, y: int, width: int, height: int,
    screen_geometry: tuple[int, int, int, int],
    preferred_tool: str | None = None,
) -> object | None:
    """Wayland: 截取屏幕区域。按 CLI 工具 → D-Bus portal 优先级回退。

    返回 QPixmap 或 None（空 QPixmap）。为避免 capture_overlay 的
    静态 Qt 依赖，返回类型标注为 object | None。
    """
    from PyQt6.QtGui import QPixmap

    # 1) 命令行截图工具（区域截图）
    cli_img = linux_cli_screenshot_region(x, y, width, height, preferred_tool=preferred_tool)
    if cli_img is not None and not cli_img.isNull():
        print(f"[ScreenshotTools] Wayland: 使用 CLI 截图工具 ({find_screenshot_tool(preferred=preferred_tool)})")
        return QPixmap.fromImage(cli_img)

    print("[ScreenshotTools] Wayland CLI 截图失败，尝试 D-Bus portal...")

    # 2) D-Bus Screenshot portal（跨合成器通用方案）
    wayland_img = wayland_screenshot_via_portal()
    if wayland_img is not None and not wayland_img.isNull():
        sx, sy, sw, sh = screen_geometry
        crop_x = max(0, int((x - sx) * (wayland_img.width() / max(1, sw))))
        crop_y = max(0, int((y - sy) * (wayland_img.height() / max(1, sh))))
        crop_w = max(1, int(width * (wayland_img.width() / max(1, sw))))
        crop_h = max(1, int(height * (wayland_img.height() / max(1, sh))))
        cropped = wayland_img.copy(
            crop_x, crop_y,
            min(crop_w, wayland_img.width() - crop_x),
            min(crop_h, wayland_img.height() - crop_y),
        )
        print("[ScreenshotTools] Wayland: 使用 D-Bus portal 裁剪截图")
        return QPixmap.fromImage(cropped)

    print("[ScreenshotTools] Wayland D-Bus portal 截图也失败")
    return None


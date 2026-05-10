# cross_platform/screenshot_tools.py
"""跨平台截图工具检测、注册与系统包管理。

将原先散布在 backend/capture_overlay.py（工具注册表、CLI 截图、
Wayland portal）和 bootstrap/deps_bootstrap.py（系统包安装/卸载）的
截图相关逻辑统一到这里。

模块分为两层：
- 工具层（零外部依赖）：注册表、可用性检测、显示环境探测。
- Qt 层（QImage）：CLI 截图函数和 Wayland portal，延迟导入 Qt。
- 包管理层：系统包管理器安装/卸载截图工具。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

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

# 截图工具到系统软件包的映射
SCREENSHOT_TOOL_PACKAGES: dict[str, str] = {
    "maim": "maim",
    "grim": "grim",
    "scrot": "scrot",
    "import": "imagemagick",
    "gnome-screenshot": "gnome-screenshot",
    "flameshot": "flameshot",
    "spectacle": "spectacle",
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


def get_screenshot_tools() -> list[str]:
    """返回当前桌面环境推荐的截图工具列表（按优先级排序）。"""
    if is_wayland():
        return ["grim", "gnome-screenshot", "flameshot", "spectacle", "maim", "scrot", "import"]
    return ["maim", "import", "scrot", "gnome-screenshot", "flameshot", "spectacle", "grim"]


def is_any_screenshot_tool_installed() -> bool:
    """检查是否有任一截图工具已安装。"""
    return any(shutil.which(t) for t in SCREENSHOT_TOOL_PACKAGES)


def list_installed_screenshot_tools() -> list[str]:
    """列出当前已安装的截图工具。"""
    return [t for t in SCREENSHOT_TOOL_PACKAGES if shutil.which(t)]


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


# ============================================================================
# 系统包管理
# ============================================================================


def detect_package_manager() -> str | None:
    """检测可用的系统包管理器。"""
    for pm in ("apt-get", "dnf", "yum", "pacman", "zypper"):
        if shutil.which(pm):
            return pm
    return None


def _build_install_cmd(package_manager: str, pkg_name: str) -> list[str]:
    """构建安装命令。"""
    if package_manager in ("apt-get", "apt"):
        return [package_manager, "install", "-y", pkg_name]
    if package_manager in ("dnf", "yum"):
        return [package_manager, "install", "-y", pkg_name]
    if package_manager == "pacman":
        return [package_manager, "-S", "--noconfirm", pkg_name]
    if package_manager == "zypper":
        return [package_manager, "install", "-y", pkg_name]
    return []


def _build_uninstall_cmd(package_manager: str, pkg_name: str) -> list[str]:
    """构建卸载命令。"""
    if package_manager in ("apt-get", "apt"):
        return [package_manager, "remove", "-y", pkg_name]
    if package_manager in ("dnf", "yum"):
        return [package_manager, "remove", "-y", pkg_name]
    if package_manager == "pacman":
        return [package_manager, "-R", "--noconfirm", pkg_name]
    if package_manager == "zypper":
        return [package_manager, "remove", "-y", pkg_name]
    return []


def _run_with_privilege(cmd: list[str], log_fn: Callable[[str], None] | None = None) -> bool:
    """尝试使用多种提权方式运行命令。"""
    if shutil.which("sudo"):
        try:
            env = os.environ.copy()
            env.setdefault("DEBIAN_FRONTEND", "noninteractive")
            result = subprocess.run(
                ["sudo"] + cmd, capture_output=True, text=True, timeout=120, env=env,
            )
            if result.returncode == 0:
                if log_fn:
                    log_fn(f"[SCREENSHOT] sudo 执行成功: {' '.join(cmd[:3])}")
                return True
        except Exception:
            pass

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            if log_fn:
                log_fn(f"[SCREENSHOT] 直接执行成功: {' '.join(cmd[:3])}")
            return True
    except Exception:
        pass

    return False


def install_screenshot_tools(log_fn: Callable[[str], None] | None = None) -> bool:
    """安装 Linux 截图工具。至少安装成功一个即视为成功。"""
    if is_any_screenshot_tool_installed():
        installed = list_installed_screenshot_tools()
        if log_fn:
            log_fn(f"[SCREENSHOT] 已有可用工具: {', '.join(installed)}，跳过安装")
        return True

    pm = detect_package_manager()
    if not pm:
        if log_fn:
            log_fn("[SCREENSHOT] 未找到系统包管理器，请手动安装截图工具")
            log_fn("[SCREENSHOT] 推荐: sudo apt install maim grim flameshot")
        return False

    if log_fn:
        log_fn(f"[SCREENSHOT] 包管理器: {pm}，按优先级尝试安装截图工具...")

    tools = get_screenshot_tools()
    installed_any = False

    for tool in tools:
        pkg = SCREENSHOT_TOOL_PACKAGES.get(tool)
        if not pkg:
            continue

        if shutil.which(tool):
            installed_any = True
            if log_fn:
                log_fn(f"[SCREENSHOT] {tool} 已就绪 ✓")
            continue

        cmd = _build_install_cmd(pm, pkg)
        if not cmd:
            continue

        if log_fn:
            log_fn(f"[SCREENSHOT] 尝试安装 {tool} (包: {pkg})...")

        if _run_with_privilege(cmd, log_fn=log_fn):
            if shutil.which(tool):
                installed_any = True
                if log_fn:
                    log_fn(f"[SCREENSHOT] {tool} 安装成功 ✅")
                continue

        if log_fn:
            log_fn(f"[SCREENSHOT] {tool} 安装失败，尝试下一个...")

    if installed_any:
        if log_fn:
            log_fn("[SCREENSHOT] 截图工具安装完成 ✅")
        return True

    if log_fn:
        log_fn("[SCREENSHOT] 所有自动安装方式均失败，尝试终端安装...")
    for terminal in ("x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "lxterminal", "xterm"):
        term = shutil.which(terminal)
        if not term:
            continue
        pkgs = " ".join(SCREENSHOT_TOOL_PACKAGES.get(t, t) for t in tools[:3])
        try:
            subprocess.run(
                [term, "-e", f"sudo {pm} install -y {pkgs}; echo '按 Enter 关闭...'; read"],
                timeout=180,
            )
            if is_any_screenshot_tool_installed():
                if log_fn:
                    log_fn("[SCREENSHOT] 截图工具安装完成 ✅ (终端)")
                return True
            break
        except Exception:
            continue

    if log_fn:
        log_fn("[SCREENSHOT] 截图工具安装失败，请手动安装:")
        log_fn(f"[SCREENSHOT]   sudo {pm} install maim grim flameshot imagemagick")
    return False


def uninstall_screenshot_tools(log_fn: Callable[[str], None] | None = None) -> bool:
    """卸载所有通过系统包管理器安装的截图工具。"""
    installed = list_installed_screenshot_tools()
    if not installed:
        if log_fn:
            log_fn("[SCREENSHOT] 未检测到截图工具，跳过卸载")
        return True

    pm = detect_package_manager()
    if not pm:
        if log_fn:
            log_fn(f"[SCREENSHOT] 未找到包管理器，请手动卸载: {', '.join(installed)}")
        return False

    if log_fn:
        log_fn(f"[SCREENSHOT] 将卸载以下截图工具: {', '.join(installed)}")

    all_ok = True
    for tool in installed:
        pkg = SCREENSHOT_TOOL_PACKAGES.get(tool, tool)
        cmd = _build_uninstall_cmd(pm, pkg)
        if not cmd:
            continue

        if log_fn:
            log_fn(f"[SCREENSHOT] 正在卸载 {tool} (包: {pkg})...")

        if _run_with_privilege(cmd, log_fn=log_fn):
            if log_fn:
                log_fn(f"[SCREENSHOT] {tool} 已卸载 ✅")
        else:
            all_ok = False
            if log_fn:
                log_fn(f"[SCREENSHOT] {tool} 卸载失败，请手动执行: sudo {pm} remove {pkg}")

    if all_ok:
        if log_fn:
            log_fn("[SCREENSHOT] 截图工具卸载完成 ✅")
    else:
        if log_fn:
            log_fn("[SCREENSHOT] 部分工具卸载失败（可能需要 sudo 权限）")

    return all_ok


def verify_screenshot_layer(_pyexe: str = "", _timeout: int = 10) -> tuple[bool, str]:
    """验证 SCREENSHOT 层：检查是否有截图工具可用。"""
    if os.name == "nt":
        return True, ""
    if is_any_screenshot_tool_installed():
        installed = list_installed_screenshot_tools()
        return True, f"可用工具: {', '.join(installed)}"
    return False, "未安装截图工具，请通过依赖向导安装 SCREENSHOT 层"

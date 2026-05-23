"""Linux Qt graphics backend defaults."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path


_CHROMIUM_SOFTWARE_FLAGS = (
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--disable-accelerated-2d-canvas",
    "--disable-accelerated-video-decode",
    "--disable-vulkan",
    "--disable-features=UseOzonePlatform,Vulkan",
    "--in-process-gpu",
    "--use-gl=swiftshader",
)


def _append_unique_flags(existing: str, flags: tuple[str, ...]) -> str:
    parts = existing.split()
    seen = set(parts)
    for flag in flags:
        if flag not in seen:
            parts.append(flag)
            seen.add(flag)
    return " ".join(parts)


def _env_is_wayland(env: MutableMapping[str, str]) -> bool:
    return bool(env.get("WAYLAND_DISPLAY")) or env.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def _has_dri_render_node() -> bool:
    try:
        return any(Path("/dev/dri").glob("renderD*"))
    except Exception:
        return False


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _glx_is_available() -> bool:
    """Check whether GLX (libGL.so) can be loaded at all.

    On headless / GPU-less systems (e.g. VMs, containers, WSL)
    libGL.so may be missing entirely, in which case Qt6 xcb will
    abort during GLX initialisation even when QT_OPENGL=software.
    """
    for soname in ("libGL.so.1", "libGL.so", "libGLX.so.0", "libGLX.so"):
        try:
            ctypes.CDLL(soname, mode=ctypes.RTLD_LAZY | ctypes.RTLD_LOCAL)
            return True
        except OSError:
            continue
    return False


def _looks_virtualized() -> bool:
    marker_text = "\n".join(
        [
            _read_text("/sys/class/dmi/id/product_name"),
            _read_text("/sys/class/dmi/id/sys_vendor"),
            _read_text("/proc/sys/kernel/osrelease"),
        ]
    ).lower()
    markers = (
        "virtualbox",
        "vmware",
        "kvm",
        "qemu",
        "bochs",
        "hyper-v",
        "hyperv",
        "parallels",
        "virtual machine",
        "microsoft",
        "wsl",
    )
    return any(marker in marker_text for marker in markers)


def _needs_graphics_fallback(env: MutableMapping[str, str]) -> bool:
    if env.get("LATEXSNIPPER_FORCE_LINUX_GRAPHICS_FALLBACKS") == "1":
        return True
    if _env_is_wayland(env):
        return True
    if _looks_virtualized():
        return True
    if not _has_dri_render_node():
        return True
    # Even with a DRI node, if GLX itself is missing Qt6 xcb will abort.
    if env.get("DISPLAY") and not _glx_is_available():
        return True
    return False


def apply_linux_graphics_fallbacks(env: MutableMapping[str, str] | None = None) -> None:
    """Prefer robust software rendering only for high-risk Linux graphics sessions."""
    if not sys.platform.startswith("linux"):
        return

    target = os.environ if env is None else env
    if target.get("LATEXSNIPPER_DISABLE_LINUX_GRAPHICS_FALLBACKS") == "1":
        return

    if not _needs_graphics_fallback(target):
        return

    if "QT_QPA_PLATFORM" not in target and target.get("DISPLAY"):
        target["QT_QPA_PLATFORM"] = "xcb"

    # When GLX is absent, tell the xcb platform plugin to skip GL
    # initialisation entirely, otherwise Qt6 will abort even with
    # QT_OPENGL=software set.
    if not _glx_is_available():
        target.setdefault("QT_XCB_GL_INTEGRATION", "none")

    target.setdefault("QT_OPENGL", "software")
    target.setdefault("QSG_RHI_BACKEND", "software")
    target.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    target["QTWEBENGINE_CHROMIUM_FLAGS"] = _append_unique_flags(
        target.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
        _CHROMIUM_SOFTWARE_FLAGS,
    )

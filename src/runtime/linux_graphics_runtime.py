"""Linux Qt graphics backend defaults."""

from __future__ import annotations

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
    return _env_is_wayland(env) or _looks_virtualized() or not _has_dri_render_node()


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

    target.setdefault("QT_OPENGL", "software")
    target.setdefault("QSG_RHI_BACKEND", "software")
    target.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    target["QTWEBENGINE_CHROMIUM_FLAGS"] = _append_unique_flags(
        target.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
        _CHROMIUM_SOFTWARE_FLAGS,
    )

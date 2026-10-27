"""Native screenshot interfaces used by the capture overlay."""

from __future__ import annotations

import logging
import os
import uuid

from runtime.app_paths import APP_DESKTOP_ID

logger = logging.getLogger(f"latexsnipper.{__name__}")


def is_wayland() -> bool:
    return bool(
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("XDG_SESSION_TYPE") == "wayland"
    )


def wayland_screenshot_via_portal():
    """Capture through org.freedesktop.portal.Screenshot on Wayland."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QImage

    try:
        import dbus  # type: ignore[reportMissingImports]
        from dbus.mainloop.glib import (  # pyright: ignore[reportMissingImports]
            DBusGMainLoop,
        )
    except ImportError:
        return None

    try:
        from gi.repository import GLib  # type: ignore
    except ImportError:
        return None

    loop = GLib.MainLoop()
    result: dict = {}
    subscription = None
    timeout_id = None
    request = None
    bus = None

    def _on_response(response: int, results: dict) -> None:
        result["response"] = response
        result["results"] = results
        loop.quit()

    def _on_timeout() -> bool:
        nonlocal timeout_id
        timeout_id = None
        logger.warning("Wayland 截图授权超时（10 秒）")
        loop.quit()
        return False

    try:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus(private=True)
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        )
        dbus.Interface(portal, "org.freedesktop.host.portal.Registry").Register(
            APP_DESKTOP_ID, {}, timeout=5
        )
        token = "latexsnipper_" + uuid.uuid4().hex
        sender = bus.get_unique_name()[1:].replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        subscription = bus.add_signal_receiver(
            _on_response,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            bus_name="org.freedesktop.portal.Desktop",
            path=path,
        )
        screenshot = dbus.Interface(
            portal,
            "org.freedesktop.portal.Screenshot",
        )
        handle = screenshot.Screenshot(
            "",
            {"interactive": False, "modal": False, "handle_token": token},
            timeout=5,
        )
        request = dbus.Interface(
            bus.get_object("org.freedesktop.portal.Desktop", handle),
            "org.freedesktop.portal.Request",
        )
        if handle != path:
            raise RuntimeError("Unexpected screenshot request identity")
        timeout_id = GLib.timeout_add(10000, _on_timeout)
        if "response" not in result:
            loop.run()
    except Exception as exc:
        logger.warning("Wayland 截图 Portal 失败: %s", exc)
        return None
    finally:
        if subscription is not None:
            subscription.remove()
        if timeout_id is not None:
            GLib.source_remove(timeout_id)
        if request is not None and "response" not in result:
            try:
                request.Close(timeout=5)
            except Exception as exc:
                logger.warning("关闭截图 Portal 请求失败: %s", exc)
        if bus is not None:
            bus.close()

    if result.get("response") != 0:
        return None

    uri = result.get("results", {}).get("uri", "")
    if not uri:
        return None

    path = QUrl(str(uri)).toLocalFile()
    if not path:
        return None
    try:
        image = QImage(path)
        return image if not image.isNull() else None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

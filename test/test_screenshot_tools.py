"""Validate dark capture detection and the screenshot portal request lifecycle."""

import sys
from types import ModuleType, SimpleNamespace

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QImage

from capture.screenshot_tools import (
    is_image_effectively_black,
    wayland_screenshot_via_portal,
)


@pytest.mark.parametrize("point", [None, (0, 0), (20, 30), (99, 99)])
def test_black_capture_detection_preserves_sparse_bright_content(point):
    image = QImage(100, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    if point is not None:
        image.setPixelColor(*point, QColor("white"))
    assert is_image_effectively_black(image) == (point is None)


@pytest.mark.parametrize(
    "outcome", ["approved", "approved-early", "cancelled", "timeout"]
)
def test_portal_subscribes_before_request_and_cleans_up(tmp_path, monkeypatch, outcome):
    image_path = tmp_path / "截图 with spaces.png"
    image = QImage(3, 2, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    assert image.save(str(image_path))
    events = []
    state = {}

    class Loop:
        def run(self):
            assert outcome != "approved-early"
            if outcome == "timeout":
                state["timeout"]()
            else:
                state["response"](
                    1 if outcome == "cancelled" else 0,
                    {"uri": QUrl.fromLocalFile(str(image_path)).toString()},
                )

        def quit(self):
            events.append("quit")

    class Bus:
        def __init__(self, *, private):
            assert private

        def close(self):
            events.append("disconnect")

        def get_unique_name(self):
            return ":1.23"

        def get_object(self, name, path):
            assert name == "org.freedesktop.portal.Desktop"
            return path

        def add_signal_receiver(self, callback, **kwargs):
            assert kwargs["signal_name"] == "Response"
            assert kwargs["dbus_interface"] == "org.freedesktop.portal.Request"
            state["path"] = kwargs["path"]
            state["response"] = callback
            events.append("subscribe")
            return SimpleNamespace(remove=lambda: events.append("unsubscribe"))

    def interface(path, name):
        def screenshot(parent, options, **kwargs):
            assert parent == ""
            assert path == "/org/freedesktop/portal/desktop"
            assert events == ["register", "subscribe"]
            assert state["path"] == (
                "/org/freedesktop/portal/desktop/request/1_23/"
                + options["handle_token"]
            )
            events.append("request")
            if outcome == "approved-early":
                state["response"](
                    0, {"uri": QUrl.fromLocalFile(str(image_path)).toString()}
                )
            return state["path"]

        if name == "org.freedesktop.host.portal.Registry":
            return SimpleNamespace(Register=lambda *a, **kw: events.append("register"))
        if name == "org.freedesktop.portal.Screenshot":
            return SimpleNamespace(Screenshot=screenshot)
        assert name == "org.freedesktop.portal.Request"
        assert path == state["path"]
        return SimpleNamespace(Close=lambda **kw: events.append("close"))

    def timeout_add(milliseconds, callback):
        assert milliseconds == 10000
        state["timeout"] = callback
        return 42

    dbus = ModuleType("dbus")
    dbus.SessionBus = Bus
    dbus.Interface = interface
    glib = SimpleNamespace(
        MainLoop=Loop,
        timeout_add=timeout_add,
        source_remove=lambda source: events.append(("remove-timer", source)),
    )
    modules = {
        "dbus": dbus,
        "dbus.mainloop": ModuleType("dbus.mainloop"),
        "dbus.mainloop.glib": SimpleNamespace(DBusGMainLoop=lambda **kw: None),
        "gi": ModuleType("gi"),
        "gi.repository": SimpleNamespace(GLib=glib),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    result = wayland_screenshot_via_portal()
    assert "unsubscribe" in events
    assert events[-1] == "disconnect"
    if outcome.startswith("approved"):
        assert result is not None and (result.width(), result.height()) == (3, 2)
        assert not image_path.exists()
    else:
        assert result is None
    if outcome == "timeout":
        assert "close" in events
    else:
        assert ("remove-timer", 42) in events

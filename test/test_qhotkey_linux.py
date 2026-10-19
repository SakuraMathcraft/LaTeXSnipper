from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

import platform_services.hotkeys.qhotkey_linux as linux_hotkeys
from platform_services.hotkeys.qhotkey_linux import LinuxHotkey


def test_pynput_combo_uses_separate_modifier_brackets() -> None:
    mods, key = LinuxHotkey._parse("Ctrl+F")

    assert mods == {"ctrl"}
    assert key == "f"
    assert LinuxHotkey._pynput_combo(mods, key) == "<ctrl>+f"


def test_pynput_combo_supports_multiple_modifiers() -> None:
    mods, key = LinuxHotkey._parse("Ctrl+Shift+F")

    assert mods == {"ctrl", "shift"}
    assert key == "f"
    assert LinuxHotkey._pynput_combo(mods, key) == "<ctrl>+<shift>+f"


def test_pynput_function_key_uses_named_key_syntax():
    mods, key = LinuxHotkey._parse("Ctrl+F8")
    assert LinuxHotkey._pynput_combo(mods, key) == "<ctrl>+<f8>"


@pytest.fixture
def hotkey_app():
    return QApplication.instance() or QApplication(["LaTeXSnipper-hotkey-tests"])


def test_wayland_authorization_preserves_active_shortcut_until_approved(
    hotkey_app, monkeypatch
):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    instances = []

    class Portal:
        def __init__(self, trigger, description, ready, activated):
            self.trigger, self.ready, self.activated = trigger, ready, activated
            self.stopped = False
            instances.append(self)

        def start(self):
            pass

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(linux_hotkeys, "_PortalHotkey", Portal)
    hotkey = LinuxHotkey()
    results, activations = [], []
    hotkey.registration_finished.connect(lambda ok, error: results.append(ok))
    hotkey.activated.connect(lambda: activations.append(True))
    try:
        hotkey.register("Ctrl+F")
        first = instances[-1]
        assert first.trigger == "CTRL+f"
        assert not hotkey.is_registered() and not results
        first.ready(True, "", "Ctrl+F")
        assert hotkey.is_registered()

        hotkey.register("Ctrl+Shift+G")
        cancelled = instances[-1]
        first.activated()
        cancelled.ready(False, "cancelled", "")
        assert hotkey.is_registered() and not first.stopped
        assert cancelled.stopped and hotkey.shortcut_description == "Ctrl+F"

        hotkey.register("Ctrl+H")
        abandoned = instances[-1]
        hotkey.cancel_registration()
        abandoned.ready(True, "", "Ctrl+H")
        abandoned.activated()
        assert abandoned.stopped and hotkey.shortcut_description == "Ctrl+F"

        hotkey.register("Ctrl+J")
        replacement = instances[-1]
        replacement.ready(True, "", "Super+J")
        first.activated()
        replacement.activated()
        assert first.stopped and hotkey.shortcut_description == "Super+J"
        assert activations == [True, True]
        assert results == [True, False, True]
    finally:
        hotkey.cleanup()
    assert replacement.stopped and not hotkey.is_registered()


def test_x11_listener_failure_is_reported(hotkey_app, monkeypatch):
    import sys

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    class Listener:
        alive = True

        def __init__(self, callbacks):
            pass

        def start(self):
            pass

        def stop(self):
            self.alive = False

        def is_alive(self):
            return self.alive

        def _mark_ready(self):
            pass

    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(GlobalHotKeys=Listener)),
    )
    hotkey = LinuxHotkey()
    results = []
    hotkey.registration_finished.connect(lambda ok, error: results.append(ok))
    try:
        hotkey.register("Ctrl+F")
        assert not hotkey.is_registered() and not results
        listener = hotkey._listener
        listener._mark_ready()
        assert hotkey.is_registered() and results == [True]
        listener.alive = False
        hotkey._check_listener()
        assert not hotkey.is_registered() and results == [True, False]
    finally:
        hotkey.cleanup()


@pytest.mark.parametrize("outcome", ["approved", "cancelled", "closed"])
def test_shortcut_preferences_wait_for_system_authorization(
    hotkey_app, monkeypatch, outcome
):
    import ui.controllers.hotkey as controller_module

    class Provider(QObject):
        registration_finished = pyqtSignal(bool, str)
        shortcut_description = "Super+G"
        cancelled = False

        def register(self, seq):
            self.requested = seq

        def cancel_registration(self):
            self.cancelled = True

    notices = []
    monkeypatch.setattr(
        controller_module,
        "InfoBar",
        SimpleNamespace(
            info=lambda **kwargs: notices.append(("info", kwargs)),
            error=lambda **kwargs: notices.append(("error", kwargs)),
            success=lambda **kwargs: notices.append(("success", kwargs)),
        ),
    )
    values = {"hotkey": "Ctrl+F"}
    view = QWidget()
    provider = Provider(view)
    controller = controller_module.HotkeyController(
        view,
        SimpleNamespace(get=values.get, set=values.__setitem__),
        None,
        provider,
        SimpleNamespace(notification_parent=lambda: view),
    )
    dialog = QDialog(view)
    controller.update_hotkey("Ctrl+G", dialog)
    assert values["hotkey"] == "Ctrl+F" and notices[-1][0] == "info"
    if outcome == "closed":
        controller._cancel_pending_change(dialog)
        provider.registration_finished.emit(True, "")
        assert provider.cancelled and values["hotkey"] == "Ctrl+F"
    else:
        provider.registration_finished.emit(outcome == "approved", "Cancelled")
        assert values["hotkey"] == ("Ctrl+G" if outcome == "approved" else "Ctrl+F")
        assert notices[-1][0] == ("success" if outcome == "approved" else "error")
        if outcome == "approved":
            assert "Super+G" in notices[-1][1]["content"]


@pytest.mark.parametrize(
    "outcome", ["approved", "cancelled", "empty", "closed", "stopped"]
)
def test_portal_wire_messages_authorization_activation_and_cleanup(
    monkeypatch, outcome
):
    dbus = pytest.importorskip("jeepney")
    import jeepney.io.blocking

    owner = ":1.99"
    messages, sent, events = deque(), [], []
    session = "/org/freedesktop/portal/desktop/session/1_12/capture"

    def signal(path, interface, member, signature, body):
        message = dbus.new_signal(
            dbus.DBusAddress(path, interface=interface), member, signature, body
        )
        message.header.fields[dbus.HeaderFields.sender] = owner
        return message

    class Connection:
        unique_name = ":1.12"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("disconnected")

        @contextmanager
        def filter(self, *args, **kwargs):
            yield messages

        def send_and_get_reply(self, message, **kwargs):
            # Exercise real D-Bus encoding, including oa(sa{sv})sa{sv}.
            parser = dbus.Parser()
            parser.add_data(message.serialise(serial=1))
            decoded = parser.get_next_message()
            assert decoded.body == message.body
            member = message.header.fields[dbus.HeaderFields.member]
            if member == "AddMatch":
                reply = dbus.new_method_return(message)
            else:
                options = message.body[-1]
                request = f"{linux_hotkeys._PORTAL_PATH}/request/1_12/{options['handle_token'][1]}"
                if member == "CreateSession":
                    response, results = 0, {"session_handle": ("s", session)}
                else:
                    assert member == "BindShortcuts"
                    assert message.body[0] == session
                    assert message.body[1][0][1]["preferred_trigger"] == ("s", "CTRL+f")
                    response = 1 if outcome == "cancelled" else 0
                    shortcuts = (
                        []
                        if outcome == "empty"
                        else [("capture", {"trigger_description": ("s", "Super+F")})]
                    )
                    results = {"shortcuts": ("a(sa{sv})", shortcuts)}
                    if outcome == "stopped":
                        hotkey.stop()
                # Responses can arrive before the method's immediate reply.
                messages.append(
                    signal(
                        request,
                        "org.freedesktop.portal.Request",
                        "Response",
                        "ua{sv}",
                        (response, results),
                    )
                )
                if member == "BindShortcuts":
                    if outcome == "closed":
                        messages.append(
                            signal(
                                session,
                                "org.freedesktop.portal.Session",
                                "Closed",
                                "",
                                (),
                            )
                        )
                    else:
                        for target_session, action in (
                            (session, "other"),
                            (session + "_other", "capture"),
                            (session, "capture"),
                        ):
                            messages.append(
                                signal(
                                    linux_hotkeys._PORTAL_PATH,
                                    linux_hotkeys._PORTAL_INTERFACE,
                                    "Activated",
                                    "osta{sv}",
                                    (target_session, action, 1, {}),
                                )
                            )
                reply = dbus.new_method_return(message, "o", (request,))
            reply.header.fields[dbus.HeaderFields.sender] = owner
            return reply

        def recv_until_filtered(self, queue, **kwargs):
            return queue.popleft()

        def send(self, message):
            sent.append(
                (
                    message.header.fields[dbus.HeaderFields.path],
                    message.header.fields[dbus.HeaderFields.member],
                )
            )

    def ready(ok, error, description):
        events.append((ok, error, description))

    def activated():
        events.append("activated")
        hotkey.stop()

    monkeypatch.setattr(
        jeepney.io.blocking, "open_dbus_connection", lambda **kwargs: Connection()
    )
    hotkey = linux_hotkeys._PortalHotkey("CTRL+f", "Capture", ready, activated)
    hotkey._run()
    assert (session, "Close") in sent and "disconnected" in events
    if outcome == "approved":
        assert events == [(True, "", "Super+F"), "activated", "disconnected"]
    elif outcome == "stopped":
        assert events == ["disconnected"]
        assert len(sent) == 2  # Cancel the pending request and close its session.
    else:
        assert "activated" not in events
        assert any(isinstance(event, tuple) and event[0] is False for event in events)

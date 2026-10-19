"""Linux global hotkeys: desktop portal on Wayland and pynput on X11."""

from __future__ import annotations

import importlib
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence

from localization.manager import translate as tr

logger = logging.getLogger(f"latexsnipper.{__name__}")


class LinuxHotkey(QObject):
    activated = pyqtSignal()
    registration_finished = pyqtSignal(bool, str)
    _portal_ready = pyqtSignal(object, bool, str, str)
    _portal_activated = pyqtSignal(object)
    _x11_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq_obj: QKeySequence | None = None
        self._seq_str: str | None = None
        self._registered = False
        self._listener = None
        self._portal = None
        self._previous_portal = None
        self._pending = False
        self.shortcut_description = ""
        self._portal_ready.connect(self._finish_portal)
        self._portal_activated.connect(self._activate_portal)
        self._x11_ready.connect(self._finish_x11)
        self._listener_check = QTimer(self)
        self._listener_check.setInterval(1000)
        self._listener_check.timeout.connect(self._check_listener)

    def setShortcut(self, seq: QKeySequence) -> None:
        self._seq_obj = seq
        self._seq_str = self._qkeysequence_to_string(seq)

    @staticmethod
    def _qkeysequence_to_string(seq: QKeySequence) -> str:
        kc = seq[0]
        mods = kc.keyboardModifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        key = kc.key()
        if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
            parts.append(chr(ord("A") + (key - Qt.Key.Key_A.value)))
        elif Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
            parts.append(chr(ord("0") + (key - Qt.Key.Key_0.value)))
        elif Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F12.value:
            parts.append(f"F{key - Qt.Key.Key_F1.value + 1}")
        else:
            raise ValueError(f"Unsupported key: {key}")
        return "+".join(parts)

    @staticmethod
    def _parse(keyseq_str: str) -> tuple[set[str], str]:
        """Parse "Ctrl+Shift+F" into ({'ctrl', 'shift'}, 'f')."""
        ks = keyseq_str.upper().replace(" ", "")
        parts = ks.split("+")
        mods = set()
        key_part = None
        for p in parts:
            if p == "CTRL":
                mods.add("ctrl")
            elif p == "SHIFT":
                mods.add("shift")
            elif p == "ALT":
                mods.add("alt")
            elif p in ("WIN", "CMD", "META"):
                mods.add("cmd")
            else:
                key_part = p
        if not key_part or not mods:
            raise ValueError(f"Invalid hotkey: {keyseq_str}")
        return mods, key_part.lower()

    @staticmethod
    def _pynput_combo(mods: set[str], key: str) -> str:
        """Return the GlobalHotKeys combo syntax, e.g. '<ctrl>+<shift>+f'."""
        if key.startswith("f") and key[1:].isdigit():
            key = f"<{key}>"
        return "+".join([*(f"<{mod}>" for mod in sorted(mods)), key])

    def register(self, seq: QKeySequence | str | None = None) -> None:
        if seq is not None:
            if isinstance(seq, str):
                seq = QKeySequence(seq)
            self.setShortcut(seq)
        if not self._seq_str:
            raise RuntimeError("No shortcut set")
        mods, key = self._parse(self._seq_str)
        wayland = (
            bool(os.environ.get("WAYLAND_DISPLAY"))
            or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        )
        if wayland:
            self._register_portal(mods, key)
            return
        self.unregister()
        try:
            from pynput import keyboard  # pyright: ignore[reportMissingModuleSource]

            owner = self

            class ReadyHotkeys(keyboard.GlobalHotKeys):
                def _mark_ready(self):
                    super()._mark_ready()
                    try:
                        owner._x11_ready.emit(self)
                    except RuntimeError:
                        self.stop()

            listener = ReadyHotkeys(
                {self._pynput_combo(mods, key): self.activated.emit}
            )
            self._listener = listener
            listener.start()
            self._listener_check.start()
        except Exception as exc:
            self.unregister()
            logger.warning("X11 全局快捷键不可用: %s", exc)
            self.registration_finished.emit(False, str(exc))
            return

    def _finish_x11(self, listener) -> None:
        if listener is not self._listener:
            return
        if not listener.is_alive():
            self._check_listener()
            return
        self._registered = True
        self.registration_finished.emit(True, "")

    def _register_portal(self, mods: set[str], key: str) -> None:
        self.cancel_registration()
        names = {"ctrl": "CTRL", "shift": "SHIFT", "alt": "ALT", "cmd": "LOGO"}
        trigger = "+".join(
            [
                *(names[mod] for mod in sorted(mods)),
                key.upper() if key.startswith("f") and key[1:].isdigit() else key,
            ]
        )

        def ready(ok, error, description):
            try:
                self._portal_ready.emit(portal, ok, error, description)
            except RuntimeError:
                portal.stop()

        def activated():
            try:
                self._portal_activated.emit(portal)
            except RuntimeError:
                portal.stop()

        portal = _PortalHotkey(trigger, tr("截图识别"), ready, activated)
        self._previous_portal = self._portal
        self._portal = portal
        self._pending = True
        portal.start()

    def _finish_portal(self, portal, ok: bool, error: str, description: str) -> None:
        if portal is self._previous_portal:
            if not ok:
                portal.stop()
                self._previous_portal = None
                self._registered = False
            return
        if portal is not self._portal:
            return
        self._pending = False
        if ok:
            if self._previous_portal is not None:
                self._previous_portal.stop()
                self._previous_portal = None
            self._registered = True
            self.shortcut_description = description
        else:
            portal.stop()
            self._portal = self._previous_portal
            self._previous_portal = None
            self._registered = self._portal is not None
            if not self._registered:
                self.shortcut_description = ""
            error = (
                tr("已取消系统快捷键授权。")
                if error == "cancelled"
                else tr("Wayland 全局快捷键不可用：{error}").format(error=error)
            )
        self.registration_finished.emit(ok, error)

    def _activate_portal(self, portal) -> None:
        active = self._previous_portal if self._pending else self._portal
        if portal is active and self._registered:
            self.activated.emit()

    def _check_listener(self) -> None:
        if self._listener is not None and not self._listener.is_alive():
            self.unregister()
            self.registration_finished.emit(
                False, tr("X11 快捷键监听已停止，请重新设置快捷键。")
            )

    def cancel_registration(self) -> None:
        if self._listener is not None and not self._registered:
            self.unregister()
        if self._portal is not None and self._pending:
            self._portal.stop()
            self._portal = self._previous_portal
            self._previous_portal = None
            self._registered = self._portal is not None
            self._pending = False

    def unregister(self) -> None:
        self._listener_check.stop()
        self._registered = False
        self._pending = False
        self.shortcut_description = ""
        for portal in (self._portal, self._previous_portal):
            if portal is not None:
                portal.stop()
        self._portal = self._previous_portal = None
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                logger.warning("停止 X11 热键监听失败", exc_info=True)
            self._listener = None

    def is_registered(self) -> bool:
        if self._portal is not None:
            return self._registered
        return (
            self._registered
            and self._listener is not None
            and self._listener.is_alive()
        )

    def cleanup(self) -> None:
        self.unregister()


_PORTAL_BUS = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
_CAPTURE_ACTION = "capture"


class _PortalHotkey:
    def __init__(
        self,
        trigger: str,
        description: str,
        ready: Callable[[bool, str, str], None],
        activated: Callable[[], None],
    ):
        self._dbus = importlib.import_module("jeepney")
        self._unwrap = importlib.import_module("jeepney.wrappers").unwrap_msg
        self._open_connection = importlib.import_module(
            "jeepney.io.blocking"
        ).open_dbus_connection
        self.trigger = trigger
        self.description = description
        self.ready = ready
        self.activated = activated
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="wayland-hotkey", daemon=True
        )
        self._session = ""
        self._request = ""
        self._owner = ""

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def _call(self, connection, address, method, signature=None, body=()):
        reply = connection.send_and_get_reply(
            self._dbus.new_method_call(address, method, signature, body), timeout=5
        )
        result = self._unwrap(reply)
        if address.bus_name == _PORTAL_BUS:
            self._owner = reply.header.fields[self._dbus.HeaderFields.sender]
        return result

    def _receive(self, connection, messages, deadline: float | None = None):
        while not self.stopped.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Global shortcut authorization timed out")
            try:
                message = connection.recv_until_filtered(messages, timeout=0.2)
            except TimeoutError:
                continue
            if message.header.fields.get(self._dbus.HeaderFields.sender) != self._owner:
                if (
                    message.header.fields.get(self._dbus.HeaderFields.sender)
                    == "org.freedesktop.DBus"
                    and message.header.fields.get(self._dbus.HeaderFields.member)
                    == "NameOwnerChanged"
                    and message.body[0] == _PORTAL_BUS
                    and message.body[1] == self._owner
                ):
                    raise RuntimeError("GlobalShortcuts portal disconnected")
                continue
            if (
                message.header.fields.get(self._dbus.HeaderFields.path) == self._session
                and message.header.fields.get(self._dbus.HeaderFields.member)
                == "Closed"
            ):
                raise RuntimeError("Global shortcut session was closed by the desktop")
            return message
        return None

    def _authorize(self, connection, messages, method, signature, body, options):
        token = "latexsnipper_" + uuid.uuid4().hex
        options["handle_token"] = ("s", token)
        self._request = f"{_PORTAL_PATH}/request/{connection.unique_name[1:].replace('.', '_')}/{token}"
        reply = self._call(
            connection,
            self._dbus.DBusAddress(_PORTAL_PATH, _PORTAL_BUS, _PORTAL_INTERFACE),
            method,
            signature,
            (*body, options),
        )
        if reply != (self._request,):
            raise RuntimeError("Unexpected GlobalShortcuts request identity")
        deadline = time.monotonic() + 180
        while message := self._receive(connection, messages, deadline):
            fields = message.header.fields
            if (
                fields.get(self._dbus.HeaderFields.path) != self._request
                or fields.get(self._dbus.HeaderFields.member) != "Response"
            ):
                continue
            self._request = ""
            response, results = message.body
            if response:
                raise RuntimeError(
                    "cancelled" if response == 1 else "Shortcut authorization failed"
                )
            return results
        return None

    def _run(self) -> None:
        try:
            with self._open_connection(auth_timeout=3) as connection:
                remote = self._dbus.MatchRule(
                    type="signal", sender=_PORTAL_BUS, path_namespace=_PORTAL_PATH
                )
                with connection.filter(
                    self._dbus.MatchRule(type="signal"), bufsize=64
                ) as messages:
                    self._call(
                        connection,
                        self._dbus.message_bus,
                        "AddMatch",
                        "s",
                        (remote.serialise(),),
                    )
                    owner_changed = self._dbus.MatchRule(
                        type="signal",
                        sender="org.freedesktop.DBus",
                        interface="org.freedesktop.DBus",
                        member="NameOwnerChanged",
                    )
                    owner_changed.add_arg_condition(0, _PORTAL_BUS)
                    self._call(
                        connection,
                        self._dbus.message_bus,
                        "AddMatch",
                        "s",
                        (owner_changed.serialise(),),
                    )
                    try:
                        created = self._authorize(
                            connection,
                            messages,
                            "CreateSession",
                            "a{sv}",
                            (),
                            {
                                "session_handle_token": (
                                    "s",
                                    "latexsnipper_" + uuid.uuid4().hex,
                                )
                            },
                        )
                        if created is None:
                            return
                        self._session = created["session_handle"][1]
                        shortcut = (
                            _CAPTURE_ACTION,
                            {
                                "description": ("s", self.description),
                                "preferred_trigger": ("s", self.trigger),
                            },
                        )
                        bound = self._authorize(
                            connection,
                            messages,
                            "BindShortcuts",
                            "oa(sa{sv})sa{sv}",
                            (self._session, [shortcut], ""),
                            {},
                        )
                        if bound is None:
                            return
                        shortcuts = bound.get("shortcuts", ("a(sa{sv})", []))[1]
                        descriptions = {name: values for name, values in shortcuts}
                        if _CAPTURE_ACTION not in descriptions:
                            raise RuntimeError("No global shortcut was authorized")
                        label = descriptions[_CAPTURE_ACTION].get(
                            "trigger_description", ("s", self.trigger)
                        )[1]
                        if not self.stopped.is_set():
                            self.ready(True, "", label)
                        while message := self._receive(connection, messages):
                            fields = message.header.fields
                            if (
                                fields.get(self._dbus.HeaderFields.interface)
                                != _PORTAL_INTERFACE
                            ):
                                continue
                            if fields.get(
                                self._dbus.HeaderFields.member
                            ) == "Activated" and message.body[:2] == (
                                self._session,
                                _CAPTURE_ACTION,
                            ):
                                self.activated()
                            elif (
                                fields.get(self._dbus.HeaderFields.member)
                                == "ShortcutsChanged"
                                and message.body[0] == self._session
                            ):
                                values = dict(message.body[1]).get(_CAPTURE_ACTION)
                                if values is None:
                                    raise RuntimeError(
                                        "Global shortcut was removed by the desktop"
                                    )
                                self.ready(
                                    True,
                                    "",
                                    values.get(
                                        "trigger_description", ("s", self.trigger)
                                    )[1],
                                )
                    finally:
                        for path, interface in (
                            (self._request, "Request"),
                            (self._session, "Session"),
                        ):
                            if path:
                                try:
                                    connection.send(
                                        self._dbus.new_method_call(
                                            self._dbus.DBusAddress(
                                                path,
                                                _PORTAL_BUS,
                                                f"org.freedesktop.portal.{interface}",
                                            ),
                                            "Close",
                                        )
                                    )
                                except OSError:
                                    logger.debug(
                                        "关闭热键 Portal 会话失败", exc_info=True
                                    )
        except Exception as exc:
            if not self.stopped.is_set():
                logger.warning("Wayland 全局快捷键不可用: %s", exc)
                self.ready(False, str(exc), "")

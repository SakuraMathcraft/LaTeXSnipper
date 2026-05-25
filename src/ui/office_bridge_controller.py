"""Office bridge lifecycle controller for the main window."""

from __future__ import annotations

import secrets

from PyQt6.QtCore import QTimer

from integration.office.bridge_auth import OfficeBridgeAuth
from integration.office.bridge_server import OfficeBridgeServer


OFFICE_BRIDGE_ENABLED_KEY = "office_bridge_enabled"
OFFICE_BRIDGE_PORT_KEY = "office_bridge_port"
OFFICE_BRIDGE_TOKEN_KEY = "office_bridge_token"
DEFAULT_OFFICE_BRIDGE_PORT = 8765


class OfficeBridgeControllerMixin:
    def _office_bridge_enabled_pref(self) -> bool:
        try:
            return bool(self.cfg.get(OFFICE_BRIDGE_ENABLED_KEY, False))
        except Exception:
            return False

    def _office_bridge_port_pref(self) -> int:
        try:
            value = int(self.cfg.get(OFFICE_BRIDGE_PORT_KEY, DEFAULT_OFFICE_BRIDGE_PORT))
        except Exception:
            value = DEFAULT_OFFICE_BRIDGE_PORT
        return min(max(value, 1024), 65535)

    def _office_bridge_token(self) -> str:
        token = ""
        try:
            token = str(self.cfg.get(OFFICE_BRIDGE_TOKEN_KEY, "") or "").strip()
        except Exception:
            token = ""
        if token:
            return token
        token = secrets.token_urlsafe(32)
        try:
            self.cfg.set(OFFICE_BRIDGE_TOKEN_KEY, token)
        except Exception:
            pass
        return token

    def office_bridge_is_running(self) -> bool:
        return bool(getattr(self, "_office_bridge_server", None))

    def office_bridge_status_text(self) -> str:
        server = getattr(self, "_office_bridge_server", None)
        if server:
            return f"Office bridge: {server.base_url}"
        if self._office_bridge_enabled_pref():
            return "Office bridge: enabled, not running"
        return "Office bridge: disabled"

    def apply_office_bridge_startup_preference(self) -> None:
        if self._office_bridge_enabled_pref():
            self._start_office_bridge()

    def set_office_bridge_enabled_async(self, enabled: bool, callback=None) -> None:
        try:
            self.cfg.set(OFFICE_BRIDGE_ENABLED_KEY, bool(enabled))
        except Exception:
            pass

        def _apply() -> None:
            ok = True
            message = ""
            try:
                if enabled:
                    self._start_office_bridge()
                    message = self.office_bridge_status_text()
                else:
                    self._stop_office_bridge()
                    message = "Office bridge: disabled"
            except Exception as exc:
                ok = False
                message = str(exc)
                try:
                    self.cfg.set(OFFICE_BRIDGE_ENABLED_KEY, False)
                except Exception:
                    pass
            if callback:
                callback(ok, message)

        QTimer.singleShot(0, _apply)

    def _start_office_bridge(self) -> None:
        if getattr(self, "_office_bridge_server", None):
            return
        server = OfficeBridgeServer(
            port=self._office_bridge_port_pref(),
            auth=OfficeBridgeAuth(self._office_bridge_token()),
        )
        server.start()
        self._office_bridge_server = server
        print(f"[INFO] Office bridge started: {server.base_url}")

    def _stop_office_bridge(self) -> None:
        server = getattr(self, "_office_bridge_server", None)
        self._office_bridge_server = None
        if server:
            server.stop()
            print("[INFO] Office bridge stopped")

"""Authentication helpers for the Office bridge."""

from __future__ import annotations

import hmac
import secrets


class OfficeBridgeAuth:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or secrets.token_urlsafe(32)

    @property
    def token(self) -> str:
        return self._token

    def verify_authorization(self, header_value: str | None) -> bool:
        prefix = "Bearer "
        if not header_value or not header_value.startswith(prefix):
            return False
        candidate = header_value[len(prefix):].strip()
        return bool(candidate) and hmac.compare_digest(candidate, self._token)
